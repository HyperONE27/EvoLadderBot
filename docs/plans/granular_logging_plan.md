# Granular Logging Configuration Plan

This document outlines a plan to implement a more configurable and fine-grained logging system for the EvoLadderBot. The goal is to reduce log noise in production while allowing for detailed debugging when necessary.

## 1. Current State Analysis

The current logging setup uses the standard Python `logging` module. Loggers are instantiated in various services and commands with `logging.getLogger(__name__)`. However, the configuration is likely managed centrally in `bot_setup.py` and is not easily adjustable without code changes for different environments or debugging scenarios.

## 2. Proposed Architecture

We will introduce a centralized logging configuration that allows for dynamic control over log levels and log types.

### 2.1. Configuration File

A new file, `src/bot/logging_config.py`, will be created to store all logging-related settings. This keeps logging configuration separate from the main application config (`config.py`).

### 2.2. Configuration Structure

The `logging_config.py` will contain a dictionary-based configuration. This allows for easy extension.

Example structure:

```python
# src/bot/logging_config.py

import logging

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
            'level': 'INFO', # Default level for the handler
        },
    },
    'loggers': {
        '': {  # Root logger
            'handlers': ['console'],
            'level': 'WARNING', # Global default log level
            'propagate': True,
        },
        'discord': {
            'level': 'INFO',
        },
        'websockets': {
            'level': 'INFO',
        },
        'backend.db': {
            'level': 'INFO',
        },
        'backend.services.matchmaking_service': {
            'level': 'DEBUG',
        },
        'performance': {
            'level': 'INFO',
        },
        'memory': {
            'level': 'INFO',
        }
    },
    'toggles': {
        'log_performance_metrics': True,
        'log_memory_usage': True,
        'log_db_queries': False,
    }
}
```

This structure provides:
*   A global default log level.
*   Specific log levels for different modules (`backend.db`, `backend.services.matchmaking_service`).
*   Toggles for specific features like performance or memory logging. These toggles can be checked in the code before a log message is even constructed, saving CPU cycles.

### 2.3. Applying the Configuration

In `src/bot/bot_setup.py`, we will add a function `setup_logging()` that uses `logging.config.dictConfig` to apply the configuration from `logging_config.py`.

```python
# src/bot/bot_setup.py
import logging.config
from .logging_config import LOGGING_CONFIG

def setup_logging():
    """Configures logging for the application."""
    logging.config.dictConfig(LOGGING_CONFIG)

# This function will be called early in the bot's startup process.
```

## 3. Implementation Steps

1.  **Create `src/bot/logging_config.py`**: Add the proposed configuration structure. Adjust default levels based on an initial assessment of what is noisy.
2.  **Modify `src/bot/bot_setup.py`**: Add the `setup_logging()` function and call it at startup. The existing logging setup will be replaced.
3.  **Refactor Performance/Memory Logging**:
    *   The `performance_service` and `memory_monitor` should use a dedicated logger (e.g., `logging.getLogger('performance')`).
    *   Before logging, they should check the corresponding toggle in `LOGGING_CONFIG['toggles']`.
    *   Example in `performance_service`:
        ```python
        from src.bot.logging_config import LOGGING_CONFIG

        perf_logger = logging.getLogger('performance')

        def log_performance(data):
            if LOGGING_CONFIG['toggles']['log_performance_metrics']:
                perf_logger.info(f"Performance data: {data}")
        ```
4.  **Refactor Database Logging**:
    *   In `src/backend/db/adapters/timed_adapter.py` or similar places where queries are logged, use a dedicated logger like `logging.getLogger('backend.db.queries')`.
    *   Wrap log calls with the `log_db_queries` toggle.
5.  **Review and Refactor Module-level Loggers**:
    *   Go through all files that use `logging.getLogger(__name__)`.
    *   Ensure their logger names (e.g., `backend.services.matchmaking_service`) match keys in the `LOGGING_CONFIG` if they need a specific log level. Otherwise, they will inherit from parent loggers, which is the desired default behavior.
6.  **Add Documentation**: Add comments to `logging_config.py` explaining how to add new loggers and change levels.

## 4. Future Enhancements (Optional)

*   **Dynamic Reloading**: Implement a command for bot administrators to reload the logging configuration from the file without restarting the bot. This would involve re-running `logging.config.dictConfig()`.
*   **File-based Logging**: Add file handlers to the `LOGGING_CONFIG` to write logs to files, with rotation.
*   **Environment-based Configuration**: Adjust `LOGGING_CONFIG` based on an environment variable (e.g., `ENV=development` vs `ENV=production`), so that development environments are more verbose by default.

This plan will be executed methodically to ensure a smooth transition to the new logging system.
