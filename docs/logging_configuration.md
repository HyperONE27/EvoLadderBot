# Logging Configuration Guide

This document explains how to configure the new centralized logging system for fine-grained control over what gets logged.

## Overview

The new logging system provides:
- **Category-based logging**: Different types of operations (performance, memory, database, etc.) can be controlled independently
- **Config file configuration**: Easy to adjust logging levels by modifying `src/bot/config.py`
- **Performance-optimized**: Logging can be disabled for categories you don't need
- **Structured logging**: Consistent format across all log types

## Configuration Variables

All logging configuration is done in `src/bot/config.py`:

### Base Configuration
- `LOG_LEVEL`: Base logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

### Category-Specific Levels
- `LOG_GENERAL`: General application logging
- `LOG_PERFORMANCE`: Performance monitoring and timing
- `LOG_MEMORY`: Memory usage and leak detection
- `LOG_DATABASE`: Database operations and queries
- `LOG_DISCORD`: Discord library and API calls
- `LOG_QUEUE`: Queue management and matchmaking
- `LOG_MATCHMAKING`: Matchmaking algorithm and logic
- `LOG_NOTIFICATIONS`: Player notifications and subscriptions
- `LOG_PROCESS_POOL`: Process pool health and management
- `LOG_REPLAY`: Replay file processing

### Performance Thresholds
- `PERF_SLOW_OPERATION_THRESHOLD`: Log operations slower than this (ms)
- `PERF_CRITICAL_OPERATION_THRESHOLD`: Critical threshold for very slow operations (ms)

### Memory Thresholds
- `MEMORY_LEAK_THRESHOLD`: Alert when memory grows by this amount (MB)
- `MEMORY_HIGH_USAGE_THRESHOLD`: Alert when total memory exceeds this (MB)

## Example Configurations

### Development/Debugging (Verbose)
```python
# In src/bot/config.py
LOG_LEVEL = "DEBUG"
LOG_PERFORMANCE = "DEBUG"
LOG_MEMORY = "DEBUG"
LOG_DATABASE = "DEBUG"
LOG_QUEUE = "DEBUG"
LOG_MATCHMAKING = "DEBUG"
```

### Production (Minimal Noise)
```python
# In src/bot/config.py
LOG_LEVEL = "WARNING"
LOG_GENERAL = "WARNING"
LOG_PERFORMANCE = "ERROR"
LOG_MEMORY = "WARNING"
LOG_DATABASE = "ERROR"
LOG_QUEUE = "WARNING"
LOG_MATCHMAKING = "WARNING"
LOG_NOTIFICATIONS = "WARNING"
```

### Performance Testing (Focus on Performance)
```python
# In src/bot/config.py
LOG_LEVEL = "INFO"
LOG_PERFORMANCE = "DEBUG"
LOG_MEMORY = "DEBUG"
LOG_DATABASE = "WARNING"
LOG_QUEUE = "WARNING"
LOG_MATCHMAKING = "WARNING"
LOG_NOTIFICATIONS = "WARNING"
```

### Memory Debugging (Focus on Memory)
```python
# In src/bot/config.py
LOG_LEVEL = "INFO"
LOG_MEMORY = "DEBUG"
LOG_PERFORMANCE = "WARNING"
LOG_DATABASE = "WARNING"
LOG_QUEUE = "INFO"
LOG_MATCHMAKING = "INFO"
LOG_NOTIFICATIONS = "INFO"
```

## Usage in Code

The new logging system provides specialized macros for different types of operations:

```python
from src.bot.logging_config import (
    log_general, log_performance, log_memory, log_database,
    log_queue, log_matchmaking, log_notifications, log_process_pool,
    LogLevel
)

# General logging
log_general(LogLevel.INFO, "Application started")

# Performance logging with duration
log_performance(LogLevel.WARNING, "Slow database query", duration_ms=150.5)

# Memory logging with usage
log_memory(LogLevel.INFO, "Memory check completed", memory_mb=245.3)

# Database operations
log_database(LogLevel.INFO, "User profile updated", operation="update_profile")

# Queue operations
log_queue(LogLevel.INFO, "Player added to queue", player_id=123456)

# Matchmaking
log_matchmaking(LogLevel.INFO, "Match found", match_id="match_123")

# Notifications
log_notifications(LogLevel.INFO, "Player notified", player_id=123456)

# Process pool
log_process_pool(LogLevel.INFO, "Pool health check completed")
```

## Benefits

1. **Reduced Noise**: Turn off categories you don't need
2. **Performance Focus**: Enable only performance and memory logging for optimization
3. **Debugging**: Enable all categories for comprehensive debugging
4. **Production Ready**: Minimal logging for production environments
5. **Consistent Format**: All logs follow the same structured format

## Migration from Old System

The old `logger.info()`, `logger.warning()`, etc. calls have been replaced with category-specific macros. This provides:
- Better organization of log messages
- Consistent formatting across categories
- Environment-based control
- Performance optimization through selective logging

## Runtime Configuration

You can also control logging at runtime:

```python
from src.bot.logging_config import set_category_level, disable_category, enable_category, LogLevel

# Disable performance logging
disable_category(LogCategory.PERFORMANCE)

# Set memory logging to DEBUG
set_category_level(LogCategory.MEMORY, LogLevel.DEBUG)

# Re-enable notifications
enable_category(LogCategory.NOTIFICATIONS, LogLevel.INFO)
```
