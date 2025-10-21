# Configuration Management Strategy: .env vs. Global Config

This document outlines the strategy for managing configuration in the application, drawing a clear line between what should be stored in environment variables (`.env` file) versus what should be defined in a global, version-controlled configuration file (e.g., `config.py`).

The guiding principle is the separation of **Secrets & Environment-Specifics** from **Application Constants**.

---

## 1. Environment Variables (`.env` file)

Environment variables are the correct place for any configuration that is sensitive or that changes between different deployment environments (e.g., your local development machine, a staging server, and the live production server).

**Purpose:** To store secrets and environment-specific settings. This file should **never** be committed to version control.

**What to put here:**

*   **Secrets & Credentials:**
    *   `DISCORD_BOT_TOKEN`: The unique token for your Discord bot.
    *   `DATABASE_URL`: The connection string for your database (especially important if you move to a hosted database like PostgreSQL).
    *   Any API keys for external services you might integrate in the future.

*   **Environment-Specific Configuration:**
    *   `LOG_LEVEL`: You might want `DEBUG` for local development but `INFO` or `WARNING` in production.
    *   `BOT_COMMAND_PREFIX`: You could use a different prefix like `!` for production and `?` for a development instance of the bot to avoid conflicts.
    *   `ENABLE_DEBUG_FEATURES`: A flag to turn on or off specific diagnostic commands or features.

**Example `.env` file:**
```dotenv
# .env

# This file is for local development and should NOT be committed to git.
# In production, these values should be set as actual environment variables.

# Secrets
DISCORD_BOT_TOKEN="your_secret_bot_token_here"
DATABASE_URL="sqlite:///evoladder.db"

# Environment-Specifics
LOG_LEVEL="DEBUG"
BOT_COMMAND_PREFIX="?"
```

**Security:** Always ensure that `.env` is listed in your `.gitignore` file.

---

## 2. Global Config File (e.g., `src/config.py`)

A global configuration file is the correct place for constants and settings that are integral to the application's behavior but are **not secret** and **do not change** between environments. These values are part of the application's design and should be version-controlled.

**Purpose:** To define stable, non-sensitive, application-level constants. This file should be committed to version control.

**What to put here:**

*   **Application Logic Constants:**
    *   MMR calculation values from `MMRService` (`_K_FACTOR`, `_DIVISOR`, `_DEFAULT_MMR`).
    *   Matchmaking parameters from `MatchmakingService` (`ABORT_TIMER_SECONDS`, `HIGH_PRESSURE_THRESHOLD`).

*   **File System and Path Definitions:**
    *   `REPLAYS_DIR` from `replay_service.py`.
    *   Paths to data files (`countries.json`, `maps.json`).

*   **Default Values and Magic Numbers:**
    *   Default number of match aborts for a new player.
    *   The number of items to show per page on the leaderboard.
    *   Any other hardcoded numbers or strings that define the bot's behavior.

**Example `config.py` file:**
```python
# src/config.py

import os

# --- Matchmaking ---
ABORT_TIMER_SECONDS = 300
HIGH_PRESSURE_THRESHOLD = 0.8
MODERATE_PRESSURE_THRESHOLD = 0.5

# --- MMR ---
DEFAULT_MMR = 1500
K_FACTOR = 40
MMR_DIVISOR = 500

# --- File Paths ---
# Use an absolute path relative to the project root for robustness
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPLAYS_DIR = os.path.join(PROJECT_ROOT, "data", "replays")
COUNTRIES_DATA_PATH = os.path.join(PROJECT_ROOT, "data", "misc", "countries.json")

# --- Bot Behavior ---
LEADERBOARD_PAGE_SIZE = 15
DEFAULT_PLAYER_ABORTS = 3
```

---

## How They Work Together

A robust configuration service (as proposed in the Architectural Improvements document) would:
1.  Load the constants from the global `config.py` file first.
2.  Then, load the values from the `.env` file (or the machine's environment variables).
3.  The environment variables would **override** any values from the global config if there's a name collision. This allows for dynamic changes in different environments without altering the codebase.

By following this separation, you gain security, flexibility, and clarity in your application's configuration.
