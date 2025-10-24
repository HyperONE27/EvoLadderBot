# Counter-Analysis of `code_quality_analysis.md` (Expanded)

## Executive Summary

This document serves as a critical re-evaluation of the findings presented in `code_quality_analysis.md`. Each claim has been investigated with the intent to disprove it, ensuring that confirmed issues are legitimate and not just theoretical concerns.

The investigation confirms that the majority of the critical and high-priority issues identified in the original analysis are valid and represent tangible risks to the application's stability, data integrity, and performance. While some lower-priority claims were debatable, the core architectural fragilities are accurately identified. This expanded version provides deep-dive explanations and actionable, measurable remediation plans for each confirmed issue.

---

## 1. Critical Issues Re-evaluation

### 1.1. Singleton Pattern Race Conditions

-   **Claim:** The `DataAccessService` singleton implementation contains a race condition.
-   **Verdict:** **Confirmed.**

#### In-Depth Explanation

The current singleton pattern in `src/backend/services/data_access_service.py` is not safe for an `asyncio` environment. The root of the problem lies in how an `asyncio` event loop can switch between tasks at any `await` point.

**Failure Scenario:**
1.  **Coroutine A** calls `DataAccessService()`. It enters `__new__`, finds `cls._instance` is `None`, creates a new object, and returns it.
2.  **Coroutine A** then enters `__init__`. It checks the `_initialized` flag (which is `False`) and proceeds with initialization. Let's say it hits an `await` statement inside an `async def initialize()` method that is called from `__init__`. At this point, control is yielded back to the event loop.
3.  **Coroutine B** now runs. It calls `DataAccessService()`. It enters `__new__` and gets the same, *partially initialized* instance created by Coroutine A.
4.  **Coroutine B** enters `__init__`. It also sees `_initialized` as `False` and proceeds to run the exact same initialization logic.
5.  **Result:** Critical components like the `_write_queue`, `_init_lock`, and the background writer task (`_writer_task`) are initialized twice. This can lead to a state where two writer tasks are competing to pull jobs from two different queue instances, leading to data loss, unpredictable write behavior, and difficult-to-debug race conditions.

#### Measurable Remediation Plan

1.  **Introduce a Class-Level Lock:** Add an `asyncio.Lock` to the `DataAccessService` class definition.
    ```python
    class DataAccessService:
        _instance: Optional['DataAccessService'] = None
        _initialized: bool = False
        _lock = asyncio.Lock() # New lock
    ```
2.  **Create an Asynchronous Getter:** Implement an `async` class method to act as the sole entry point for acquiring the service instance. The direct `DataAccessService()` constructor should be deprecated.
3.  **Implement Double-Checked Locking:** The getter method must use the lock and check for initialization status both before and after acquiring the lock to ensure atomicity.
    ```python
    @classmethod
    async def get_instance(cls) -> 'DataAccessService':
        if not cls._instance:
            async with cls._lock:
                # Check again inside the lock to prevent a race condition
                # where another task initialized it while we were waiting for the lock.
                if not cls._instance:
                    instance = cls.__new__(cls)
                    # Use a private async method for initialization
                    await instance._initialize()
                    cls._instance = instance
        return cls._instance
    
    async def _initialize(self):
        # All original __init__ logic goes here.
        # This ensures initialization happens only once, atomically.
        if self._initialized:
            return
        # ... (setup queues, dataframes, start worker task)
        self._initialized = True
    ```
4.  **Refactor Call Sites:** Systematically replace all calls from `DataAccessService()` to `await DataAccessService.get_instance()`.
5.  **Mandate Eager Initialization:** The `await DataAccessService.get_instance()` method **must** be called once during the bot's main startup sequence (e.g., in `initialize_backend_services`). This ensures the service is fully loaded before any user commands are processed, preventing a "first request penalty" where a user's command hangs while the database is loaded. Do not use lazy-loading patterns where the service is initialized on its first use within a command.
6.  **Measurement:** Create a test that spawns multiple coroutines (`asyncio.gather`) which all attempt to get the instance concurrently. Add logging inside the `_initialize` method and assert that the initialization log message appears exactly once.

---

### 1.2. Database Connection Pool Exhaustion

-   **Claim:** The exception handling in `src/backend/db/connection_pool.py` is overly complex and could leak connections.
-   **Verdict:** **Confirmed.**

#### In-Depth Explanation

