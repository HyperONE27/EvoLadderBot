# Plan: Transitioning to an In-Memory First Database Architecture

## 1. The Core Problem & Vision

Despite the current Polars caching in `LeaderboardService`, the application faces performance issues because:

1.  The cache is not the canonical source of truth; it has a TTL, and read operations can still fall back to the database, causing unpredictable latency.
2.  Critical, frequently accessed data points like `remaining_aborts` are fetched directly from the database in performance-critical paths (`MatchFoundView`), causing significant UI delays.
3.  Database write operations are synchronous, blocking the main application thread and impacting responsiveness, especially during match completion and replay processing.

**Vision:** We will evolve our architecture by creating a unified `DataAccessService`. This service will treat in-memory Polars DataFrames as the primary, canonical "database" for our hot tables (`players`, `mmrs_1v1`, `preferences_1v1`, `matches_1v1`, and `replays`). The physical database (Supabase) will act as a persistent, asynchronously updated backup. For any remaining "cold" tables or write-only operations, the service will handle them appropriately, providing a single, clean abstraction layer for all data access.

## 2. Implementation: The `DataAccessService` (Facade Pattern)

A new singleton service, `DataAccessService`, will be created at `src/backend/services/data_access_service.py`. This service will be the **sole manager and entry point for all application data**, acting as a Facade over our hybrid in-memory/database system.

### 2.1. Core Components

#### **A. Singleton Design & Initialization**
-   The service will be a singleton to ensure a single, consistent source of data.
-   At bot startup, it will perform a one-time bulk read from the `players`, `mmrs_1v1`, `preferences_1v1`, `matches_1v1`, and `replays` tables to populate its internal Polars DataFrames.
-   It will also encapsulate an instance of the `DatabaseReader` and `DatabaseWriter` to handle the initial load and background persistence tasks.

#### **B. Asynchronous Write-Back Queue**
-   An `asyncio.Queue` will be implemented within the service to handle all database write operations for the hot tables.
-   A dedicated background `asyncio` task (`_db_writer_worker`) will run continuously, processing jobs from the queue. Each job will contain the necessary information (e.g., table, data payload) for a database write.
-   This completely decouples application performance from database write latency. This queue will handle writes for both the hot tables and the write-only log tables (`player_action_logs`, `command_calls`).

### 2.2. Service API

#### **A. High-Performance Read API (Getters for Hot Data)**
These synchronous methods query the in-memory Polars DataFrames directly, guaranteeing sub-millisecond response times.

-   `get_player_info(discord_uid: int) -> Optional[Dict[str, Any]]`
-   `get_player_mmr(discord_uid: int, race: str) -> Optional[float]`
-   `get_all_player_mmrs(discord_uid: int) -> Dict[str, float]`
-   `get_remaining_aborts(discord_uid: int) -> int`
-   `get_preferences_1v1(discord_uid: int) -> Optional[Dict[str, Any]]`
-   `get_match_1v1(match_id: int) -> Optional[Dict[str, Any]]`
-   `get_player_matches_1v1(discord_uid: int, limit: int = 50) -> List[Dict[str, Any]]`
-   `get_replay_info(match_id: int) -> Optional[Dict[str, Any]]`
-   `get_leaderboard_dataframe() -> pl.DataFrame`

#### **B. Delegated Read API (Getters for Cold Data)**
For less critical data, the service will simply delegate the call to its internal `DatabaseReader` instance, providing a unified API.

-   `get_match_1v1(match_id: int) -> Optional[Dict[str, Any]]`
-   `get_player_matches_1v1(discord_uid: int, limit: int = 50) -> List[Dict[str, Any]]`
-   *(... and other methods from `DatabaseReader`)*

#### **C. Asynchronous Write API (Setters)**
These `async` methods provide an "instant" response while handling persistence in the background.

-   `update_player_mmr(...)`
-   `update_remaining_aborts(...)`
-   `create_or_update_player(...)`
-   `update_preferences_1v1(...)`
-   `create_match_1v1(...)`
-   `update_match_report(...)`
-   `insert_replay(...)`
-   `log_player_action(...)`
-   `insert_command_call(...)`

**Each `async` write method will:**
1.  **Instantly update the appropriate in-memory Polars DataFrame (if applicable).**
2.  **Enqueue the corresponding database write job** into the `asyncio.Queue`.

## 3. Codebase Refactoring Strategy

### 3.1. Phase 1: Service Implementation
-   Create `src/backend/services/data_access_service.py`.
-   Implement the singleton structure, Polars DataFrames for all hot tables, `asyncio.Queue`, and the background worker task.
-   Implement all getter and setter methods.

### 3.2. Phase 2: Targeted Refactoring
The entire application will be refactored to **only** use the `DataAccessService` for data needs, completely removing direct dependencies on `db_reader` and `db_writer`.

-   **`queue_command.py` (`MatchFoundView.get_embed` and `on_message`)**:
    -   All data fetches will be sourced from the `DataAccessService`.
-   **`user_info_service.py`**:
    -   Will be heavily refactored or deprecated, with its logic absorbed into the `DataAccessService`.
-   **`replay_service.py`**:
    -   Will be refactored to use the `DataAccessService`'s async write methods to prevent blocking during replay processing.
-   **`ranking_service.py`**:
    -   Will source its DataFrame from `DataAccessService.get_leaderboard_dataframe()`.
-   **`leaderboard_service.py`**:
    -   Will be deprecated or refactored into a thin, stateless formatting layer on top of data provided by the `DataAccessService`.

## 4. Addressing `MatchFoundView` Dropdown Slowness

The delay is caused by synchronous database writes in `replay_service.py`.

**Resolution Plan:**

1.  **Refactor `replay_service.store_upload_from_parsed_dict`** to use the non-blocking, async write methods of our new `DataAccessService`.
2.  **Result**: The `on_message` handler in `queue_command.py` will no longer be blocked by database I/O. After the replay is parsed, the call to `_update_dropdown_states()` will be near-instantaneous.

## 5. Future Scalability

This architecture is highly extensible. If other tables are identified as performance bottlenecks, they can be seamlessly "promoted" to hot tables within the `DataAccessService` by:
1.  Adding a new Polars DataFrame.
2.  Loading it at startup.
3.  Changing its getter methods to read from the DataFrame instead of delegating to the `DatabaseReader`.
The rest of the application will require **no changes**.
