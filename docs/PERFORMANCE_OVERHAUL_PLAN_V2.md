# Comprehensive Performance Overhaul Plan (V2 with Dependency Injection)

**Status**: 📝 DRAFT  
**Date**: October 20, 2025

---

## 1. Problem Diagnosis: The Root Cause of Latency

_(This analysis remains the same as the original plan)_

Despite recent query optimizations, the bot's response times remain unacceptably slow, frequently exceeding Discord's 3-second interaction timeout. The root cause is **high database connection overhead**, where a new, expensive remote connection is established for every single query.

A secondary issue is the on-demand instantiation of services (e.g., `LeaderboardService()`) within command handlers, which adds minor but unnecessary object creation overhead.

---

## 2. The Solution: Connection Pooling & True Dependency Injection

This plan will address the root causes of latency by implementing two key architectural improvements, transforming our data access and service layers for high performance, maintainability, and testability.

### Phase 1: Implement Database Connection Pooling (Critical)

We will integrate `psycopg2.pool` to create a managed pool of persistent connections to the PostgreSQL database.

**Key Tasks**:
1.  **Create a Centralized Pool Manager**:
    - A new module, `src/backend/db/connection_pool.py`, will be created to initialize and manage a `psycopg2.pool.SimpleConnectionPool`.

2.  **Refactor the `PostgreSQLAdapter`**:
    - The adapter's `get_connection` context manager will be rewritten to borrow and return connections from the global pool.

**Respecting Existing Abstractions**:
This change is a perfect example of honoring our existing abstractions. The `PostgreSQLAdapter` is the *only* part of the application that needs to know about the connection pool. From the perspective of the rest of the codebase (e.g., `DatabaseReader`, `DatabaseWriter`), the adapter's interface remains unchanged. We are improving the *internal implementation* of the adapter without altering its public contract, which is a core benefit of the adapter pattern.

**Expected Impact**:
- **90-95% reduction** in connection overhead for all database calls.
- Average per-query latency will drop from **~200ms** to **<50ms**.
- The vast majority of commands will execute well within the 3-second Discord timeout.

### Phase 2: Refactor to a Dependency Injection (DI) Model (High Priority)

To address the redundant object creation and improve architectural quality, we will refactor the system to use **Dependency Injection (DI)** instead of a Service Locator pattern. With DI, an object's dependencies are "injected" into it (e.g., passed as constructor arguments) rather than being imported from a global registry.

This creates a more transparent, testable, and loosely coupled architecture.

**Key Tasks**:
1.  **Centralize Service Instantiation**:
    - We will still create a single, global instance of each service (e.g., `user_info_service = UserInfoService()`). However, these instances will be created in a single "composition root"—the application's main entry point, `src/bot/interface/interface_main.py`.

2.  **Refactor Command Handlers into Classes**:
    - Each command file in `src/bot/interface/commands/` will be refactored. The stateless functions will be converted into methods of a dedicated command class.
    - The `__init__` constructor of each command class will explicitly declare its service dependencies as arguments.

    **Example: `profile_command.py` Refactor**
    ```python
    # BEFORE: A stateless function that imports global services
    from src.backend.services import user_info_service, command_guard_service
    async def profile_command(interaction):
        player_data = user_info_service.get_player(...)

    # AFTER: A class with injected dependencies
    class ProfileCommand:
        def __init__(self, user_info_service: UserInfoService, command_guard_service: CommandGuardService):
            self.user_info_service = user_info_service
            self.command_guard_service = command_guard_service

        async def handle(self, interaction):
            player_data = self.user_info_service.get_player(...)
    ```

3.  **Update the Composition Root (`interface_main.py`)**:
    - In `interface_main.py`, we will import the singleton services and the new command classes.
    - We will then **inject** the services into the command class constructors when registering the commands with the bot.

    **Example: `interface_main.py` Composition**
    ```python
    # 1. Import services and command classes
    from src.backend.services import user_info_service, command_guard_service
    from src.bot.interface.commands.profile_command import ProfileCommand

    # 2. Instantiate command handlers, injecting dependencies
    profile_command = ProfileCommand(
        user_info_service=user_info_service,
        command_guard_service=command_guard_service
    )

    # 3. Register the handler's method with the bot tree
    @bot.tree.command(name="profile", ...)
    async def profile(interaction):
        await profile_command.handle(interaction)
    ```

**Benefits of Dependency Injection**:
- **Explicit Dependencies**: A class's constructor signature is a clear contract of what it needs to function. There are no hidden global dependencies.
- **Superior Testability**: It is trivial to pass mock or fake services into a class's constructor during unit tests, allowing for true isolation.
- **Loose Coupling**: This pattern discourages complex, tangled dependencies and promotes a cleaner, more modular architecture that is easier to maintain and refactor.

---

## 3. Implementation & Validation Plan

| Phase | Task | File(s) to Modify | Priority |
| :--- | :--- | :--- | :--- |
| **1** | **Connection Pooling** | | **Critical** |
| | 1.1 Create `connection_pool.py` | `src/backend/db/connection_pool.py` (New) | Critical |
| | 1.2 Refactor `PostgreSQLAdapter` | `src/backend/db/adapters/postgresql_adapter.py`| Critical |
| | 1.3 Update startup test to use pool | `tests/backend/db/test_db_connection.py` | High |
| **2** | **Dependency Injection** | | **High** |
| | 2.1 Create singleton service instances | `src/backend/services/service_instances.py` | High |
| | 2.2 Refactor all command handlers to classes | `src/bot/interface/commands/*.py` | High |
| | 2.3 Inject dependencies at composition root | `src/bot/interface/interface_main.py` | High |
| | 2.4 Refactor service-to-service calls (DI) | `src/backend/services/*.py` | Medium |

### Validation & Testing Strategy
_(This remains the same as the original plan)_

- **Local Performance Measurement**: Use `time.time()` logging to measure performance gains.
- **Connection Monitoring**: Add logging to the connection pool to observe its behavior.
- **Regression Testing**: Execute a full suite of bot commands to ensure no functionality is broken.
- **Production Monitoring**: Monitor Supabase and Railway metrics post-deployment.

This revised overhaul will not only fix the performance bottlenecks but also significantly improve the architectural quality of the codebase, making it more robust and easier to maintain in the long run.
