# Foreword: On Refactoring a "Fixer-Upper" vs. a "Condemned Building"

This document serves as a roadmap for improving the codebase. Before detailing the proposed changes, it's crucial to first assess the current state of the architecture. Not all repositories with "leaky abstractions" are created equal. The line between a challenging but manageable refactor and a project that requires a full rewrite is determined by its foundational structure.

This foreword distinguishes between these two states to illustrate why this codebase, despite its flaws, is a "Fixer-Upper" with good bones, making a methodical refactoring effort a worthwhile and achievable endeavor.

---

### The "Fixer-Upper" (This Project's Current State)

This repository has a solid foundational structure but suffers from messy implementation details—like a house with a strong frame but leaky plumbing. The high-level organization provides a clear map, which is what makes refactoring feel achievable.

**Key Characteristics:**

1.  **High-Level Separation of Concerns is Respected:**
    *   **What this looks like:** There is a clear, top-level distinction between the core logic and the presentation layer (`src/backend` vs. `src/bot`). This is the single most important structural decision that makes this repo salvageable.
    *   **Why it matters:** We can work on improving the `MatchmakingService` without having to touch Discord-specific code. The "leaky abstraction" is that the UI layer reaches *into* the backend and does too much, but the *boundary itself exists*.

2.  **Code is Organized by Domain, Not Just by Type:**
    *   **What this looks like:** We have `src/backend/services`, containing files with clear, domain-specific responsibilities (`mmr_service.py`, `replay_service.py`, `user_info_service.py`).
    *   **Why it matters:** Even if the code inside a service is imperfect, we know exactly where to find the logic for a specific domain. The cognitive load for finding code is low.

3.  **Data Access is Centralized:**
    *   **What this looks like:** We have `src/backend/db/db_reader_writer.py`. While a combined reader/writer class is itself a leaky abstraction, all the SQL queries are located *in one place*.
    *   **Why it matters:** To refactor the data layer (e.g., to SQLAlchemy), we have a single, well-defined target. We only need to fix the plumbing in one part of the house, not rip out pipes from every wall.

4.  **Clear Entry Points:**
    *   **What this looks like:** `src/bot/interface/interface_main.py` is the clear starting point for the bot. It's obvious how the application boots up and what high-level processes are started.
    *   **Why it matters:** We can trace the application's lifecycle from the beginning without having to uncover a "magic" startup process hidden in an obscure script.

---

### The "Condemned Building" (A Counter-Example of a Painfully Disorganized Repo)

This type of repository lacks a coherent structure. The foundational walls are in the wrong place or missing entirely. Refactoring is nearly impossible because every change has unpredictable, cascading effects.

**Key Characteristics:**

1.  **No High-Level Separation of Concerns:**
    *   **What it would look like:** A single, 5,000-line `bot.py` file that handles everything: Discord connection, command definitions, UI views, raw SQL queries, MMR calculations, and replay parsing.

2.  **"Miscellaneous" as a Core Design Principle:**
    *   **What it would look like:** The project would be full of generic files like `utils.py` and `helpers.py` containing hundreds of unrelated functions, creating a tangled web of dependencies.

3.  **Scattered and Inconsistent Data Access:**
    *   **What it would look like:** Instead of a central data access layer, every command file would create its own database connection, with raw SQL strings embedded directly inside UI callbacks.

4.  **Heavy Reliance on Global State:**
    *   **What it would look like:** Critical information (like the matchmaking queue) would be stored in a global dictionary, modified directly by different commands and background tasks, leading to race conditions and untestable code.

---

Because this codebase aligns with the "Fixer-Upper" model, the following architectural improvements can be implemented methodically to address the "leaky plumbing" without demolishing the strong foundation.

# Architectural Improvements Roadmap

This document provides a high-level overview of potential architectural improvements for the codebase. These changes are not directly related to performance or scaling but are focused on improving the overall quality, maintainability, testability, and robustness of the code. The proposals range from immediate quality-of-life changes to long-term strategic shifts.

---

## 1. Dependency Injection and Inversion of Control

### Problem
Currently, services instantiate their dependencies directly. This pattern, known as **tight coupling**, makes the system rigid. For example, `MatchmakingService` creates its own instances of `DatabaseWriter`, `MapsService`, and other services.

**Before:**
```python
# In src/backend/services/matchmaking_service.py
from src.backend.db.db_reader_writer import DatabaseWriter
from src.backend.services.maps_service import MapsService

class MatchmakingService:
    def __init__(self):
        # Direct instantiation creates hard dependencies
        self.db_writer = DatabaseWriter()
        self.maps_service = MapsService()
        # ... and so on for other services

    def _get_available_maps(self, p1: Player, p2: Player) -> List[str]:
        # This method is directly tied to the MapsService implementation
        all_maps = self.maps_service.get_available_maps()
        # ...
```
This makes testing `MatchmakingService` in isolation extremely difficult. To test `_get_available_maps`, you are forced to also test the real `MapsService` and, by extension, its dependencies. You cannot easily substitute a mock `MapsService` that returns a predictable list of maps for the test.

