"""
Centralized logging configuration for EvoLadderBot.

This module provides structured JSON logging with contextual information.
It must be imported and configured before any other application modules.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs as JSON.
    
    Each log record includes:
    - timestamp: ISO 8601 formatted timestamp
    - level: Log level (INFO, WARNING, ERROR, etc.)
    - logger: Name of the logger that emitted the record
    - message: The log message
    - extra: Any additional context fields provided via the 'extra' parameter
    - exc_info: Exception information if present
    """
    
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add any extra context fields
        # These are fields added via logger.info("message", extra={"key": "value"})
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName",
                "relativeCreated", "thread", "threadName", "exc_info",
                "exc_text", "stack_info", "taskName"
            ]:
                log_data[key] = value
        
        return json.dumps(log_data)


def configure_logging(log_level: int = logging.INFO) -> None:
    """
    Configure the root logger with JSON formatting.
    
    This function should be called once at application startup, before any
    other modules are imported or any loggers are created.
    
    Args:
        log_level: The minimum log level to capture (default: logging.INFO)
    """
    # Create handler that writes to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('discord.http').setLevel(logging.WARNING)
    logging.getLogger('discord.gateway').setLevel(logging.WARNING)
    logging.getLogger('discord.client').setLevel(logging.WARNING)
    
    # Log the initialization
    logger = logging.getLogger(__name__)
    logger.info("Logging system initialized", extra={"log_level": logging.getLevelName(log_level)})

