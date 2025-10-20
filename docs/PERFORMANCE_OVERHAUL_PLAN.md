# Comprehensive Performance Overhaul Plan

**Status**: 📝 DRAFT  
**Date**: October 20, 2025

---

## 1. Problem Diagnosis: The Root Cause of Latency

Despite recent query optimizations (e.g., using native UPSERTs), the bot's response times remain unacceptably slow, frequently exceeding Discord's 3-second interaction timeout. Deferring interactions is a temporary workaround that only masks the underlying performance issues without solving them.

The root cause has been identified as **high database connection overhead**. Our current database adapter implementation establishes a new, expensive remote connection (involving a full TCP handshake, SSL negotiation, and PostgreSQL authentication) to Supabase for *every single database query*.

### Example: The `/profile` Command Flow

A typical `/profile` command execution involves two separate database calls: `get_player_by_discord_uid()` and `get_all_player_mmrs_1v1()`. The timeline for this operation looks like this:

1.  **Call `get_player_by_discord_uid()`**:
    - `DatabaseReader` is instantiated.
    - `PostgreSQLAdapter` is instantiated.
    - **`adapter.get_connection()` is called:**
        - A new TCP socket is opened to the Supabase server. (**~50-100ms**)
        - A full SSL handshake is performed. (**~50-100ms**)
        - The client authenticates with the PostgreSQL server. (**~50-100ms**)
    - The actual SQL query is executed. (**<50ms**)
    - The connection is closed.
    - **Total Time for Query 1: ~150-350ms**

2.  **Call `get_all_player_mmrs_1v1()`**:
    - The entire process is repeated, establishing a *second* brand-new connection.
    - **Total Time for Query 2: ~150-350ms**

**Conclusion**: For a simple command, **300-700ms** can be spent purely on connection overhead. This latency is the primary reason the bot feels sluggish and is the direct cause of interaction timeouts.

A secondary, less critical issue is the on-demand instantiation of services (e.g., `LeaderboardService()`) within command handlers, which adds minor but unnecessary object creation overhead to each command execution.

---

## 2. The Solution: Connection Pooling & Singleton Services

This plan will address the root causes of latency by implementing two key architectural improvements, transforming our data access and service layers for high performance.

### Phase 1: Implement Database Connection Pooling (Critical)

We will integrate `psycopg2.pool` to create and manage a pool of persistent connections to the PostgreSQL database. This pool is established once at bot startup. Subsequent queries will instantly borrow a warm, ready-to-use connection from the pool, eliminating the costly setup overhead.

**Key Tasks**:
1.  **Create a Centralized Pool Manager**:
    - A new module, `src/backend/db/connection_pool.py`, will be created.
    - This module will initialize a `psycopg2.pool.SimpleConnectionPool` upon its first import, effectively making it a singleton.
    - The pool will be configured using the `DATABASE_URL` and settings for minimum/maximum connections from `config.py`.

2.  **Refactor the `PostgreSQLAdapter`**:
    - The adapter's `get_connection` context manager will be rewritten. Instead of creating a new connection, it will:
        - Call `pool.getconn()` to borrow a connection from the global pool.
        - `yield` the connection for the query execution.
        - Call `pool.putconn(conn)` in a `finally` block to guarantee the connection is returned to the pool, even if errors occur.

**Expected Impact**:
- **90-95% reduction** in connection overhead for all database calls.
- Average per-query latency will drop from **~200ms** to **<50ms**.
- The `/profile` command execution time is projected to drop from ~500ms to **~100-150ms**.
- The vast majority of commands will execute well within the 3-second Discord timeout, making `defer()` the exception rather than the rule.

### Phase 2: Refactor Services to Singletons (High Priority)

We will ensure that all backend services are instantiated only once when the bot starts. This reduces object creation overhead, centralizes service management, and improves code maintainability.

**Key Tasks**:
1.  **Create a Central Service Registry**:
    - In `src/backend/services/__init__.py`, we will import all service classes (`LeaderboardService`, `UserInfoService`, etc.).
    - We will create a single, global instance of each service that can be imported throughout the application (e.g., `leaderboard_service = LeaderboardService()`).

2.  **Refactor Command Handlers**:
    - All command files in `src/bot/interface/commands/` will be updated.
    - Local instantiations like `user_service = UserInfoService()` will be removed.
    - They will be replaced with direct imports of the singleton instances: `from src.backend.services import user_service`.

**Expected Impact**:
- Eliminates redundant object creation on every command invocation.
- Enforces a consistent, stateful, and more efficient service architecture.
- Improves code clarity by decoupling service instantiation from the command logic.

---

## 3. Implementation & Validation Plan

This table outlines the concrete steps for implementing the overhaul.

| Phase | Task | File(s) to Modify | Priority |
| :--- | :--- | :--- | :--- |
| **1** | **Connection Pooling** | | **Critical** |
| | 1.1 Create `connection_pool.py` | `src/backend/db/connection_pool.py` (New) | Critical |
| | 1.2 Refactor `PostgreSQLAdapter` to use pool | `src/backend/db/adapters/postgresql_adapter.py`| Critical |
| | 1.3 Update startup test to use pool | `src/backend/db/test_connection_startup.py` | High |
| **2** | **Singleton Services** | | **High** |
| | 2.1 Create singleton service instances | `src/backend/services/__init__.py` | High |
| | 2.2 Refactor all command handlers | `src/bot/interface/commands/*.py` | High |
| | 2.3 Refactor service-to-service calls | `src/backend/services/*.py` | Medium |

### Validation & Testing Strategy

- **Local Performance Measurement**: We will add simple `time.time()` logging around critical command handlers before and after the changes to precisely measure the performance gains.
- **Connection Monitoring**: We will add logging to the connection pool module to observe connections being created, borrowed, and returned, confirming the pool is operating as expected.
- **Regression Testing**: Execute a full suite of bot commands (`/queue`, `/profile`, `/leaderboard`, `/setup`, etc.) locally with `DATABASE_TYPE=postgresql` to ensure no functionality has been broken.
- **Production Monitoring**: After deployment, we will closely monitor Supabase query performance metrics and Railway response time logs to confirm the improvements in a live environment.

This overhaul will fundamentally fix the performance bottlenecks, leading to a faster, more reliable bot and a significantly improved user experience.