### Solution
Introduce a centralized **Dependency Injection (DI) container** using a library like `dependency-injector`. The container is responsible for creating and managing the lifecycle of all services. Services declare their dependencies in their constructor, and the container provides them. This is known as **Inversion of Control (IoC)**.

**After:**
```python
# In a new central file, e.g., src/backend/container.py
from dependency_injector import containers, providers
from src.backend.db.db_reader_writer import DatabaseWriter
from src.backend.services import MapsService, MatchmakingService, ...

class Container(containers.DeclarativeContainer):
    # Configuration provider would go here

    # Singleton services that should have one instance per application run
    db_writer = providers.Singleton(DatabaseWriter)
    maps_service = providers.Singleton(MapsService)
    
    # Factory services are created on each request
    matchmaking_service = providers.Factory(
        MatchmakingService,
        db_writer=db_writer,
        maps_service=maps_service,
    )

# In src/backend/services/matchmaking_service.py
class MatchmakingService:
    # Dependencies are now explicit contracts defined in the constructor
    def __init__(self, db_writer: DatabaseWriter, maps_service: MapsService):
        self.db_writer = db_writer
        self.maps_service = maps_service
```

**Benefits:**
- **Decoupling**: Services no longer know how to create their dependencies. They only know what they need.
- **Enhanced Testability**: In tests, you can easily inject mock dependencies.
  ```python
  # In a test file
  mock_maps_service = MockMapsService()
  # You can now test MatchmakingService without a real MapsService
  matchmaking_service = MatchmakingService(db_writer=mock_db, maps_service=mock_maps_service)
  ```
- **Flexibility & Maintainability**: Swapping out an implementation (e.g., a different database writer) only requires changing the container configuration in one place.
- **Clearer Dependencies**: A service's `__init__` signature clearly documents all its dependencies.

---

## 2. Centralized Configuration Management

### Problem
Configuration values (e.g., MMR constants, file paths, external tokens, bot settings) are scattered throughout the codebase, often as hardcoded "magic numbers" or strings.
- `MMRService._K_FACTOR: int = 40`
- `MatchmakingService.ABORT_TIMER_SECONDS: int = 300`
- `REPLAYS_DIR = os.path.join("data", "replays")` in `replay_service.py`

This makes configuration difficult to track and modify, and requires code changes for what should be simple environment adjustments.

### Solution
Create a dedicated `ConfigService`, potentially powered by a library like `Pydantic`, that is the **single source of truth** for all configuration. This service would load settings from a hierarchy of sources (e.g., `.env` file for development, environment variables for production) and provide validated, type-hinted configuration to the rest of the application via the DI container.

**Benefits:**
- **Centralization**: All configuration is defined and documented in one place.
- **Environment Management**: Easily manage different configurations for development and production without code changes.
- **Security**: Sensitive keys and tokens are kept out of source code and managed via environment variables.
- **Validation**: `Pydantic` can validate that required settings are present and of the correct type on startup, preventing runtime errors.

---

## 3. Stricter Separation of Concerns & Asymmetrical Coupling

### Problem
Components in the UI layer (`src/bot`), particularly `queue_command.py`, contain significant business logic. This includes direct database calls, complex state management, and orchestration of multiple backend services. This violates the principle of separation of concerns.

However, it is crucial to note the **asymmetrical nature of the coupling**:
- **The Good**: The `backend` is almost completely unaware of the `bot`. It does not import any Discord-specific modules or UI components. This is a major architectural strength.
- **The Bad**: The `bot` is deeply aware of the `backend`'s internal workings, reaching into its services and even the database layer directly.

This one-way dependency from `bot` -> `backend` is far better than a tangled, bi-directional dependency. It means we can refactor the entire backend, and as long as we update the calling methods in the bot, the system will work. The core logic is reusable.

For example, the `MatchResultSelect.callback` in `queue_command.py` is responsible for:
1.  Parsing the user's selection.
2.  Calling `db_writer.update_player_report_1v1`.
3.  Calling `match_completion_service.check_match_completion`.
4.  Fetching fresh data from `db_reader`.
5.  Calculating new MMRs and determining winner/loser display logic.
6.  Updating the state of multiple UI components.
7.  Sending the final notification embed.

This is far too much responsibility for a UI callback.