The `get_connection` context manager's `finally` block contains nested `try...except Exception: pass` blocks. This pattern is dangerous because it can swallow critical errors during the connection cleanup phase, leading to connection leaks.

**Failure Scenario:**
1.  A connection `conn` is successfully retrieved from the pool. The code using the connection works fine.
2.  The `finally` block is entered to clean up the connection.
3.  `_validate_connection(conn)` is called. Let's assume the database has just restarted, and this check raises a `psycopg2.InterfaceError` because the connection is now dead.
4.  The `except Exception as e:` block at line 174 catches this `InterfaceError`.
5.  Inside this block, it attempts `conn.close()`. However, because the connection is in a broken state, `conn.close()` *also* raises an exception.
6.  This second exception is caught by the `except Exception: pass` block and is silently ignored.
7.  The function then exits. The connection was never returned to the pool via `_global_pool.putconn(conn)` and was never successfully closed. It is now an "orphaned" or "zombie" connection.
8.  If this scenario repeats, the pool will gradually be depleted of usable connections until it is exhausted, causing the application to hang.

#### Measurable Remediation Plan

1.  **Simplify the `finally` Block:** Refactor the logic to remove nested, silent `try/except` blocks. The goal is to make cleanup deterministic.
2.  **Prioritize Returning to Pool:** The default action should always be to return the connection. Closing it should be a deliberate choice only when the connection is known to be invalid.
3.  **Refactored Logic:**
    ```python
    @contextmanager
    def get_connection():
        conn = None
        try:
            conn = _global_pool.getconn()
            yield conn
            conn.commit()
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            # For connection-related errors, we assume the connection is bad.
            # We don't re-raise immediately, but ensure it's closed.
            print(f"[DB Pool] Connection error: {e}. Discarding connection.")
            if conn:
                try:
                    conn.close()
                except Exception as close_exc:
                    print(f"[DB Pool] Error closing a bad connection: {close_exc}")
            conn = None # Mark as handled
            raise e # Re-raise original error
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                _global_pool.putconn(conn)
    ```
4.  **Measurement:**
    -   Add distinct logging for each path: `Connection returned to pool`, `Connection closed due to error`, `Failed to close bad connection`.
    -   Implement a monitoring function that periodically logs the status of the connection pool (`_global_pool.minconn`, `_global_pool.maxconn`, and the number of used connections). This will make it possible to observe if the number of used connections grows over time without decreasing.

---

### 1.3. Memory Leak in Async Task Management

-   **Claim:** Background tasks created in `QueueSearchingView` (`src/bot/commands/queue_command.py`) are not properly cleaned up.
-   **Verdict:** **Confirmed.**

#### In-Depth Explanation

When a `QueueSearchingView` is created, it spawns `self.match_task = asyncio.create_task(self._listen_for_match())`. This task waits indefinitely for a match notification. Discord UI views have a timeout (`GLOBAL_TIMEOUT`). When a view times out, Discord stops listening for interactions with it, and the `on_timeout` method on the view object is called.

**Failure Scenario:**
1.  A user joins the queue, creating a `QueueSearchingView` and its associated `match_task`.
2.  No match is found within the timeout period (e.g., 5 minutes).
3.  The `on_timeout` method is called. The current implementation of `QueueSearchingView` lacks an `on_timeout` method, so the default `discord.ui.View.on_timeout` is called, which does nothing but disable the view items.
4.  Crucially, `self.match_task.cancel()` is **never called**.
5.  The `match_task` now lives forever in the `asyncio` event loop, holding a reference to its coroutine (`_listen_for_match`). That coroutine holds a reference to `self` (the `QueueSearchingView` instance).
6.  Because the task holds a reference to the view, the Python garbage collector cannot reclaim the memory for the `QueueSearchingView` object.
7.  For every user who queues up and subsequently times out, a task and a view object are leaked. This will cause the bot's memory usage to grow steadily over time.

#### Measurable Remediation Plan

1.  **Implement a Cleanup Method:** Create a dedicated `stop()` or `cleanup()` method in `QueueSearchingView`.
    ```python
    class QueueSearchingView(discord.ui.View):
        # ... existing __init__ ...

        def stop_tasks(self):
            """Safely cancel all background tasks associated with this view."""
            self.is_active = False
            if self.match_task and not self.match_task.done():
                self.match_task.cancel()
            if self.status_task and not self.status_task.done():
                self.status_task.cancel()
    ```
