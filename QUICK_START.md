# Quick Start Guide - Database Backend

## Initial Setup (One Time Only)

```bash
# Create the database with all tables
python src/backend/db/create_table.py
```

This creates `evoladder.db` with all necessary tables.

## Database Already Has Test Data

The database currently contains:
- 10 test players (AlphaStrike, BravoTango, CharlieEcho, etc.)
- 21 MMR records across different races
- Sample data ready for `/leaderboard` testing
- **Region codes** use correct values from `residential_regions` in `regions.json` (NAE, EUW, SAM, SEA, OCE, etc.)

## Using the Bot Commands

All these commands now work with the database:

### `/setup`
- Creates complete player profile
- Stores: player name, BattleTag, alt names, country, region
- Sets `completed_setup = TRUE`
- **Database table**: `players`

### `/activate`
- Stores activation code
- Creates player if doesn't exist
- **Database table**: `players` (activation_code field)

### `/termsofservice`
- Records TOS acceptance
- Sets `accepted_tos = TRUE` + timestamp
- **Database table**: `players`

### `/setcountry`
- Updates player's country
- Logs old and new values
- **Database tables**: `players`, `player_action_logs`

### `/leaderboard`
- Reads MMR data from database
- Supports all filters (race, country, best-race-only)
- **Database table**: `mmrs_1v1` (joined with `players`)

## Quick Database Check

```python
from src.backend.services.user_info_service import UserInfoService

service = UserInfoService()

# Create a test player
# NOTE: Region codes must come from residential_regions in regions.json
service.create_player(
    discord_uid=999999,
    player_name="TestPlayer",
    battletag="TestPlayer#1234",
    country="US",
    region="NAE"  # Eastern North America (from residential_regions)
)

# Check if they exist
if service.player_exists(999999):
    print("✓ Player created successfully!")
```

## Adding MMR Data

```python
from src.backend.db.db_reader_writer import DatabaseWriter

writer = DatabaseWriter()

writer.create_or_update_mmr_1v1(
    discord_uid=999999,
    player_name="TestPlayer",
    race="sc2_terran",
    mmr=2000,
    games_played=50,
    games_won=30,
    games_lost=20
)
```

## Checking Leaderboard Data

```python
from src.backend.services.leaderboard_service import LeaderboardService
import asyncio

async def check_leaderboard():
    service = LeaderboardService()
    data = await service.get_leaderboard_data(page_size=10)
    print(f"Total players: {data['total_players']}")
    print(f"Total pages: {data['total_pages']}")
    for player in data['players']:
        print(f"  {player['player_id']} - {player['mmr']} MMR")

asyncio.run(check_leaderboard())
```

## Database Location

- **File**: `evoladder.db` (in project root)
- **Format**: SQLite 3
- **Tables**: 8 tables (see `schema.md`)

## Important Notes

1. **Every command** calls `ensure_player_exists()` first - creates minimal DB record for new users
2. **All SQL queries** are in `src/backend/db/db_reader_writer.py`
3. **Services** handle business logic
4. **Commands** handle UI only
5. **Automatic logging** for important actions
6. **Discord UID** is the primary identifier (not player name)

## What's Not Implemented Yet

- `/queue` command (intentionally excluded for now)
- Match recording
- MMR updates
- Matchmaking logic

---

**Everything is ready to go!** The database is set up, all commands are connected, and test data is in place for testing.

