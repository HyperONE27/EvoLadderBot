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

# Expected game settings for replay verification
EXPECTED_GAME_PRIVACY = "Normal"
EXPECTED_GAME_SPEED = "Faster"
EXPECTED_GAME_DURATION = "Infinite"
EXPECTED_LOCKED_ALLIANCES = "Yes"

# --- Matchmaking Configuration ---
# Time window in seconds to consider a player "active"
MM_ACTIVITY_WINDOW_SECONDS = 15 * 60

# How often to prune the recent_activity list, in seconds
MM_PRUNE_INTERVAL_SECONDS = 60

# Global matchmaking interval (matchwave) in seconds
MM_MATCH_INTERVAL_SECONDS = 45

# Time window in seconds for players to abort a match after it's found
MM_ABORT_TIMER_SECONDS = 180

# The number of matchmaking waves before the MMR window expands
MM_MMR_EXPANSION_STEP = 1

# --- Queue Pressure Ratio Thresholds ---
MM_HIGH_PRESSURE_THRESHOLD = 0.5
MM_MODERATE_PRESSURE_THRESHOLD = 0.3

# --- MMR Window Parameters (Base, Growth) ---
MM_HIGH_PRESSURE_PARAMS = (75, 25)
MM_MODERATE_PRESSURE_PARAMS = (100, 35)
MM_LOW_PRESSURE_PARAMS = (125, 45)
MM_DEFAULT_PARAMS = (75, 25)

# --- Queue Pressure Calculation ---
MM_POPULATION_THRESHOLD_LOW = 10
MM_POPULATION_THRESHOLD_MID = 25
MM_PRESSURE_SCALE_LOW_POP = 1.2
MM_PRESSURE_SCALE_MID_POP = 1.0
MM_PRESSURE_SCALE_HIGH_POP = 0.8

# --- Match Finding ---
MM_WAIT_CYCLE_PRIORITY_BONUS = 10

# --- In-Game Channel Naming ---
MM_IN_GAME_CHANNEL_PREFIX = "scevo"
MM_IN_GAME_CHANNEL_BASE_NUMBER = 10

# --- Default MMR ---
MMR_DEFAULT = 1500


# --- Logging Configuration ---
# Log level (e.g., "INFO", "DEBUG", "WARNING")