### Solution
Refactor the UI layer to be as "dumb" as possible. All business logic should be moved into the appropriate backend services. The UI layer should only:
1.  Receive user input (e.g., `interaction`, `selection`).
2.  Call a **single, high-level method** on a backend service.
3.  Display the result (e.g., an embed, view, or message) returned by that service.

**After:**
The `MatchResultSelect.callback` would be simplified to:
```python
# In queue_command.py
class MatchResultSelect(discord.ui.Select):
    async def callback(self, interaction: discord.Interaction):
        # 1. Receive input
        reported_winner = self.values[0]
        
        # 2. Call a single backend method
        result_view_model = self.match_completion_service.process_match_report(
            match_id=self.match_result.match_id,
            reporting_player_id=interaction.user.id,
            winner=reported_winner
        )

        # 3. Display the result
        await interaction.response.edit_message(
            embed=result_view_model.embed, 
            view=result_view_model.view
        )
```
The new `process_match_report` method in `MatchCompletionService` would contain all the orchestration logic that was previously in the UI.

**Benefits:**
- **Maintainability**: The code is vastly easier to understand. UI is for display, services are for logic.
- **Reusability**: The `process_match_report` logic could be reused by an admin command or a future web UI without any changes.
- **Testability**: The entire match completion flow can be tested by calling one service method, completely independent of Discord.

---

## 4. Formalized Error Handling Strategy

### Problem
Error handling is often done with broad `try...except Exception` blocks, which can hide bugs and make debugging difficult. When an error occurs, we often lack the context to give the user a helpful response.

### Solution
Define a set of custom exception classes for the application domain and implement a global error handler for the bot.

**1. Custom Exception Hierarchy:**
```python
class EvoLadderException(Exception):
    """Base exception for the application."""
    pass

class PlayerNotFoundError(EvoLadderException):
    """Raised when a player cannot be found in the database."""
    pass

class MatchConflictError(EvoLadderException):
    """Raised when player reports for a match conflict."""
    pass

class ReplayParseError(EvoLadderException):
    """Raised when a replay file is invalid."""
    pass
```

**2. Global Error Handler:**
The `bot.tree` can have a global error handler that catches these specific exceptions and translates them into user-friendly messages.
```python
# in interface_main.py
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    cause = error.__cause__ # The original exception
    if isinstance(cause, PlayerNotFoundError):
        await interaction.response.send_message("Error: Could not find your player profile. Have you run /setup?", ephemeral=True)
    elif isinstance(cause, MatchConflictError):
        await interaction.response.send_message("Error: Your match report conflicts with your opponent's. An admin will review it.", ephemeral=True)
    else:
        # Log the full error for debugging
        print(f"An unhandled error occurred: {error}")
        await interaction.response.send_message("An unexpected error occurred. Please try again later.", ephemeral=True)
```
Services would then raise these specific exceptions instead of returning `None` or `False`.

**Benefits:**
- **Clarity & Robustness**: The code explicitly states what can go wrong and allows for granular error handling.
- **Better User Experience**: Specific errors are translated into helpful, user-facing messages.
- **Improved Debugging**: Unhandled exceptions are still caught and logged by the default case.

---

## 5. Database Abstraction and the Repository Pattern

### Problem
The `db_reader_writer.py` module uses raw, multi-line SQL strings and acts as a monolithic data access layer for all domains (players, matches, replays, etc.). This violates the Single Responsibility Principle and couples the entire application to the specific database schema and SQLite's SQL dialect.

### Solution
Introduce a database abstraction layer like **SQLAlchemy Core** and refactor the data access layer into domain-specific **Repositories**.

**1. Adopt an Abstraction:** Replace raw SQL with a tool that allows for Pythonic query building.

**2. Implement the Repository Pattern:** Split `db_reader_writer.py` into multiple, focused classes.
- `PlayerRepository`: Handles all database operations related to the `players` and `mmrs_1v1` tables.
- `MatchRepository`: Handles all operations for the `matches_1v1` table.
- `ReplayRepository`: Handles all operations for the `replays` table.

Each repository would expose high-level, domain-specific methods like `get_player_by_discord_id()` or `update_match_result()`, hiding the underlying SQLAlchemy (or raw SQL) implementation.

**Benefits:**
- **Single Responsibility**: Each repository has one clear purpose, making them easier to manage.
- **Type Safety & Autocompletion**: Errors from typos in column names are caught by linters and IDEs.
- **Maintainability**: When changing match-related logic, you only need to touch the `MatchRepository`.
- **Database Agnosticism**: SQLAlchemy makes it much easier to switch from SQLite to PostgreSQL in the future.

---

## 6. Event-Driven Architecture

