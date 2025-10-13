# Concurrency Strategy: Multiprocessing vs. Multithreading for Replay Parsing

This document outlines the two primary strategies for handling the CPU-bound task of replay parsing without blocking the main application's event loop. It provides code examples, effort estimates, and a final recommendation tailored to the `EvoLadderBot` project.

## 1. The Core Problem

As identified in the `scaling_strategy.md`, our application has two distinct types of work:

1.  **I/O-Bound:** Most of the application's time is spent waiting for the network (Discord API, database). `asyncio` handles this perfectly.
2.  **CPU-Bound:** Replay parsing is a short but intense task that uses 100% of a CPU core. In a standard `asyncio` application, this task will **block the event loop**, making the entire bot unresponsive until it's complete.

The goal is to offload this CPU-bound work so the bot remains responsive at all times.

## 2. Solution 1: Multiprocessing (The Robust & Recommended Approach)

This approach runs the replay parsing code in a completely separate process, managed by the operating system. It's like having a dedicated "Back Office" for heavy lifting, ensuring the "Front Office" (the bot) is always available to talk to users.

This is the **"Stage 1: In-Process Worker"** solution from the scaling roadmap.

### How it Works

We use a `ProcessPoolExecutor`, which manages a pool of separate Python processes. The main `asyncio` event loop hands off the parsing job to this pool and `await`s the result without ever blocking itself.

**Code Example:**

Let's assume we have a `MatchCompletionService` that needs to parse a replay.

```python
# In a service like 'match_completion_service.py'
import asyncio
import time
from concurrent.futures import ProcessPoolExecutor

# This is our CPU-bound function that simulates parsing a replay
def parse_replay_blocking(replay_data: bytes) -> dict:
    """
    This function runs in a SEPARATE PROCESS.
    It simulates a CPU-intensive task that would normally block.
    """
    print("Worker Process: Starting replay parse...")
    time.sleep(2) # Simulates a 2-second parse time
    print("Worker Process: Parse complete.")
    return {"map_name": "Triton LE", "winner": "Player A"}

class MatchCompletionService:
    def __init__(self):
        # Create a pool of worker processes. The size can be tuned.
        # This should be created once and reused throughout the application's lifecycle.
        self.process_pool = ProcessPoolExecutor(max_workers=2)

    async def handle_replay_submission(self, replay_data: bytes):
        """
        This is the async method called by our bot.
        It offloads the blocking work to the process pool.
        """
        loop = asyncio.get_running_loop()
        print("Main Process: Received replay. Offloading to worker process...")

        # loop.run_in_executor hands the work to the pool and returns a future.
        # We await the future without blocking the main event loop.
        replay_info = await loop.run_in_executor(
            self.process_pool, parse_replay_blocking, replay_data
        )

        print(f"Main Process: Got result from worker: {replay_info}")
        # ... now we can continue with async operations, like writing to the DB
        await self.record_match_result(replay_info)

    async def record_match_result(self, info):
        print("Main Process: Writing match result to database...")
        await asyncio.sleep(0.1) # Simulate async DB call
        print("Main Process: Database write complete.")

```

### Analysis

*   **Scale:** This **completely solves the core scaling problem.** It allows the bot to handle dozens of concurrent I/O operations while a CPU core is busy parsing a replay. You can scale up by increasing the number of workers in the pool to utilize more CPU cores, directly addressing the bottleneck.
*   **Effort (Low-to-Medium):**
    *   **Compared to other features:** The effort is significantly **less than building a new user-facing feature** (like the multi-step `setup` command) but **more than a simple bug fix.**
    *   **Details:** It involves creating the `ProcessPoolExecutor` once when the application starts, and then changing a single function call to use `loop.run_in_executor`. The main complexity is ensuring that any data passed to or returned from the worker function is "pickleable" (serializable), which is true for basic types, `bytes`, and simple dicts. This is a well-understood and very common pattern in Python.

---