2.  **Hook into View Lifecycle:** Call this `stop_tasks` method from all points where the view's lifecycle ends.
    ```python
    # In the button callback that cancels the queue
    class CancelQueueButton(discord.ui.Button):
        async def callback(self, interaction: discord.Interaction):
            # ... existing logic ...
            self.view.stop_tasks()
            await matchmaker.remove_player(self.player)

    # In the main view class for timeout handling
    class QueueSearchingView(discord.ui.View):
        # ... existing methods ...
        async def on_timeout(self) -> None:
            print(f"Queue view for player {self.player.discord_user_id} timed out.")
            self.stop_tasks()
            # Also ensure the player is removed from the matchmaker backend
            await matchmaker.remove_player(self.player)
    ```
3.  **Measurement:**
    -   In a test environment, get the set of all running tasks before a user queues: `tasks_before = asyncio.all_tasks()`.
    -   Simulate a user queueing and then timing out (by creating the view with a very short timeout).
    -   After the timeout, get the set of running tasks again: `tasks_after = asyncio.all_tasks()`.
    -   Assert that `tasks_after == tasks_before`. This proves the created task was successfully cancelled and cleaned up.

---

## 2. High Priority Issues Re-evaluation

### 2.1. Discord Interaction Token Expiration

-   **Claim:** The bot does not handle the 15-minute expiration of Discord interaction tokens.
-   **Verdict:** **Confirmed.**

#### In-Depth Explanation

Discord interactions (slash commands, button clicks) provide a temporary token that is valid for 15 minutes. This token allows you to respond to or edit the original response message without needing full channel permissions. The bot relies heavily on `interaction.edit_original_response()` to update the `MatchFoundView`.

**Failure Scenario:**
1.  Two players are matched. A `MatchFoundView` is displayed in their DMs using `edit_original_response`.
2.  They play a game that lasts 20 minutes.
3.  Player 1 wins and uploads the replay to the DM channel. The bot's `on_message` event handler receives the replay.
4.  The handler processes the replay and determines the match outcome. It then attempts to update the `MatchFoundView` by calling `await self.last_interaction.edit_original_response(...)`.
5.  Because more than 15 minutes have passed, the interaction token is expired. The Discord API returns a `404 Not Found` error.
6.  The `discord.py` library raises a `discord.errors.NotFound` exception. The current code does not handle this exception, causing the entire `on_message` handler to crash for that replay.
7.  **Result:** The user who uploaded the replay receives no confirmation, the UI is not updated with the result, and MMR is not processed correctly because the flow was interrupted.

#### Measurable Remediation Plan

1.  **Store Message Identifiers:** In the `MatchFoundView`, when it is first created, the `channel.id` and the `message.id` of the view **must** be captured and stored as instance attributes.
2.  **Create a Robust Update Method:** Implement a helper method that abstracts the logic of updating the message using the bot's global token, completely independent of the original interaction.
    ```python
    # Inside MatchFoundView or a similar class
    async def _edit_original_message(self, **kwargs):
        """Update the message using the stored channel and message IDs."""
        if not self.channel_id or not self.message_id:
            print("ERROR: channel_id or message_id not set, cannot update view.")
            return

        try:
            # Fetch the channel and message directly using the bot's credentials.
            channel = self.bot.get_channel(self.channel_id)
            if not channel:
                # Handle cases where channel is not cached (e.g., after restart)
                channel = await self.bot.fetch_channel(self.channel_id)
            
            message = await channel.fetch_message(self.message_id)
            await message.edit(**kwargs)
        except (discord.NotFound, discord.Forbidden) as e:
            print(f"Failed to update message via bot token: {e}")
    ```
3.  **Refactor Call Sites:** Replace all calls to `edit_original_response` that could happen after a long delay (e.g., in `on_message`, match completion handlers) with calls to the new `_edit_original_message` helper.
4.  **Measurement:** Create a unit test where you construct a `MatchFoundView`, manually set its `channel_id` and `message_id`, and then call a handler that uses `_edit_original_message`. Mock `bot.fetch_channel` and `channel.fetch_message` and assert that they are called with the correct IDs.

---

### 2.2. Data Consistency Between Memory and Database

-   **Claim:** The asynchronous write-back queue is volatile and will lose data on a service restart.
-   **Verdict:** **Confirmed.**

#### In-Depth Explanation

