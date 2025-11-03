# src/bot/config.py

"""
Global configuration file for application constants and environment variables.

This module centralizes all environment variable loading to ensure:
1. Environment variables are loaded ONCE at startup
2. All modules import from here (never use os.getenv directly)
3. Missing required variables cause immediate failure (no silent fallbacks)
"""

import os
from dotenv import load_dotenv
from src.backend.core.config import MM_MATCH_INTERVAL_SECONDS

# Load environment variables FIRST
load_dotenv()


def _get_required_env(key: str) -> str:
    """
    Get a required environment variable.
    
    Args:
        key: Environment variable name
        
    Returns:
        The environment variable value
        
    Raises:
        ValueError: If the environment variable is not set
    """
    value = os.getenv(key)
    if value is None:
        raise ValueError(
            f"Required environment variable '{key}' is not set. "
            f"Please add it to your .env file or Railway environment variables."
        )
    return value


def _get_required_int_env(key: str) -> int:
    """
    Get a required integer environment variable.
    
    Args:
        key: Environment variable name
        
    Returns:
        The environment variable value as an integer
        
    Raises:
        ValueError: If the environment variable is not set or not a valid integer
    """
    value = _get_required_env(key)
    try:
        return int(value)
    except ValueError:
        raise ValueError(
            f"Environment variable '{key}' must be a valid integer, got: {value}"
        )


# =============================================================================
# REQUIRED ENVIRONMENT VARIABLES
# =============================================================================

# Discord Bot Configuration
EVOLADDERBOT_TOKEN = _get_required_env("EVOLADDERBOT_TOKEN")

# Global timeout for Discord interactions (in seconds)
GLOBAL_TIMEOUT = _get_required_int_env("GLOBAL_TIMEOUT")

# Worker processes for multiprocessing (replay parsing)
WORKER_PROCESSES = _get_required_int_env("WORKER_PROCESSES")

# Database Configuration
DATABASE_TYPE = _get_required_env("DATABASE_TYPE")  # "sqlite" or "postgresql"

# Database connection string (required for PostgreSQL, ignored for SQLite)
# For SQLite: not required
# For PostgreSQL: must be set
if DATABASE_TYPE.lower() == "postgresql":
    DATABASE_URL = _get_required_env("DATABASE_URL")
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "")  # Optional for SQLite

# SQLite Configuration (only used when DATABASE_TYPE=sqlite)
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "evoladder.db")

# Database Connection Pool Configuration
DB_POOL_MIN_CONNECTIONS = int(os.getenv("DB_POOL_MIN_CONNECTIONS"))
DB_POOL_MAX_CONNECTIONS = int(os.getenv("DB_POOL_MAX_CONNECTIONS"))

# Supabase Configuration (for storage and additional features)
SUPABASE_URL = _get_required_env("SUPABASE_URL")
SUPABASE_KEY = _get_required_env("SUPABASE_KEY")  # Anon key for client-side operations
SUPABASE_SERVICE_ROLE_KEY = _get_required_env("SUPABASE_SERVICE_ROLE_KEY")  # Service role for admin operations
SUPABASE_BUCKET_NAME = os.getenv("SUPABASE_BUCKET_NAME", "replays")  # Default bucket name

# =============================================================================
# APPLICATION CONSTANTS
# =============================================================================

# The current map pool season to be used by the matchmaking service
CURRENT_SEASON = "season_alpha"

# Queue searching view heartbeat timer (seconds) - how often to update the searching view
QUEUE_SEARCHING_HEARTBEAT_SECONDS = MM_MATCH_INTERVAL_SECONDS / 2

# =============================================================================
# PRUNE COMMAND PROTECTION TIMERS
# =============================================================================

# Recent message protection (minutes) - protects very recent messages from deletion
# This is a safety net to prevent deleting messages that might be prune-related
RECENT_MESSAGE_PROTECTION_MINUTES = 5

# Queue message protection (days) - protects queue messages from deletion
# Only queue messages less than this age are protected from pruning
QUEUE_MESSAGE_PROTECTION_DAYS = 7

# Prune command delay (seconds) - delay between message deletions to avoid rate limits
PRUNE_DELETE_DELAY_SECONDS = 1

# =============================================================================
# MESSAGE QUEUE CONFIGURATION
# =============================================================================

# Discord message queue rate limit (messages per second)
# This controls the global throughput of all outbound Discord API calls
DISCORD_MESSAGE_RATE_LIMIT = 45