## 3. Solution 2: Multithreading (The Future / High-Efficiency Approach)

This approach runs the replay parsing code in a separate thread, but **within the same process**.

**CRITICAL CAVEAT:** In standard Python, this **DOES NOT** solve the problem for CPU-bound tasks because of the Global Interpreter Lock (GIL). All threads run in the same process and the GIL prevents more than one of them from executing Python bytecode at the same time. This solution is **only viable in a future "free-threaded" Python build (3.13+)** where the GIL is disabled.

### How it Would Work

The implementation code is nearly identical to the multiprocessing solution, which is one of its main attractions. We just swap `ProcessPoolExecutor` for `ThreadPoolExecutor`.

**Code Example (Hypothetical - for a GIL-less Python):**

```python
# In a service like 'match_completion_service.py' (in a free-threaded world)
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

# This is our CPU-bound function that simulates parsing a replay
def parse_replay_blocking(replay_data: bytes) -> dict:
    """
    This function runs in a SEPARATE THREAD in the SAME PROCESS.
    Without the GIL, this can run on another CPU core in parallel.
    """
    print("Worker Thread: Starting replay parse...")
    time.sleep(2) # Simulates a 2-second parse time
    print("Worker Thread: Parse complete.")
    return {"map_name": "Triton LE", "winner": "Player A"}

class MatchCompletionService:
    def __init__(self):
        # Create a pool of worker threads.
        self.thread_pool = ThreadPoolExecutor(max_workers=2)

    async def handle_replay_submission(self, replay_data: bytes):
        loop = asyncio.get_running_loop()
        print("Main Thread: Received replay. Offloading to worker thread...")

        # The call is identical, just using the ThreadPoolExecutor
        replay_info = await loop.run_in_executor(
            self.thread_pool, parse_replay_blocking, replay_data
        )

        print(f"Main Thread: Got result from worker: {replay_info}")
        await self.record_match_result(replay_info)

    async def record_match_result(self, info):
        print("Main Thread: Writing match result to database...")
        await asyncio.sleep(0.1) # Simulate async DB call
        print("Main Thread: Database write complete.")
```

### Analysis

*   **Scale:** In a free-threaded world, this also **completely solves the core scaling problem.** It's more memory-efficient and has lower startup overhead than multiprocessing, which could make it slightly faster in practice.
*   **Effort (Very Low Code, Very High Project Risk):**
    *   **Coding Effort:** The actual lines of code you need to write are minimal and almost identical to the multiprocessing solution. The effort is **very low.**
    *   **Project Effort & Risk:** The *total* effort required to make this work today is **extremely high.** It involves:
        1.  Switching your entire deployment to a non-standard, experimental Python build.
        2.  Auditing every single dependency (especially the PostgreSQL driver) for free-threading compatibility.
        3.  Debugging potential race conditions that were previously hidden by the GIL.
    *   This is far more effort and risk than any other single feature in the project.

## 4. Summary & Recommendation

| Aspect | Multiprocessing | Multithreading (GIL-less) |
| :--- | :--- | :--- |
| **Effort to Implement** | **Low-to-Medium.** A well-defined, safe change. | **Very High.** Requires new runtime and full dependency audit. |
| **Performance Overhead** | Higher (more memory, slower to start workers). | **Lower.** Very efficient. |
| **Resilience** | **Excellent.** Worker crash does not affect the bot. | **Poor.** Worker crash takes down the entire bot process. |
| **Current Viability** | **Excellent.** Works on any standard Python 3.7+. | **Experimental.** Requires Python 3.13+ and compatible libraries. |

**Final Recommendation:**

Implement **multiprocessing**.

It is a pragmatic, robust, and well-supported solution that perfectly addresses your scaling bottleneck *today*. It aligns directly with the strategy you've already laid out and carries minimal project risk.

View multithreading as a potential future optimization. Once the free-threaded Python ecosystem matures, you can refactor to a thread-based model to gain efficiency, but you should not consider it as a primary option for your initial scaled launch.

