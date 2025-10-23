"""
Process pool health checker for event-driven health monitoring.

This module provides a global process pool health checker that can be used
from anywhere in the application to check process pool health on-demand.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Global reference to the bot instance for health checking
_bot_instance: Optional[object] = None


def set_bot_instance(bot):
    """Set the bot instance for health checking."""
    global _bot_instance
    _bot_instance = bot


async def ensure_process_pool_healthy() -> bool:
    """
    Event-driven process pool health check.
    
    Only checks the process pool when it's actually needed for work.
    This replaces idle spinning with an on-demand approach.
    
    Returns:
        True if pool is healthy or was successfully restarted, False otherwise
    """
    if _bot_instance is None:
        logger.warning("[Process Pool] No bot instance available for health check")
        return False
    
    if not hasattr(_bot_instance, '_ensure_process_pool_healthy'):
        logger.warning("[Process Pool] Bot instance does not have health check method")
        return False
    
    return await _bot_instance._ensure_process_pool_healthy()
