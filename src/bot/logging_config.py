"""
Centralized logging configuration system with macros for different log types.

This module provides:
1. Centralized logging configuration with environment variable support
2. Specialized logging macros for different types of operations
3. Fine-grained control over what gets logged
4. Performance-optimized logging that can be toggled on/off
"""

import logging
import os
import sys
from typing import Optional, Dict, Any
from enum import Enum


class LogLevel(Enum):
    """Logging levels with numeric values for comparison."""
    CRITICAL = 50
    ERROR = 40
    WARNING = 30
    INFO = 20
    DEBUG = 10
    NOTSET = 0


class LogCategory(Enum):
    """Categories of logging for fine-grained control."""
    GENERAL = "general"
    PERFORMANCE = "performance"
    MEMORY = "memory"
    DATABASE = "database"
    DISCORD = "discord"
    QUEUE = "queue"
    MATCHMAKING = "matchmaking"
    NOTIFICATIONS = "notifications"
    PROCESS_POOL = "process_pool"
    REPLAY = "replay"


class LoggingConfig:
    """Centralized logging configuration with environment variable support."""
    
    def __init__(self):
        self._setup_logging()
        self._configure_category_levels()
        self._setup_macros()
    
    def _setup_logging(self):
        """Configure the root logger and format."""
        # Import config here to avoid circular imports
        from src.bot.config import LOG_LEVEL
        
        # Get base log level from config
        base_level = LOG_LEVEL.upper()
        log_level = getattr(logging, base_level, logging.INFO)
        
        # Configure root logger
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            force=True  # Override any existing configuration
        )
        
        # Set Discord library to WARNING to reduce noise
        logging.getLogger('discord').setLevel(logging.WARNING)
        logging.getLogger('discord.http').setLevel(logging.WARNING)
        logging.getLogger('discord.gateway').setLevel(logging.WARNING)
    
    def _configure_category_levels(self):
        """Configure log levels for different categories."""
        # Import config here to avoid circular imports
        from src.bot.config import (
            LOG_GENERAL, LOG_PERFORMANCE, LOG_MEMORY, LOG_DATABASE,
            LOG_DISCORD, LOG_QUEUE, LOG_MATCHMAKING, LOG_NOTIFICATIONS,
            LOG_PROCESS_POOL, LOG_REPLAY
        )
        
        # Get levels from config
        category_levels = {
            LogCategory.GENERAL: LOG_GENERAL,
            LogCategory.PERFORMANCE: LOG_PERFORMANCE,
            LogCategory.MEMORY: LOG_MEMORY,
            LogCategory.DATABASE: LOG_DATABASE,
            LogCategory.DISCORD: LOG_DISCORD,
            LogCategory.QUEUE: LOG_QUEUE,
            LogCategory.MATCHMAKING: LOG_MATCHMAKING,
            LogCategory.NOTIFICATIONS: LOG_NOTIFICATIONS,
            LogCategory.PROCESS_POOL: LOG_PROCESS_POOL,
            LogCategory.REPLAY: LOG_REPLAY,
        }
        
        # Apply category-specific log levels
        for category, level_str in category_levels.items():
            level = getattr(logging, level_str.upper(), logging.INFO)
            logger_name = f"src.{category.value}"
            logging.getLogger(logger_name).setLevel(level)
    
    def _setup_macros(self):
        """Set up logging macros for different operations."""
        # Create category loggers
        self.loggers = {}
        for category in LogCategory:
            self.loggers[category] = logging.getLogger(f"src.{category.value}")
    
    def get_logger(self, category: LogCategory) -> logging.Logger:
        """Get a logger for a specific category."""
        return self.loggers[category]
    
    def is_enabled(self, category: LogCategory, level: LogLevel) -> bool:
        """Check if a specific category and level is enabled."""
        logger = self.get_logger(category)
        return logger.isEnabledFor(level.value)


# Global logging configuration instance
_logging_config = LoggingConfig()


# =============================================================================
# LOGGING MACROS
# =============================================================================

def log_general(level: LogLevel, message: str, **kwargs):
    """Log a general message."""
    logger = _logging_config.get_logger(LogCategory.GENERAL)
    if logger.isEnabledFor(level.value):
        logger.log(level.value, message, **kwargs)


def log_performance(level: LogLevel, message: str, duration_ms: Optional[float] = None, **kwargs):
    """Log performance-related messages with optional duration."""
    logger = _logging_config.get_logger(LogCategory.PERFORMANCE)
    if logger.isEnabledFor(level.value):
        if duration_ms is not None:
            message = f"[PERF] {message} ({duration_ms:.2f}ms)"
        logger.log(level.value, message, **kwargs)


def log_memory(level: LogLevel, message: str, memory_mb: Optional[float] = None, **kwargs):
    """Log memory-related messages with optional memory usage."""
    logger = _logging_config.get_logger(LogCategory.MEMORY)
    if logger.isEnabledFor(level.value):
        if memory_mb is not None:
            message = f"[MEM] {message} ({memory_mb:.2f} MB)"
        logger.log(level.value, message, **kwargs)