---

## 5. Detailed Implementation Plan: Multiprocessing

This section provides a step-by-step guide to implementing the `ProcessPoolExecutor` solution. It details the exact code changes required in the context of your existing application structure.

### Prerequisites

Before you begin, ensure the following are in place:

*   **Dependencies:** All required packages, especially `sc2reader`, must be installed. You can ensure this by running `pip install -r requirements.txt`.
*   **Environment Variables:** The implementation relies on a new environment variable, `WORKER_PROCESSES`, to control the size of the process pool. Make sure this is added to your `.env` and `.env.example` files.

### Step 1: Isolate the CPU-Bound Parsing Logic

**File:** `src/backend/services/replay_service.py`

**Goal:** The core of `sc2reader`'s parsing logic is synchronous and CPU-bound. We must isolate this logic in a top-level function that is not part of a class. This makes it easy for the `ProcessPoolExecutor` to import and run the function in a separate process.

**Required Changes:**

1.  Add new imports: `io` and `sc2reader`.
2.  Create a new, standalone function `parse_replay_data_blocking`. This function will take the raw `bytes` of a replay file as input.
3.  This function will be responsible for loading the replay using `sc2reader` and extracting the necessary information into a simple dictionary. Simple data types (strings, ints, dicts) are required so the result can be safely "pickled" and sent back to the main process.

```python:src/backend/services/replay_service.py
import os
from typing import Optional
import io
import sc2reader


def parse_replay_data_blocking(replay_bytes: bytes) -> dict:
    """
    Parses replay file data using sc2reader in a blocking, CPU-bound manner.
    This function is designed to be run in a separate process to avoid blocking
    the main application's event loop.

    Args:
        replay_bytes: The raw byte content of the .SC2Replay file.

    Returns:
        A dictionary containing key information about the replay, or an error dict.
    """
    try:
        replay = sc2reader.load_replay(io.BytesIO(replay_bytes), load_level=2)

        if len(replay.players) != 2:
            return {"error": f"Expected 2 players, but replay has {len(replay.players)}."}

        # Basic data extraction
        player1 = replay.players[0]
        player2 = replay.players[1]
        
        return {
            "error": None,
            "map_name": replay.map_name,
            "game_length_seconds": replay.game_length.seconds,
            "player1_name": player1.name,
            "player1_race": player1.play_race,
            "player2_name": player2.name,
            "player2_race": player2.play_race,
        }
    except Exception as e:
        # Catch any parsing errors from sc2reader
        return {"error": f"sc2reader failed to parse replay: {e}"}


class ReplayService:
    def __init__(self):
        # This class is not directly used in the new_code, but kept for context.
        # The actual parsing logic is now in parse_replay_data_blocking.
        pass

    async def record_match_result(self, info):
        print("Main Process: Writing match result to database...")
        await asyncio.sleep(0.1) # Simulate async DB call
        print("Main Process: Database write complete.")
```

### Step 2: Create and Manage the Global Process Pool

**File:** `src/bot/interface/interface_main.py`

**Goal:** We need to create a single, application-wide `ProcessPoolExecutor`. Creating a new process is expensive, so we create a pool of them once at startup and reuse them for every replay that needs parsing. We will also ensure the pool is shut down gracefully when the bot terminates.

**Required Changes:**

1.  Import `ProcessPoolExecutor` and `os`.
2.  In the `if __name__ == "__main__":` block, before `bot.run()`, read an environment variable to configure the number of worker processes.
3.  Create the `ProcessPoolExecutor` instance and attach it to the `bot` object, making it accessible to any part of the application that has the `bot` instance.
4.  Wrap the `bot.run()` call in a `try...finally` block to guarantee that `process_pool.shutdown()` is called, which cleanly closes the worker processes.