The current architecture uses an in-memory `asyncio.Queue` for pending database writes. This design successfully decouples the application logic from database latency but sacrifices durability.

**Failure Scenario:**
1.  A match completes. The `DataAccessService` is called to update the MMRs for both players and record the match result.
2.  The in-memory Polars DataFrames are updated instantly. The UI reflects the new MMRs.
3.  Three `WriteJob` objects (one for the match, two for MMR updates) are placed into the `asyncio.Queue`.
4.  Before the background worker task can process these jobs from the queue, the bot's process is terminated. This could be due to a crash, a manual restart, or a redeployment by the hosting provider (like Railway).
5.  **Result:** When the bot restarts, it reloads all its data from the persistent Supabase database. The three write jobs that were in the in-memory queue are gone forever. The database still contains the old MMR values and has no record of the match. The players' MMR has been silently rolled back, creating a permanent inconsistency between what the users saw and the official state of the ladder.

#### Measurable Remediation Plan (High-Performance, Non-Blocking)

This plan achieves durability without blocking the main `asyncio` event loop, avoiding the performance regressions seen in previous attempts.

1.  **Use an Async-Compatible SQLite Library:** The `sqlite3` standard library is synchronous and will block the event loop. Use `aiosqlite` to perform database operations asynchronously.
2.  **Implement a Persistent `WriteLog` Class:** Create a class to manage the SQLite-backed write-ahead log.
    ```python
    # In a new file, e.g., src/backend/core/write_log.py
    import aiosqlite
    
    class WriteLog:
        def __init__(self, db_path):
            self._db_path = db_path
            self._write_signal = asyncio.Event() # For push notifications
    
        async def initialize(self):
            # Connect and create table
            ...
    
        async def enqueue(self, job):
            # Use `to_thread` to ensure even file system metadata updates don't block
            await asyncio.to_thread(self._write_to_db, job)
            self._write_signal.set() # Signal the worker
    
        def _write_to_db(self, job):
            # Synchronous code to write to SQLite
            # This will run in a separate thread
            ...
    ```
3.  **Modify Enqueue Logic:** When a write operation is requested in `DataAccessService`, it will call `await self._write_log.enqueue(job)`. This is a non-blocking operation.
4.  **Implement Push-Based Worker Logic:** The `_db_writer_worker` will be event-driven, not polling-based. This is far more efficient.
    ```python
    # In DataAccessService._db_writer_worker
    async def _db_writer_worker(self):
        while not self._shutdown_event.is_set():
            await self._write_log._write_signal.wait() # Wait for a signal
            self._write_log._write_signal.clear()      # Reset the signal
            
            # Process all pending jobs
            pending_jobs = await self._write_log.get_pending_jobs()
            for job in pending_jobs:
                # ... process job, mark complete/failed in SQLite ...
    ```
5.  **Startup Recovery:** During `DataAccessService` initialization, it must check the `WriteLog` for any pending jobs from a previous run and process them *before* setting the write signal for the main worker loop. This ensures old jobs are cleared before new ones are accepted.
6.  **Measurement:**
    -   Create a test that enqueues several jobs.
    -   Use `psutil` or a similar library to verify that no new threads are being created for each write (verifying that `to_thread` is using a managed thread pool).
    -   In another test, enqueue a job, then immediately "crash" and restart the `DataAccessService` instance. Assert that the `_recover_pending_writes` method finds and processes the job from the first run.

---

### 2.3. Race Conditions in Match State Management

-   **Claim:** `match_completion_service.py` has a narrow lock scope, allowing race conditions.
-   **Verdict:** **Confirmed.**

#### In-Depth Explanation

The service monitors active matches and uses a lock to check their state. However, the lock is released before the terminal action (completing or aborting the match) is fully executed.

**Failure Scenario:**
1.  A match is in progress. The `_monitor_match_completion` task for this match runs.
2.  It acquires the lock for the match ID. Inside the lock, it reads the match data from the `DataAccessService` and sees that both players have reported the same result. It decides to complete the match.
3.  The lock is released. The monitor task proceeds to call `await self._handle_match_completion(match_id, match_data)`.
4.  Just after the lock is released, but *before* `_handle_match_completion` runs, one of the players clicks the "Abort" button.
5.  The abort request is processed by the `Matchmaker.abort_match` method, which updates the match state to "aborted" in the `DataAccessService`.
6.  Now, the `_handle_match_completion` coroutine finally runs. It calculates and applies MMR changes based on the `match_data` it read earlier, which showed a completed match.
7.  **Result:** The match is simultaneously marked as aborted *and* has its MMR calculated and applied. This is a logically inconsistent state that can lead to confusion and incorrect ladder rankings. The lock was ineffective because it only protected the "read and decide" phase, not the entire "read-decide-act" atomic transaction.

