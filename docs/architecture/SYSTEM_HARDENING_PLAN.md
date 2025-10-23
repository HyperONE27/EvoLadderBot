# System Quality and Hardening Plan

This document provides a critical assessment of the current state of the EvoLadderBot codebase following the implementation of fixes from `big_plan.md` Parts 1 and 2. It identifies remaining gaps and deficiencies and outlines a concrete, expanded plan for the architectural hardening items listed in Part 3.

## 1. System Quality Assessment & Identified Gaps

The recent fixes have significantly improved the bot's resilience, particularly regarding race conditions and data durability. However, a skeptical audit reveals several areas that still lack the robustness required for a production system.

### 1.1. Deficient Exception Handling

**Finding:** The codebase is replete with broad `except Exception` clauses. This practice is dangerous as it catches and hides all types of errors, including programming bugs (`TypeError`, `AttributeError`), unexpected system states, and critical signals, treating them all as generic, recoverable failures. This leads to silent failures and makes debugging extremely difficult.

**Gap:** The system lacks a coherent error handling strategy. There is no distinction between transient errors (which might be retried), fatal errors (which should crash the service), and validation errors (which should be reported to the user).

### 1.2. Inadequate Observability (Logging)

**Finding:** The vast majority of the application uses `print()` for output. This provides no structured information, no log levels (INFO, WARNING, ERROR), no timestamps, and no context about where the log originated.

**Gap:** It is nearly impossible to effectively debug a live instance of the bot. There is no way to filter logs by severity, correlate events across different services, or trace the lifecycle of a specific request (e.g., a single matchmaking flow).

### 1.3. SQLite `WriteLog` Hardening

**Finding:** The `WriteLog` implementation is functionally correct for the "happy path" but lacks hardening against common operational issues.

**Gaps:**
1.  **Concurrency Bottlenecks:** Opening a new database connection for every operation is inefficient and can cause `database is locked` errors under concurrent access from the main thread and the writer thread.
2.  **Missing WAL Mode:** The database is not configured for SQLite's WAL (Write-Ahead Logging) mode, which is the standard for improving read-write concurrency.
3.  **Silent Failures:** There is no handling for disk I/O errors (e.g., volume full). An `enqueue` operation would fail, and the application would crash without a clear indication of the root cause.

### 1.4. Brittle State Management in Discord Views

**Finding:** While the `QueueSearchingView` memory leak was addressed, the general pattern of managing complex, long-running state within a `discord.ui.View` remains fragile. The view object itself is often the sole manager of background tasks and state, making it difficult to recover or inspect state if the bot restarts.

**Gap:** There is no centralized, persistent "session" management for user interactions. For example, if the bot restarts while a match is in progress, the `MatchFoundView` objects are lost, and the bot has no way to resume interaction with those users for that match. The state exists only in the `DataAccessService`'s dataframes, not in the interactive layer.

### 1.5. Missing Input Sanitization and Normalization

**Finding:** Player-supplied strings (`player_name`, `battletag`) are passed directly into the database and UI components without any sanitization or normalization.

**Gap:** This creates a risk of data integrity issues. A user could register a name with non-standard Unicode characters that visually impersonates another user. It could also lead to broken UI layouts if the characters are not rendered as expected in Discord's fixed-width code blocks.

---

## 2. Phase 3 Hardening & Future Work

This section expands on the architectural fragilities from `big_plan.md` Part 3, providing concrete action plans.

### 2.1. Implement Granular & Hierarchical Exception Handling

**Goal:** Replace all broad `except Exception` clauses with specific, meaningful error handling. Establish a clear hierarchy of application-specific exceptions and consolidate existing ones.

**Plan:**
1.  **Define a Base Exception:** Create a base exception class in a new file, `src/backend/core/exceptions.py`.
    ```python
    class EvoLadderError(Exception):
        """Base exception for all application-specific errors."""
        pass
    ```
2.  **Create Specific Subclasses:** Define subclasses for different error categories within `exceptions.py`.
    ```python
    class DatabaseError(EvoLadderError):
        """For errors related to database operations."""
        pass

    class MatchmakingError(EvoLadderError):
        """For errors during the matchmaking process."""
        pass
    
    class CommandGuardError(EvoLadderError):
        """For errors related to command permissions or conditions."""
        pass
    # ... and others like ConfigurationError, ReplayParsingError, etc.
    ```