```python:src/bot/interface/interface_main.py
import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from concurrent.futures import ProcessPoolExecutor

# ... existing imports ...

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ... existing @bot.event decorators ...

def register_commands(bot: commands.Bot):
    # This function is not directly used in the new_code, but kept for context.
    # The actual command registration logic would go here.
    pass


if __name__ == "__main__":
    TOKEN = os.getenv("EVOLADDERBOT_TOKEN")

    # 1. Determine the number of worker processes from an env var
    # Defaults to 1 for safety, but 2-4 is a good starting point for a multi-core machine.
    worker_processes = int(os.getenv("WORKER_PROCESSES", "1"))
    
    # 2. Create the process pool
    process_pool = ProcessPoolExecutor(max_workers=worker_processes)
    
    # 3. Attach the pool to the bot instance for global access
    bot.process_pool = process_pool
    
    print(f"Initialized Process Pool with {worker_processes} worker(s).")
    
    try:
        # 4. Run the bot
        bot.run(TOKEN)
    finally:
        # 5. Ensure the process pool is shut down gracefully
        print("Shutting down process pool...")
        bot.process_pool.shutdown()
```

### Step 3: Offload Parsing in the Replay Handler

**File:** `src/bot/interface/commands/queue_command.py`

**Goal:** This is where we connect the pieces. The `on_message` event handler, which receives replay file uploads, will be modified to use the process pool instead of attempting to parse the file directly.

**Required Changes:**

1.  Import the new `parse_replay_data_blocking` function.
2.  Modify the `on_message` function (renamed from `handle_replay_message` for clarity) to accept the `bot` instance as an argument. This gives it access to `bot.process_pool`.
3.  After downloading the replay `bytes`, use `asyncio.get_running_loop().run_in_executor()` to hand off the parsing job to the pool.
4.  The `await` call will pause the `on_message` handler without blocking the rest of the bot, until the worker process returns the result.
5.  Update the `on_message` event in `interface_main.py` to pass the `bot` instance.

```python:src/bot/interface/commands/queue_command.py
import asyncio
from src.backend.services.replay_service import parse_replay_data_blocking

# ... existing code for register_queue_command ...

async def on_message(bot, message):
    """
    Handles replay file uploads in messages to active match channels.
    """
    # ... existing logic to find the relevant match view ...
    # if view is None:
    #     return

    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith('.sc2replay'):
                # ... existing logic to confirm the user is a player in the match ...

                await message.channel.send(f"Found replay file `{attachment.filename}`. Downloading and parsing now...")
                
                replay_bytes = await attachment.read()

                # --- NEW LOGIC ---
                # Get the current asyncio event loop
                loop = asyncio.get_running_loop()

                # Offload the blocking function to the process pool.
                # The 'await' here does NOT block the bot. It pauses this
                # function and lets the event loop run other tasks.
                try:
                    replay_info = await loop.run_in_executor(
                        bot.process_pool, parse_replay_data_blocking, replay_bytes
                    )
                except Exception as e:
                    # This will catch any exception from the worker process
                    print(f"FATAL: Replay parsing in worker process failed: {e}")
                    await message.channel.send(
                        ":x: A critical error occurred while parsing the replay. "
                        "The file may be corrupted. Please notify an admin."
                    )
                    return
                # --- END NEW LOGIC ---

                if replay_info.get("error"):
                    error_msg = replay_info["error"]
                    await message.channel.send(f":warning: Could not parse replay: {error_msg}")
                    return

                # You now have the replay data and can proceed with game logic
                await message.channel.send(
                    f"Successfully parsed replay!\n"
                    f"Map: `{replay_info['map_name']}`\n"
                    f"Players: `{replay_info['player1_name']}` vs `{replay_info['player2_name']}`"
                )

                # ... call view.handle_replay_submission(replay_info) or similar logic ...

```

**File:** `src/bot/interface/interface_main.py` (small change)

```python:src/bot/interface/interface_main.py
from src.bot.interface.commands.queue_command import register_queue_command, on_message as handle_replay_message

# ... existing code ...

@bot.event
async def on_message(message):
    """Handle replay file detection for active match views."""
    # Pass the bot instance to the handler
    await handle_replay_message(bot, message)

# ... existing code ...
```

