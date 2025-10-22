### **Phase 1: Architectural Vision & Core Principles**

Before writing any code, we establish the new principles:

1.  **Event-Driven, Not Polling-Based**: The frontend will **never** ask "is my match ready yet?". The backend will **tell** the frontend "your match is ready now". This eliminates all polling-related delays and inefficiencies.
2.  **Strict Decoupling**: The backend matchmaking logic will have **zero knowledge** of Discord. It will not know what a `discord.Interaction` or a "View" is. It will only deal with abstract `Player` data and publish generic "events".
3.  **Truly Non-Blocking**: The main bot process (the `asyncio` event loop) must remain responsive at all times. All CPU-intensive work (the matchmaking algorithm) and all I/O (database calls) will be offloaded from the main thread.
4.  **Centralized State Management**: The state of "who is in the queue" will be managed by a single, reliable service, preventing race conditions and inconsistencies.

### **Phase 2: The New Components**

We will introduce three new, distinct backend services and refactor the Discord-facing components.

#### **1. The `NotificationService`: The Nervous System**
*   **Purpose**: To provide a real-time, push-based communication channel from the backend to specific, listening frontend components. It's the core of our event-driven model.
*   **Location**: `src/backend/services/notification_service.py` (New File)
*   **Implementation**:
    *   It will manage a dictionary: `_player_listeners: Dict[int, asyncio.Queue]`. The key is a `player_discord_id`, and the value is a dedicated `asyncio.Queue` for that player.
    *   `async def subscribe(player_id: int) -> asyncio.Queue:`
        *   Creates a new `asyncio.Queue` for the player.
        *   Stores it in the `_player_listeners` dictionary.
        *   Returns the queue object to the caller (the player's `QueueSearchingView`).
    *   `async def unsubscribe(player_id: int):`
        *   Removes the player's queue from the dictionary to prevent memory leaks.
    *   `async def publish_match_found(match: MatchResult):`
        *   This is the entry point for the `MatchmakingService`.
        *   It will get the IDs for both players from the `match` object.
        *   For each player, it will look up their `asyncio.Queue` in the dictionary and `await queue.put(match)`. This instantly sends the match data to the waiting listener.

#### **2. The `QueueService`: The Gatekeeper**
*   **Purpose**: To be the single source of truth for the matchmaking queue's state. It handles the logic of players entering and leaving the queue.
*   **Location**: `src/backend/services/queue_service.py` (New File)
*   **Implementation**:
    *   Manages an in-memory dictionary: `_queued_players: Dict[int, Player]`.
    *   `async def add_player_to_queue(interaction: discord.Interaction) -> Player:`
        *   This is called by the frontend.
        *   It performs all initial setup: guard checks, creating the `Player` object, and importantly, making a **non-blocking database call** to fetch the player's MMRs.
        *   Once the `Player` object is fully hydrated with data, it's added to the `_queued_players` dictionary.
    *   `async def remove_player_from_queue(player_id: int):`
        *   Removes a player, typically called when a player cancels their queue.
    *   `def get_snapshot() -> List[Player]:`
        *   A **synchronous** method that returns a copy of the current players in the queue. This is what the matchmaking algorithm will consume.
    *   `async def remove_matched_players(player_ids: List[int]):`
        *   Called by the `MatchmakingService` *after* a match wave to efficiently remove all matched players from the queue.

#### **3. The `MatchmakingService`: The Brain (Heavily Refactored)**
*   **Purpose**: To contain the pure, CPU-intensive logic of finding matches, completely isolated from the event loop and Discord.
*   **Location**: `src/backend/services/matchmaking_service.py` (Refactored)
*   **Implementation**:
    *   The `Matchmaker.run()` loop will be changed dramatically.
    *   **Offloading the Algorithm**: Based on performance estimates (200-300ms), the overhead of a full process-pool executor is unnecessary. Instead, the matchmaking algorithm will remain in the main process, but all I/O within it will be made non-blocking.
    *   **The New `run()` Loop**:
        1.  The loop will sleep for its 45-second interval, keeping the event loop free for the majority of the time.
        2.  When it wakes, it will call a refactored `async def attempt_match()`.
        3.  Inside `attempt_match`, the **CPU-bound logic** (finding pairs) will run synchronously. This is an acceptable 200-300ms hitch.
        4.  The function will then iterate through the found pairs and perform all I/O **asynchronously**:
            *   `match_result = await db_writer.create_match_1v1(...)` (using the new async adapter).
            *   `await notification_service.publish_match_found(match_result)`.
        5.  This approach confines the blocking behavior to a short, predictable CPU burst, while all database and notification I/O is handled concurrently without stalling the main bot.

#### **4. The Database Layer: The Foundation (New Async Adapters)**
*   **Purpose**: To ensure all database I/O is non-blocking.
*   **Implementation**:
    *   We will use a library like `aiopg` (for PostgreSQL).
    *   A new `AsyncPostgresAdapter` will be created in `src/backend/db/adapters/`. This adapter will use `aiopg` to manage a connection pool and execute queries asynchronously.
    *   The `DatabaseReader` and `DatabaseWriter` will be refactored to have `async` methods (e.g., `async def get_player_mmr_1v1(...)`) that use the new async adapter. All database calls will now be `await`-ed.

#### **5. The Frontend: The User Experience (Refactored `queue_command.py`)**
*   **`QueueSearchingView` Rewrite**:
    *   The `__init__` will no longer create any polling tasks.
    *   It will instead `await notification_service.subscribe(player_id)` to get its personal notification queue.
    *   It will create a single background task: `self.listener_task = asyncio.create_task(self._listen_for_match())`.
*   **New Method: `async def _listen_for_match(self):`**
    *   This method contains a single `await` statement: `match_result = await self.notification_queue.get()`.
    *   The code execution will **pause** here indefinitely until the `NotificationService` `put`s a result into the queue.
    *   As soon as it gets a result, it will wake up instantly.
    *   The rest of the method will then create the `MatchFoundView`, update the Discord message, and `await notification_service.unsubscribe(player_id)` to clean up.
*   **Button Callbacks**:
    *   The `JoinQueueButton` will now call `await queue_service.add_player_to_queue(interaction)`.
    *   The `CancelQueueButton` will call `await queue_service.remove_player_from_queue(player_id)`, and it will also be responsible for `self.listener_task.cancel()` and calling `unsubscribe`.

---

### **Phase 3: The Implementation Roadmap**

This is a step-by-step guide to executing the rewrite on a dedicated `feature/matchmaking-rewrite` branch.

1.  **Step 1: Foundational Services.**
    *   Implement the `NotificationService`. Write unit tests to verify that subscribing, unsubscribing, and publishing events works as expected.
    *   Implement the `QueueService`. Write unit tests for adding, removing, and snapshotting players.

2.  **Step 2: Go Async on the Database.**
    *   Add `aiopg` to `requirements.txt`.
    *   Create the `AsyncPostgresAdapter`.
    *   Refactor `DatabaseReader` and `DatabaseWriter` to use this adapter and provide `async` methods for all database operations related to the queue flow (getting/setting MMR, creating matches, getting preferences).

3.  **Step 3: Isolate the Matchmaking Algorithm.**
    *   Refactor `MatchmakingService`. The `run()` loop and `attempt_match()` function will be rewritten to separate the synchronous, CPU-bound pairing logic from the asynchronous, I/O-bound database and notification calls, as detailed in Phase 2. This avoids unnecessary executor overhead while still unblocking the event loop for all I/O.
    *   Wire it up to call the `QueueService` for its input and the `NotificationService` for its output.

4.  **Step 4: Rewrite the Frontend.**
    *   This is the final piece. Rewrite the `QueueSearchingView` to use the new subscription-based notification model.
    *   Update all button interactions to call the new async services.
    *   Ensure all cleanup logic (unsubscribing, cancelling tasks) is correctly implemented to prevent memory leaks.

5.  **Step 5: Integration and End-to-End Testing.**
    *   Update `app_context.py` to initialize and provide the new global service instances.
    *   Manually test the full user journey:
        *   `/queue` -> Join -> Match Found.
        *   `/queue` -> Join -> Cancel.
        *   Multiple players joining at once.
        *   Test how the system responds to a match being found while a player is interacting with another part of the bot.
    *   Deploy to a staging environment for stress testing with multiple simulated users.

This plan is a significant undertaking, but it systematically replaces fragile, blocking, and tightly-coupled components with a modern, event-driven, and truly asynchronous architecture that will deliver the instantaneous and reliable experience your users expect.