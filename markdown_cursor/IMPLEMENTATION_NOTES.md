# Database Implementation Notes

## Overview

This document describes the implementation of the SQLite database backend for EvoLadderBot, connecting all frontend bot commands to the database through service layers.

## Architecture

```
Bot Commands (Frontend)
    ↓
Service Layer (Backend Services)
    ↓
Database Layer (db_reader_writer.py)
    ↓
SQLite Database (evoladder.db)
```

## Files Created/Modified

### Database Layer

1. **`src/backend/db/create_table.py`**
   - Creates all SQLite tables based on `schema.md`
   - Tables: `players`, `player_action_logs`, `mmrs_1v1`, `matches_1v1`, `preferences_1v1`, `mmrs_2v2`, `matches_2v2`, `preferences_2v2`
   - Run once to initialize: `python src/backend/db/create_table.py`

2. **`src/backend/db/db_reader_writer.py`**
   - `DatabaseReader`: All SELECT queries
   - `DatabaseWriter`: All INSERT/UPDATE queries
   - ALL SQL queries are contained in this file (except table creation)
   - Methods include:
     - Player CRUD operations
     - Action logging
     - MMR management
     - Leaderboard queries with filtering
     - Match history
     - Preferences management

### Service Layer

3. **`src/backend/services/user_info_service.py`**
   - Manages user profiles and settings
   - Methods:
     - `get_player()` - Get player by Discord UID
     - `player_exists()` - Check if player exists
     - `ensure_player_exists()` - **Get-or-create pattern - called at start of every command**
     - `create_player()` - Create new player
     - `update_player()` - Update player info
     - `update_country()` - Update country with logging
     - `submit_activation_code()` - Handle activation codes
     - `accept_terms_of_service()` - Mark TOS acceptance
     - `complete_setup()` - Complete profile setup

4. **`src/backend/services/leaderboard_service.py`**
   - Modified to use database instead of JSON file
   - Queries `mmrs_1v1` table through `DatabaseReader`
   - Maintains filter state and pagination
   - Supports race/country filtering and best-race-only mode

### Bot Commands (Hooked Up)

5. **`/activate` - `src/bot/interface/commands/activate_command.py`**
   - Submits activation code to database
   - Creates player if doesn't exist, updates if exists
   - Logs action in `player_action_logs`

6. **`/setup` - `src/bot/interface/commands/setup_command.py`**
   - Collects player name, BattleTag, alt names, country, region
   - Calls `user_info_service.complete_setup()`
   - Creates/updates player record
   - Marks setup as complete with timestamp

7. **`/setcountry` - `src/bot/interface/commands/setcountry_command.py`**
   - Updates player's country
   - Calls `user_info_service.update_country()`
   - Logs old and new country values

8. **`/termsofservice` - `src/bot/interface/commands/termsofservice_command.py`**
   - Displays TOS
   - On acceptance, calls `user_info_service.accept_terms_of_service()`
   - Creates player record if doesn't exist
   - Sets `accepted_tos = TRUE` and `accepted_tos_date`

9. **`/leaderboard` - `src/bot/interface/commands/leaderboard_command.py`**
   - Now reads from database via `leaderboard_service`
   - Queries `mmrs_1v1` joined with `players` table
   - Supports all existing filters (race, country, best-race-only)
   - Pagination works with database results

## Database Schema

### Key Tables

- **`players`**: User profiles with Discord UID as unique identifier
- **`player_action_logs`**: Audit trail of all user actions
- **`mmrs_1v1`**: MMR records per race (supports multiple races per player)
- **`matches_1v1`**: Match history
- **`preferences_1v1`**: User preferences for matchmaking

### Important Fields

- `discord_uid`: Primary identifier for players (INTEGER, NOT NULL)
- `region`: Region code - **MUST come from `residential_regions` in `regions.json`**
  - Valid codes: NAW, NAC, NAE, CAM, SAM, EUW, EUE, AFR, MEA, SEA, KRJ, CHN, THM, OCE, USB, FER
  - NOT from game_servers or game_regions
- `accepted_tos`: Boolean tracking TOS acceptance
- `completed_setup`: Boolean tracking setup completion
- **Timestamps** (immutability protection):
  - `created_at`: **IMMUTABLE** - Set automatically on creation, cannot be modified
  - `accepted_tos_date`: **IMMUTABLE** - Set once when TOS accepted, cannot be overwritten
  - `completed_setup_date`: **IMMUTABLE** - Set once when setup completed, cannot be overwritten
  - `updated_at`: MUTABLE - Updated on every change

## Usage

### Initialize Database

```bash
python src/backend/db/create_table.py
```

This creates `evoladder.db` in the project root.

### Test with Sample Data

To test the leaderboard, you can create sample players and MMR data:

```python
from src.backend.db.db_reader_writer import DatabaseWriter

writer = DatabaseWriter()
writer.create_player(discord_uid=12345, player_name="TestPlayer", country="US", region="NA")
writer.create_or_update_mmr_1v1(
    discord_uid=12345,
    player_name="TestPlayer",
    race="sc2_terran",
    mmr=2000,
    games_played=50,
    games_won=30,
    games_lost=20
)
```

### Using Services

```python
from src.backend.services.user_info_service import UserInfoService

user_service = UserInfoService()

# Create a player
user_service.create_player(
    discord_uid=12345,
    player_name="MyName",
    battletag="MyName#1234",
    country="US",
    region="NA"
)

# Update country
user_service.update_country(12345, "CA")

# Check if player exists
if user_service.player_exists(12345):
    player = user_service.get_player(12345)
```

## Command Flow Examples

### /setup Command Flow

1. **Command invoked** - `ensure_player_exists()` creates minimal record if needed
2. User fills out modal with player name, BattleTag, alt names
3. User selects country and region from dropdowns
4. User confirms preview
5. Bot calls `user_info_service.complete_setup()`
6. Service creates/updates player in database
7. Service marks `completed_setup = TRUE`
8. **Service logs EACH field change as separate row** in `player_action_logs`:
   - player_name: None → "NewName"
   - battletag: None → "NewTag#1234"
   - alt_player_name_1: None → "Alt1" (if provided)
   - alt_player_name_2: None → "Alt2" (if provided)
   - country: None → "US"
   - region: None → "NAE"
   - completed_setup: False → True
9. Updates `updated_at` timestamp in players table
10. User sees success message

### /leaderboard Command Flow

1. User invokes `/leaderboard`
2. **Command invoked** - `ensure_player_exists()` creates minimal record if needed
3. Bot creates `LeaderboardService` instance
4. Service queries `mmrs_1v1` via `DatabaseReader.get_leaderboard_1v1()`
5. Results joined with `players` table for country info
6. Service applies filters (race, country, best-race-only)
7. Service handles pagination
8. Bot displays formatted leaderboard

## Notes

- **Every command calls `ensure_player_exists()` first** - creates minimal record if user is new
- **Granular logging**: Each field change creates a separate row in `player_action_logs`
  - `/setup` logs 6-7 rows (one per field: player_name, battletag, alt names, country, region, completed_setup)
  - `/setcountry` logs 1 row (country: old → new)
- **Timestamp tracking**: `updated_at` in players table is updated on every change
- All SQL queries are in `db_reader_writer.py` (except initial table creation)
- Services handle business logic and call database methods
- Bot commands handle UI and call services
- Database uses SQLite's row factory for dict-like access
- Context managers ensure proper connection cleanup

## Future Work

- `/queue` command integration (not yet implemented)
- Match result recording
- MMR calculation and updates
- Decay system implementation
- 2v2 mode support
- Additional game modes (FFA, 3v3, etc.)