### Step 4: Add Configuration

**File:** `.env.example` (and your local `.env` file)

**Goal:** Make the number of worker processes configurable without changing code.

**Required Changes:**

1.  Add a new line to your environment file to control the pool size.

```dotenv:.env.example
# Discord Bot Token
EVOLADDERBOT_TOKEN="your_token_here"

# Number of worker processes for CPU-bound tasks like replay parsing.
# A good starting point is the number of CPU cores on your machine, minus one.
WORKER_PROCESSES=2
```

This completes the implementation. With these changes, your bot will remain fully responsive while parsing replay files, addressing the core bottleneck identified in your scaling strategy.

### Implementation Flow Summary

To summarize, the new data flow for handling a replay file will be:

1.  A user uploads a replay to a match channel.
2.  The `on_message` handler in `queue_command.py` receives the message and downloads the attachment into a `bytes` object.
3.  The handler makes a non-blocking `await` call to `loop.run_in_executor()`, passing the `bytes` to the global `ProcessPoolExecutor`.
4.  The `ProcessPoolExecutor` puts the job into an internal queue.
5.  A free worker process from the pool picks up the job. This worker is a completely separate OS process.
6.  The worker process executes the `parse_replay_data_blocking` function, which runs the CPU-intensive `sc2reader` logic. The main bot's event loop is completely unaffected and continues to respond to other users.
7.  Once parsing is complete, the worker process returns the resulting `dict`.
8.  The `ProcessPoolExecutor` sends the result back to the main process.
9.  The `await` call in the `on_message` handler resolves, and the handler continues its execution with the parsed replay data.

---

## 6. Advanced Considerations & Architectural Tangents

The guide above provides the direct implementation path. However, for those looking to understand the deeper trade-offs and nuances, this section explores some relevant architectural tangents.

### Tangent 1: The Data Serialization (Pickling) Overhead

When you use `run_in_executor` with `ProcessPoolExecutor`, the data you pass to the worker function (`replay_bytes`) and the data you get back (`replay_info`) must be serialized and deserialized. Python's `pickle` module handles this automatically.

*   **How it Works:** Pickling converts your Python object (like a `dict`) into a byte stream. This byte stream is then sent from the main process to the worker process via an operating system pipe. The worker process receives the bytes, unpickles them back into a Python object, and then runs your function. The reverse happens with the return value.
*   **Performance Cost:** This process is not free. For small objects like the dictionary of replay info, the cost is negligible. However, if you were to send a multi-gigabyte object between processes, the serialization/deserialization time could become a new bottleneck.
*   **Relevance to You:** Your current implementation is optimal because you are sending raw `bytes` (which require minimal processing to be sent) and receiving a small, clean dictionary. This is a highly efficient use of this pattern. It's a key reason why the worker function should return a simple `dict` rather than a complex `sc2reader` object instance.

### Tangent 2: Graceful Error Handling in Worker Processes

What happens if a corrupted replay file causes `sc2reader` to raise an unhandled exception inside `parse_replay_data_blocking`?

The `ProcessPoolExecutor` is designed for this. The exception that occurred in the worker process is caught, pickled, and sent back to the main process. The `await loop.run_in_executor(...)` call will then **re-raise that exact exception** in your `on_message` handler.

This is incredibly useful for robust error handling. You can wrap the call in a `try...except` block to catch failures that happen in a completely separate process.

**Example: Making the `on_message` handler more robust:**

```python:src/bot/interface/commands/queue_command.py
# ... inside async def on_message(bot, message):
try:
    replay_info = await loop.run_in_executor(
        bot.process_pool, parse_replay_data_blocking, replay_bytes
    )
except Exception as e:
    # This will catch any exception from the worker process
    print(f"FATAL: Replay parsing in worker process failed: {e}")
    await message.channel.send(
        ":x: A critical error occurred while parsing the replay. "
        "The file may be corrupted. Please notify an admin."
    )
    return

if replay_info.get("error"):
# ... the rest of your logic ...
```

