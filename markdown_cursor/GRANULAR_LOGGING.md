# Granular Logging Implementation

## Overview

The `player_action_logs` table records **individual field changes** - one row per setting change. This provides a detailed audit trail of all user profile modifications.

## How It Works

### One Row Per Field Change

When a user runs `/setup` or `/setcountry`, each field that changes gets its own row in `player_action_logs`.

**Example: `/setup` command**

User fills out:
- Player Name: "TestUser"
- BattleTag: "TestUser#1234"
- Alt Name 1: "AltName1"
- Alt Name 2: "AltName2"
- Country: US
- Region: NAE

This creates **7 separate log entries**:

```
1. player_name:      None → "TestUser"
2. battletag:        None → "TestUser#1234"
3. alt_player_name_1: None → "AltName1"
4. alt_player_name_2: None → "AltName2"
5. country:          None → "US"
6. region:           None → "NAE"
7. completed_setup:  False → True
```

### Timestamp Tracking

Every change also updates the `updated_at` timestamp in the `players` table, providing an additional layer of tracking.

## Implementation Details

### In `user_info_service.py`

The `update_player()` method has a `log_changes` parameter:

```python
def update_player(
    self,
    discord_uid: int,
    player_name: Optional[str] = None,
    battletag: Optional[str] = None,
    alt_player_name_1: Optional[str] = None,
    alt_player_name_2: Optional[str] = None,
    country: Optional[str] = None,
    region: Optional[str] = None,
    log_changes: bool = False  # Enable granular logging
) -> bool:
```

When `log_changes=True`:
1. Fetches old player data before update
2. Performs the update
3. Compares each field: old value vs new value
4. Logs only fields that actually changed
5. Each change = one row in `player_action_logs`

### Commands Using Granular Logging

| Command | Fields Logged | Example Rows |
|---------|---------------|--------------|
| `/setup` | player_name, battletag, alt_player_name_1, alt_player_name_2, country, region, completed_setup | 6-7 rows |
| `/setcountry` | country | 1 row |

## Database Schema

### player_action_logs Table

```sql
CREATE TABLE player_action_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_uid     INTEGER NOT NULL,
    player_name     TEXT NOT NULL,
    setting_name    TEXT NOT NULL,        -- Which field changed
    old_value       TEXT,                 -- Previous value
    new_value       TEXT,                 -- New value
    changed_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changed_by      TEXT DEFAULT 'player'
)
```

### Sample Data

After a user runs `/setup`:

| id | discord_uid | player_name | setting_name | old_value | new_value | changed_at | changed_by |
|----|-------------|-------------|--------------|-----------|-----------|------------|------------|
| 1 | 123456 | TestUser | player_name | None | TestUser | 2025-10-04 01:00:00 | player |
| 2 | 123456 | TestUser | battletag | None | TestUser#1234 | 2025-10-04 01:00:00 | player |
| 3 | 123456 | TestUser | alt_player_name_1 | None | AltName1 | 2025-10-04 01:00:00 | player |
| 4 | 123456 | TestUser | country | None | US | 2025-10-04 01:00:00 | player |
| 5 | 123456 | TestUser | region | None | NAE | 2025-10-04 01:00:00 | player |
| 6 | 123456 | TestUser | completed_setup | False | True | 2025-10-04 01:00:00 | player |

Later, user runs `/setcountry` to change from US to CA:

| id | discord_uid | player_name | setting_name | old_value | new_value | changed_at | changed_by |
|----|-------------|-------------|--------------|-----------|-----------|------------|------------|
| 7 | 123456 | TestUser | country | US | CA | 2025-10-04 02:00:00 | player |

## Benefits

1. **Detailed Audit Trail**: See exactly what changed and when
2. **Granular Analysis**: Query specific field changes
3. **Change History**: Track evolution of user profiles over time
4. **Debugging**: Identify when specific fields were modified
5. **Compliance**: Detailed logs for data modification tracking

## Querying Logs

### Get All Changes for a User

```python
from src.backend.db.db_reader_writer import DatabaseReader

reader = DatabaseReader()
logs = reader.get_player_action_logs(discord_uid=123456, limit=100)

for log in logs:
    print(f"{log['setting_name']}: {log['old_value']} → {log['new_value']}")
```

### Get Recent Changes Across All Users

```python
# Get last 50 changes across all users
logs = reader.get_player_action_logs(discord_uid=None, limit=50)
```

### SQL Query Examples

```sql
-- Get all country changes
SELECT * FROM player_action_logs 
WHERE setting_name = 'country' 
ORDER BY changed_at DESC;

-- Count changes per user
SELECT discord_uid, COUNT(*) as change_count 
FROM player_action_logs 
GROUP BY discord_uid 
ORDER BY change_count DESC;

-- Get changes in last 24 hours
SELECT * FROM player_action_logs 
WHERE changed_at > datetime('now', '-1 day') 
ORDER BY changed_at DESC;
```

## Code Example

### Complete Setup Flow

```python
from src.backend.services.user_info_service import UserInfoService

service = UserInfoService()

# This will create 7 log entries (one per field)
service.complete_setup(
    discord_uid=123456,
    player_name="TestUser",
    battletag="TestUser#1234",
    alt_player_name_1="AltName1",
    alt_player_name_2="AltName2",
    country="US",
    region="NAE"
)

# Check the logs
logs = service.get_player_action_logs(discord_uid=123456)
print(f"Total changes logged: {len(logs)}")  # Output: 7
```

### Update Country Flow

```python
# This will create 1 log entry (country only)
service.update_country(123456, "CA")

# Check the latest log
logs = service.get_player_action_logs(discord_uid=123456, limit=1)
print(f"{logs[0]['setting_name']}: {logs[0]['old_value']} → {logs[0]['new_value']}")
# Output: country: US → CA
```

## Performance Considerations

- **Write Performance**: Each field change = 1 INSERT operation
  - `/setup` with 6 fields = 6 INSERT operations + 1 UPDATE (players table)
  - This is intentional for detailed tracking
- **Read Performance**: Index on `discord_uid` for fast user-specific queries
- **Storage**: Each log entry is small (~100 bytes), negligible overhead

## Future Enhancements

Potential future additions:
- Admin-initiated changes (`changed_by = 'admin'`)
- System-automated changes (`changed_by = 'system'`)
- Reason/note field for changes
- Rollback functionality using log history

---

**Summary**: Every field change creates its own row in `player_action_logs`, providing a complete, granular audit trail of all user profile modifications.