#### Measurable Remediation Plan

1.  **Introduce an Atomic State Field:** Add a `status` field to the in-memory match DataFrame (e.g., `'IN_PROGRESS'`, `'PROCESSING_COMPLETION'`, `'COMPLETE'`, `'ABORTED'`, `'CONFLICT'`). This is the single source of truth for a match's state.
2.  **Enforce Lock Acquisition for All State Transitions:** The `asyncio.Lock` for a given `match_id` must be acquired in **all** functions that can cause a terminal state transition. This includes:
    -   `check_match_completion()`
    -   `abort_match()` in `DataAccessService` (or the service that calls it)
    -   `record_match_result()` if it can trigger a completion/conflict directly.
3.  **Refactor State Transition Logic (Check-Then-Act Atomically):**
    ```python
    # In match_completion_service.check_match_completion
    lock = self._get_lock(match_id)
    async with lock:
        # Re-fetch data inside the lock to get the absolute latest state
        match_data = data_service.get_match(match_id)
        
        # Check 1: Is the match still in progress?
        if match_data.get('status') != 'IN_PROGRESS':
            # Another process (like an abort) already handled it. Do nothing.
            return 

        # Check 2: Do reports indicate completion?
        if reports_indicate_completion(match_data):
            # Set status to prevent other processes from interfering
            # This is the "Check-Then-Act" pattern
            data_service.update_match_status(match_id, 'PROCESSING_COMPLETION')
            
            # Now, perform the action. Since the status is updated, no other
            # process will try to act on this match.
            await self._handle_match_completion(match_id, match_data)
            data_service.update_match_status(match_id, 'COMPLETE')

        # ... other conditions for abort, conflict ...
    ```
4.  **Measurement:** Create an integration test that uses `asyncio.gather` to concurrently run a `check_match_completion` coroutine and an `abort_match` coroutine for the same match ID. Add logging to track which operation "wins" the lock and updates the state first. Assert that the final state of the match is unambiguous (either `'COMPLETE'` or `'ABORTED'`, but never both) and that the `update_match_status` method was called only once for the winning operation.

---

## 3. Architectural Fragilities & Other Issues Re-evaluation

-   **Input Validation Bypass:** **Confirmed.** The lack of Unicode normalization is a valid, if subtle, security concern.
-   **Resource Exhaustion in Process Pool:** **Confirmed.** The restart logic relies on `terminate()` and a `timeout`, with a broad `except Exception` that can hide critical failures, potentially leading to zombie processes.
-   **Memory Leak in DataFrame Operations:** **Disproven/Unlikely.** The claim that reassigning `self._rankings` will leak memory is weak. Standard Python garbage collection should handle the dereferenced dictionary and its associated DataFrame unless another part of the code is actively holding a reference to the old data, for which there is no evidence. This seems like a theoretical concern rather than a practical one.
-   **Tight Coupling Between Services:** **Confirmed.** The codebase consistently uses direct instantiation (`Service()`) instead of a dependency injection pattern, making services hard to test in isolation.
-   **Global State Management:** **Confirmed.** Multiple module-level dictionaries and manager instances are used for state, which is a fragile pattern prone to race conditions and difficult to reason about.
-   **Blocking Operations / Lack of Rate Limiting:** **Confirmed.** A review of the command structure and service methods shows a lack of universal rate-limiting and several areas where synchronous code could block the event loop.

---

## Conclusion

The initial code quality analysis holds up to critical scrutiny. The identified issues in singleton implementation, connection pool management, and async task lifecycle are not just theoretical but represent clear and present dangers to the bot's stability. The high-priority issues concerning data consistency and Discord API limitations are also confirmed.

While one medium-priority claim regarding DataFrame memory leaks was deemed unlikely, the overarching assessment is sound. The codebase is architecturally advanced in its performance design but fragile in its implementation of concurrency, state management, and error handling. The recommendations provided in the original document are therefore validated and should be prioritized.

---

## 8. Feasibility Analysis: Connection Pool Health Checks