### Tangent 3: The "Poison Pill" Problem and Fault Isolation

The single biggest advantage of processes over threads is **fault isolation**. Imagine a user uploads a specific, uniquely malformed replay file (a "poison pill") that triggers a deep bug in `sc2reader`, causing the worker process to crash violently (e.g., a segmentation fault).

*   **With Threads:** A crash in a worker thread would terminate the **entire bot process**. If the user repeatedly uploaded the same file, they could repeatedly crash your bot.
*   **With Processes:** A crash in a worker process **only affects that worker.** The `ProcessPoolExecutor` will detect that the worker died, automatically spin up a new one to replace it, and the `await` in your main process will raise an exception (a `BrokenProcessPool` error). Your main bot process continues running, completely unharmed. It can log the error and inform the user, but it remains online to serve other requests.

This makes your application resilient against unforeseen bugs and malicious inputs.

### Tangent 4: Tuning Your Worker Pool (`max_workers`)

Choosing the right number of workers is a classic trade-off:

*   **For CPU-bound tasks (like yours):** The ideal number of workers is typically equal to the number of CPU cores available on the machine. Any more than that, and the processes will start competing with each other for CPU time, with the operating system spending extra effort on context switching between them, leading to diminishing returns. Setting it to `os.cpu_count()` is a common and effective strategy.
*   **For I/O-bound tasks:** If your workers were waiting for the network, you could have many more workers than CPU cores, as most of them would be idle at any given time.
*   **Memory Considerations:** Each worker process loads its own copy of the Python interpreter and any imported modules. `N` workers means roughly `N` times the base memory usage. If your application is memory-constrained, you might choose to have fewer workers than CPU cores.

For your deployment on Railway, starting with `WORKER_PROCESSES=2` is a safe and sensible choice. As you scale up your container size, you can increase this value to take advantage of the additional CPU resources you're paying for.

### Tangent 5: Centralized Process Pool Management & Service Architecture

A common question regarding this architecture is why the `ProcessPoolExecutor` is managed in the main application entry point (`interface_main.py`) rather than being encapsulated within a dedicated backend service class. This is a deliberate architectural choice that aligns with best practices for managing global resources.

*   **Why the Worker Function is Standalone:** The core requirement is that the *worker function* (`parse_replay_data_blocking`) must be a top-level function, not a method of a class. This is a limitation of Python's `multiprocessing` library, which needs to be able to pickle (serialize) the function to send it to the child process. Methods are harder to pickle reliably across process boundaries.

*   **Why the Manager is Centralized:** The `ProcessPoolExecutor` itself is the "manager" of the worker processes. Its lifecycle should be tied directly to the application's lifecycle. Creating it in the main entry point provides several advantages:
    1.  **Singleton Instance:** It guarantees there is only one process pool for the entire application, which is crucial for resource management.
    2.  **Clean Startup/Shutdown:** It allows for a clean `try...finally` block around `bot.run()`, ensuring the pool is always shut down gracefully when the bot terminates.
    3.  **Global Accessibility:** Attaching the pool to a central object (like the `bot` instance) makes this global resource available to any part of the application that needs it, without complex dependency injection.

This approach does not violate a service-oriented architecture. The "replay parsing service" is still logically contained within `replay_service.py` (where the worker function lives). The management of the execution context (`ProcessPoolExecutor`) is simply handled at the application's top level, which is the most robust place for it.

---

## 7. Alternative Approaches & The Road Ahead

### Why Not Just Use `asyncio.to_thread`?

You might see `asyncio.to_thread()` in modern Python code and wonder if it's a simpler option. It is simpler, but it is **not the right tool for this specific problem.**