def log_database(level: LogLevel, message: str, operation: Optional[str] = None, **kwargs):
    """Log database-related messages with optional operation name."""
    logger = _logging_config.get_logger(LogCategory.DATABASE)
    if logger.isEnabledFor(level.value):
        if operation:
            message = f"[DB] {operation}: {message}"
        else:
            message = f"[DB] {message}"
        logger.log(level.value, message, **kwargs)


def log_discord(level: LogLevel, message: str, **kwargs):
    """Log Discord-related messages."""
    logger = _logging_config.get_logger(LogCategory.DISCORD)
    if logger.isEnabledFor(level.value):
        logger.log(level.value, f"[DISCORD] {message}", **kwargs)


def log_queue(level: LogLevel, message: str, player_id: Optional[int] = None, **kwargs):
    """Log queue-related messages with optional player ID."""
    logger = _logging_config.get_logger(LogCategory.QUEUE)
    if logger.isEnabledFor(level.value):
        if player_id:
            message = f"[QUEUE] Player {player_id}: {message}"
        else:
            message = f"[QUEUE] {message}"
        logger.log(level.value, message, **kwargs)


def log_matchmaking(level: LogLevel, message: str, match_id: Optional[str] = None, **kwargs):
    """Log matchmaking-related messages with optional match ID."""
    logger = _logging_config.get_logger(LogCategory.MATCHMAKING)
    if logger.isEnabledFor(level.value):
        if match_id:
            message = f"[MATCH] {match_id}: {message}"
        else:
            message = f"[MATCH] {message}"
        logger.log(level.value, message, **kwargs)


def log_notifications(level: LogLevel, message: str, player_id: Optional[int] = None, **kwargs):
    """Log notification-related messages with optional player ID."""
    logger = _logging_config.get_logger(LogCategory.NOTIFICATIONS)
    if logger.isEnabledFor(level.value):
        if player_id:
            message = f"[NOTIFY] Player {player_id}: {message}"
        else:
            message = f"[NOTIFY] {message}"
        logger.log(level.value, message, **kwargs)


def log_process_pool(level: LogLevel, message: str, **kwargs):
    """Log process pool-related messages."""
    logger = _logging_config.get_logger(LogCategory.PROCESS_POOL)
    if logger.isEnabledFor(level.value):
        logger.log(level.value, f"[POOL] {message}", **kwargs)


def log_replay(level: LogLevel, message: str, replay_id: Optional[str] = None, **kwargs):
    """Log replay-related messages with optional replay ID."""
    logger = _logging_config.get_logger(LogCategory.REPLAY)
    if logger.isEnabledFor(level.value):
        if replay_id:
            message = f"[REPLAY] {replay_id}: {message}"
        else:
            message = f"[REPLAY] {message}"
        logger.log(level.value, message, **kwargs)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def log_slow_operation(operation_name: str, duration_ms: float, threshold_ms: float = 100.0):
    """Log slow operations with performance context."""
    if duration_ms > threshold_ms:
        log_performance(
            LogLevel.WARNING,
            f"Slow operation: {operation_name}",
            duration_ms=duration_ms,
            extra={"operation": operation_name, "threshold_ms": threshold_ms}
        )


def log_memory_usage(operation: str, memory_mb: float, delta_mb: Optional[float] = None):
    """Log memory usage with optional delta."""
    message = f"Memory usage for {operation}"
    if delta_mb is not None:
        message += f" (delta: {delta_mb:+.2f} MB)"
    
    log_memory(LogLevel.INFO, message, memory_mb=memory_mb)


def log_database_operation(operation: str, success: bool, duration_ms: Optional[float] = None):
    """Log database operations with success status and optional duration."""
    level = LogLevel.INFO if success else LogLevel.ERROR
    message = f"Operation {'completed' if success else 'failed'}"
    if duration_ms is not None:
        message += f" in {duration_ms:.2f}ms"
    
    log_database(level, message, operation=operation)


# =============================================================================
# CONFIGURATION HELPERS
# =============================================================================

def get_logging_status() -> Dict[str, Any]:
    """Get current logging configuration status."""
    status = {}
    for category in LogCategory:
        logger = _logging_config.get_logger(category)
        status[category.value] = {
            "level": logging.getLevelName(logger.level),
            "enabled": logger.isEnabledFor(logging.INFO)
        }
    return status


def set_category_level(category: LogCategory, level: LogLevel):
    """Dynamically set the log level for a category."""
    logger = _logging_config.get_logger(category)
    logger.setLevel(level.value)


def disable_category(category: LogCategory):
    """Disable logging for a specific category."""
    logger = _logging_config.get_logger(category)
    logger.setLevel(logging.CRITICAL + 1)  # Disable all logging


def enable_category(category: LogCategory, level: LogLevel = LogLevel.INFO):
    """Enable logging for a specific category."""
    logger = _logging_config.get_logger(category)
    logger.setLevel(level.value)