3.  **Systematic Refactoring:**
    -   **Consolidate:** Move existing custom exception definitions (like the one in `command_guard_service.py`) into the new central `exceptions.py` file, making them subclass the new base `EvoLadderError`.
    -   **Replace:** Go through the codebase file by file, starting with the most critical modules (`data_access_service.py`, `db_reader_writer.py`, `queue_command.py`).
    -   Replace each `except Exception:` with one or more specific `except` blocks (e.g., `except psycopg2.OperationalError:`, `except KeyError:`).
    -   When appropriate, catch a specific library exception and re-raise it as one of the new application-specific exceptions to provide more context (e.g., `except psycopg2.Error as e: raise DatabaseError(f"Failed to write MMR update: {e}")`).
    -   Only use `except Exception:` at the highest level of a thread or task's entry point, where its only purpose is to log the fatal error before allowing the thread to terminate.

### 2.2. Overhaul Configuration Management

**Goal:** Eliminate all hardcoded values (magic strings, numbers, timeouts) from the application logic and move them into a centralized, type-safe configuration system.

**Plan:**
1.  **Adopt a Configuration Library:** Integrate a library like `Pydantic` with `pydantic-settings` to manage configuration from environment variables and provide type validation.
2.  **Create a `Settings` Model:** In `src/bot/config.py`, define a Pydantic model for all configuration variables.
    ```python
    from pydantic_settings import BaseSettings

    class BotSettings(BaseSettings):
        DATABASE_URL: str
        GLOBAL_TIMEOUT: int = 300
        # ... other settings ...

    # Create a single, globally accessible settings instance
    settings = BotSettings()
    ```
3.  **Refactor Codebase:**
    -   Search the codebase for hardcoded literals (e.g., `timeout=300`, status strings like `'IN_PROGRESS'`).
    -   Replace literals with references to the `settings` object (e.g., `timeout=settings.GLOBAL_TIMEOUT`).
    -   For status strings and other "magic" values, convert them to `Enum` types and store them in `src/backend/types/`.

### 2.3. Implement Structured, Leveled, and Contextual Logging

**Goal:** Replace all `print()` statements with a modern, structured logging framework to provide deep observability into the bot's behavior.

**Plan:**
1.  **Configure `logging` Module:** In `bot_setup.py`, configure the root logger to output structured logs (e.g., JSON) using a library like `structlog` or a custom JSON formatter.
2.  **Establish Logging Best Practices:**
    -   Every module should get its own logger instance: `logger = logging.getLogger(__name__)`.
    -   Use appropriate log levels:
        -   `logger.info()`: For routine events (e.g., "User joined queue").
        -   `logger.warning()`: For recoverable issues or potential problems (e.g., "Discord API is slow to respond").
        -   `logger.error()`: For errors that are handled but represent a failure (e.g., "Failed to process replay file").
        -   `logger.exception()`: Inside an `except` block to automatically include the stack trace.
        -   `logger.debug()`: For verbose, developer-focused information.
3.  **Add Context to Logs:** When logging, include relevant context like `user_id`, `match_id`, `guild_id`, etc. This allows for powerful filtering and tracing in a log aggregation tool.
    ```python
    # Example of contextual logging
    logger.info("Player joined queue", extra={"user_id": user.id, "race": chosen_race})
    ```
4.  **Systematic Refactoring:** Convert all `print()` statements to appropriate `logger` calls. This is a large but critical task that drastically improves maintainability.
5.  **Implementation Note:** Careful attention must be paid to initialization order. The logging system must be fully configured at the application's entry point (`main.py`) *before* any other application modules (like services or commands) are imported to prevent them from obtaining a default, unconfigured logger.

---

## 3. Recommended Implementation Order

To ensure a stable and methodical hardening process, the following implementation order is strongly recommended. Each step builds a foundation that makes the subsequent steps easier and safer to implement.

1.  **Implement Structured, Leveled, and Contextual Logging (Section 2.3):** This must be the first step. Proper logging is the bedrock of observability. Without it, debugging the significant changes that follow will be incredibly difficult and reliant on guesswork. Implementing this first provides the tools to immediately validate the behavior of all subsequent refactoring.

2.  **Overhaul Configuration Management (Section 2.2):** With a robust logging system in place, the next step is to eliminate hardcoded values. This centralizes application tuning and removes a major source of potential bugs *before* we begin the deep dive into refactoring application logic.

3.  **Implement Granular & Hierarchical Exception Handling (Section 2.1):** This is a large-scale refactor that will touch many parts of the codebase. It should only be attempted once logging is available to trace the new error flows and configuration is centralized to handle any error-related settings.

4.  **SQLite `WriteLog` Hardening & Input Sanitization (Sections 1.3 & 1.5):** These are more isolated and self-contained improvements. They can be implemented last, once the core application's stability, configuration, and observability have been hardened. They can be done in any order or in parallel.

## 4. Deprioritized & Future Work

### 4.1. Decouple Services with Dependency Injection

**Status:** De-prioritized.