*   `asyncio.to_thread()` uses a `ThreadPoolExecutor` under the hood. As we discussed in the Multithreading section, threads are still bound by the GIL.
*   **It is designed for offloading blocking I/O calls**, not CPU-bound work. For example, if you had to use a database library that didn't support `asyncio`, you would wrap your `db.query()` call in `asyncio.to_thread()` to prevent it from blocking the event loop while it waited for the network.
*   Using it for a CPU-bound task like replay parsing would still block the entire process due to the GIL, and you would see no benefit. Using `run_in_executor` with a `ProcessPoolExecutor` is the correct and necessary choice.

### The Path from `ProcessPoolExecutor` to Celery

This implementation is a perfect conceptual stepping stone to "Stage 2: The Decoupled System" from your scaling strategy. Think about the components we've built:

1.  A **Task Producer:** The `on_message` handler that submits a job (`replay_bytes`).
2.  A **Job Queue:** `ProcessPoolExecutor` has an internal, in-memory queue where it holds pending jobs.
3.  A **Task Consumer:** The worker process that pulls a job from the queue and executes `parse_replay_data_blocking`.

A distributed task queue system like **Celery with Redis** is a scaled-up, production-grade version of this exact pattern:

*   The **Job Queue** is no longer an in-memory queue inside your bot process, but an external, persistent message broker like Redis. This means if your bot restarts, pending jobs are not lost.
*   The **Task Consumers** are no longer local processes managed by an `Executor`, but completely separate services (e.g., a `worker` container on Railway). You can scale them independently—if replay parsing gets slow, you can just add more `worker` containers without touching your main `bot` container.

By implementing this `ProcessPoolExecutor` solution, you are learning the fundamental asynchronous workflow that underpins much larger, distributed systems.

---

## 8. Re-contextualizing for a 500-750 Concurrent User Peak

Your insight that the project will more realistically peak in the 500-750 concurrent user range is critical. This context allows us to refine the long-term roadmap and highlights just how effective the `ProcessPoolExecutor` solution is.

### The `ProcessPoolExecutor` Becomes Your Final Architecture

With a 1,000+ user target, the `ProcessPoolExecutor` is "Stage 1" on the path to a more complex system. With a 500-750 user target, it's very likely that **this becomes your permanent, final scaling architecture.**

Here’s why:

1.  **The Bottleneck is Per-Action, Not Global Load:** The fundamental problem we're solving—the event loop being blocked by a single replay parse—creates a terrible user experience even with just **10 concurrent users**. If one person uploads a replay, the bot becomes unresponsive for the other nine. Therefore, the `ProcessPoolExecutor` is non-negotiable for the quality of the service at any scale.

2.  **Throughput of a Tuned "Stage 1" System:** Let's analyze the load at your peak projection. At 750 concurrent users, with ~60% in-match, this might generate about 3-5 replay submissions per minute during peak times.
    *   A single worker process can parse a replay in ~100-200ms.
    *   A Railway container with 2 vCPUs and `WORKER_PROCESSES=2` could comfortably handle **several hundred replay submissions per minute** before the process pool's internal queue would even begin to fill up.
    *   This demonstrates that your `ProcessPoolExecutor` solution, running on a standard Railway plan, has more than enough throughput to handle the CPU-bound workload of your projected peak.

3.  **Avoiding Unnecessary Complexity:** The most significant implication of this refined user target is that you **can almost certainly avoid the massive complexity jump of "Stage 2" (Celery + Redis) entirely.** A distributed task queue is a powerful tool, but it introduces numerous new failure points, higher operational overhead, and increased costs.

**Conclusion:**

This more realistic target solidifies the `ProcessPoolExecutor` pattern as the perfect-fit solution for your project's entire lifecycle. It provides the exact decoupling you need to ensure a responsive user experience, has enough throughput to handle your generous peak estimates, and allows you to avoid the high-effort, high-complexity world of distributed systems.

You can confidently invest in this architecture, knowing it's not just a temporary fix, but a robust and complete solution for the scale you aim to achieve. This allows you to focus your valuable development time on what matters most: building features for your community.