The idea was proposed to run a connection pool health check every time a connection is used, similar to how the `ProcessPool` health is checked before parsing a replay. This section provides a detailed analysis of that proposal, its overhead, and a final recommendation.

### How the `ProcessPool` Health Check Works

The comparison to the `ProcessPool` is a good starting point. My investigation into `src/bot/bot_setup.py` and `src/bot/commands/queue_command.py` reveals key differences in *how* and *why* the check is performed:

1.  **Trigger:** The `_ensure_process_pool_healthy()` check is triggered **infrequently**, specifically only when a replay is uploaded and needs parsing. It does *not* run for every command or event.
2.  **Purpose:** Its purpose is to recover from **catastrophic worker death**. A worker process can be terminated by the OS or crash due to a memory error. The health check submits a trivial task to see if the workers are still alive and responsive. If not, it triggers a full restart of the entire pool.
3.  **Mechanism:** It uses `run_in_executor` to send a simple `_health_check_worker` function to a worker and waits for a reply.

This is fundamentally different from a database connection, which is a persistent TCP socket, not a process. The failure modes are different (network timeouts, database restarts, idle disconnects) and generally less catastrophic than a process dying.

### The Overhead of a "Check on Every Use" Health Check

A health check for a database connection is typically a "ping" query, like `SELECT 1;`. Let's analyze the overhead if we were to run this before *every single database operation*:

1.  **Network Round Trip:** Every `SELECT 1` is a full network round trip to the database server. If our database has 50ms of latency, that's an additional 50ms of blocking I/O added to every single query.
2.  **Architectural Contradiction:** The entire `DataAccessService` architecture is built to *avoid* database calls for reads and to make writes asynchronous. Mandating a synchronous, blocking "ping" before every async write operation would directly undermine this core design and re-introduce the very latency we worked so hard to eliminate.
3.  **High Frequency:** Unlike the process pool check, database writes can be frequent. A single match completion might generate 3-5 write jobs. Running a ping for each would add significant overhead.

**Conclusion:** A health check on *every use* is prohibitively expensive and architecturally unsound for our system.

### The Correct Approach: Check on Checkout (Pessimistic Pooling)

A much more standard and efficient pattern is called **"Check on Checkout"** or "pessimistic connection pooling."

-   **How it Works:** The health check (`SELECT 1`) is performed **only once**, when a connection is first borrowed from the pool via `pool.getconn()`.
-   **Benefits:**
    -   It guarantees that any connection handed to your application code is valid *at that moment*.
    -   The cost is paid only once per transaction/`with` block, not for every single statement inside it.
    -   It effectively prevents stale connections (due to network drops or DB restarts) from ever reaching your application logic.
-   **Overhead:** This is a very acceptable trade-off. It adds one small, quick round trip at the beginning of a database interaction in exchange for a massive increase in resilience.

### Recommendation

1.  **Primary Goal: Fix the Leak.** The highest priority remains fixing the faulty exception handling in `connection_pool.py` that causes connection leaks. Health checks are for handling *external* failures (like the network), not for mitigating internal application bugs.
2.  **Implement Check on Checkout:** After the leak is fixed, we should implement a "check on checkout" mechanism. The `psycopg2` connection pool we use (`SimpleConnectionPool`) does not have this built-in, so we would need to wrap the `getconn()` call.

#### Implementation Sketch:

```python
# In src/backend/db/connection_pool.py

def _ping_connection(conn) -> bool:
    """Check if a connection is alive."""
    try:
        # Use a cursor with a short timeout
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except psycopg2.Error:
        return False

@contextmanager
def get_connection():
    conn = None
    retry_count = 0
    max_retries = 3 # Try a few times to get a healthy connection

    while retry_count < max_retries:
        try:
            conn = _global_pool.getconn()
            if _ping_connection(conn):
                # Connection is healthy, proceed
                yield conn
                conn.commit()
                return # Exit the loop and context manager
            else:
                # Connection is dead, close it and try again
                print("[DB Pool] Discarding stale connection.")
                conn.close()
                conn = None
                retry_count += 1
        except Exception as e:
            # Handle other errors...
            raise
        finally:
            if conn:
                _global_pool.putconn(conn)

    raise ConnectionError("Failed to get a healthy database connection from the pool.")
```

This revised approach provides the resilience you're looking for by validating connections before use, but does so in a targeted, efficient manner that avoids the prohibitive overhead of checking on every single operation.