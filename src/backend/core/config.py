"""
Centralized configuration for the EvoLadder Bot.

This module is the single source of truth for all environment-dependent configuration.
It reads from environment variables and provides sensible defaults for local development.
"""

import os
from pathlib import Path


# ========== Project Paths ==========

# Project root directory (parent of src/)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


# ========== Persistent Volume Configuration ==========

# PERSISTENT_VOLUME_PATH is the mount point for a persistent volume (e.g., on Railway).
# If this environment variable is set, all persistent data (including the WAL)
# will be stored in this directory instead of the project directory.
#
# Example Railway setup:
#   1. Create a volume in Railway
#   2. Mount it at /volume
#   3. Set PERSISTENT_VOLUME_PATH=/volume in Railway environment variables
#
# Local development:
#   - Leave PERSISTENT_VOLUME_PATH unset
#   - Data will be stored in <project_root>/data/
PERSISTENT_VOLUME_PATH = os.getenv("PERSISTENT_VOLUME_PATH")


# ========== Write-Ahead Log (WAL) Configuration ==========

def get_wal_path() -> Path:
    """
    Get the path to the Write-Ahead Log (WAL) database file.
    
    Returns:
        Path to write_log.db
        - If PERSISTENT_VOLUME_PATH is set: <volume>/wal/write_log.db
        - Otherwise (local dev): <project_root>/data/wal/write_log.db
    """
    if PERSISTENT_VOLUME_PATH:
        # Production: Use persistent volume
        base_path = Path(PERSISTENT_VOLUME_PATH)
        wal_path = base_path / "wal" / "write_log.db"
        return wal_path
    else:
        # Local development: Use project directory
        wal_path = PROJECT_ROOT / "data" / "wal" / "write_log.db"
        return wal_path


# Expose the WAL path as a module-level constant for easy import
WAL_PATH = get_wal_path()

# ========== Replay Verification Configuration ==========

# Maximum time window (in minutes) allowed between match assignment and replay start time.
# Used to verify that replays are from the correct match window.
REPLAY_TIMESTAMP_WINDOW_MINUTES = 20