### Problem
Services are tightly, synchronously coupled. When a match is completed, the `MatchCompletionService` directly calls the `MMRService`, which directly calls the `DatabaseWriter`. If, in the future, we also want to update leaderboards, post to a "match results" channel, and update player stats, `MatchCompletionService` would need to be modified to call all those new services, increasing its complexity and violating the Single Responsibility Principle.

### Solution
Implement an **event-driven architecture** using a simple, in-memory event bus. Services would emit events, and other services would subscribe to them without knowing about each other.

**Example Flow:**
1.  `MatchCompletionService` finishes its work and emits a `MatchCompletedEvent` containing the match data.
2.  The `MMRService` is subscribed to this event. When it receives the event, it calculates the new MMRs and writes them to the database.
3.  A separate `LeaderboardService` is also subscribed. It updates the leaderboard rankings based on the event data.
4.  A `NotificationService` listens and sends a message to the public match results channel.

`MatchCompletionService` does not know or care that these other services exist. It just announces that a match is complete.

**Benefits:**
- **Extreme Decoupling**: Services are completely independent. You can add new functionality in response to an event without ever touching the service that emits it.
- **Scalability and Extensibility**: It's incredibly easy to add new features that react to existing events.
- **Improved Resilience**: An error in one event subscriber (like the `NotificationService`) does not an error in another (like the `MMRService`).

---

## 7. Comprehensive Testing Strategy

### Problem
The current testing strategy is not clearly defined. While some tests exist, coverage is inconsistent, and there isn't a clear distinction between different types of tests.

### Solution
Formalize the testing strategy into a **"Testing Pyramid"**:

- **Level 1: Unit Tests (Fast & Numerous)**:
  - **Goal**: Test individual functions and classes in complete isolation.
  - **Example**: Testing `MMRService.calculate_new_mmr` with specific MMR inputs and results.
  - **Requires**: Heavy use of mocking and the DI container to inject mock dependencies.

- **Level 2: Integration Tests (Slower & Fewer)**:
  - **Goal**: Test the interaction between services and with external systems like the database.
  - **Example**: An integration test for `MatchCompletionService.process_match_report` would use a real (but temporary/test) database to verify that after the service call, the correct rows in the `matches_1v1` and `mmrs_1v1` tables have been updated.
  - **Requires**: A testing database that can be created and torn down for each test run.

- **Level 3: End-to-End (E2E) Tests (Slowest & Rarest)**:
  - **Goal**: Test a full user flow from the user's perspective.
  - **Example**: A test that simulates a user invoking the `/queue` command, receiving a match, reporting a result, and verifying that the final Discord embed contains the correct MMR update.
  - **Requires**: A dedicated testing Discord bot and guild, and a framework for programmatic control of Discord commands and message validation.

**Benefits:**
- **Confidence**: A balanced test suite gives high confidence that new changes do not break existing functionality.
- **Documentation**: Well-written tests serve as executable documentation for how components are intended to be used.
- **Faster Debugging**: When a test fails, it pinpoints the location of the error far more quickly than manual testing.

---

## 8. Code Quality and Consistency

### Problem
While the code is functional, it lacks a consistent, automatically enforced standard for style, formatting, and type safety. This leads to variability in code style, which can increase the cognitive load of reading and maintaining the code.

### Solution
Adopt a suite of industry-standard tools to automate code quality checks. This should be integrated into the development workflow and CI/CD pipeline.

**1. Automated Formatting with `Black` and `isort`:**
- **`Black`**: An opinionated code formatter that ensures a consistent style across the entire codebase. This eliminates all debates about formatting.
- **`isort`**: Automatically sorts and organizes import statements.

**2. Strict Linting and Static Analysis with `Flake8` and `Mypy`:**
- **`Flake8`**: A linter that checks for common code smells, style guide violations (PEP 8), and logical errors.
- **`Mypy`**: A static type checker. The project should aim for a strict `mypy` configuration, ensuring all functions are fully type-hinted. This effectively turns Python into a statically-typed language, catching a huge class of bugs before the code is ever run.

**Benefits:**
- **Improved Readability**: Consistent code is easier to read and understand.
- **Fewer Bugs**: Static analysis and strict typing catch errors that would otherwise only appear at runtime.
- **Automated Reviews**: The tools automate the "nitpicky" parts of code review, allowing developers to focus on the logic.

---

## Conclusion

The proposals in this document form a comprehensive roadmap for evolving the codebase from a functional prototype to a robust, maintainable, and high-quality application. While the current structure has a solid foundation (the "good bones"), implementing these changes will fix the "leaky plumbing" and provide a stable and scalable architecture for future development. These are not just cosmetic changes; they are strategic investments in the long-term health of the project.
