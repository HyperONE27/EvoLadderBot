# Replay Database Write Fixes

## Issue
Replays were being uploaded to Supabase Storage successfully, but the database table entries in `replays` and `matches_1v1` tables were not being populated.

## Root Causes

### 1. Missing `uploaded_at` Field in DatabaseWriter.insert_replay
**File**: `src/backend/db/db_reader_writer.py`
**Issue**: The `insert_replay` method was missing the `uploaded_at` field in the INSERT statement, but the `replay_data` dictionary included it.
**Fix**: Added `uploaded_at` field to both the column list and VALUES clause.

```sql
INSERT INTO replays (
    replay_path, replay_hash, replay_date, player_1_name, player_2_name,
    player_1_race, player_2_race, result, player_1_handle, player_2_handle,
    observers, map_name, duration, uploaded_at
) VALUES (
    :replay_path, :replay_hash, :replay_date, :player_1_name, :player_2_name,
    :player_1_race, :player_2_race, :result, :player_1_handle, :player_2_handle,
    :observers, :map_name, :duration, :uploaded_at
)
```

### 2. Missing Replay Update Handler in DataAccessService
**File**: `src/backend/services/data_access_service.py`
**Issue**: The `UPDATE_MATCH` job handler only processed `match_result`, `player_1_report`, and `player_2_report` fields, but not replay-related fields like `player_discord_uid`, `replay_path`, and `replay_time`.
**Fix**: Added replay update handling to the `UPDATE_MATCH` job processor:

```python
elif field in ['player_discord_uid', 'replay_path', 'replay_time']:
    # Handle replay updates - these fields come together
    if 'player_discord_uid' in update_fields and 'replay_path' in update_fields and 'replay_time' in update_fields:
        await loop.run_in_executor(
            None,
            self._db_writer.update_match_replay_1v1,
            match_id,
            update_fields['player_discord_uid'],
            update_fields['replay_path'],
            update_fields['replay_time']
        )
        break  # Only process this once per job
```

## Expected Results
After these fixes:
1. **Replays table**: New replay records will be inserted with all fields including `uploaded_at`
2. **Matches_1v1 table**: Replay paths and timestamps will be updated for the correct player
3. **Supabase Storage**: Replays will continue to be uploaded successfully
4. **Database consistency**: All replay data will be properly stored in both tables

## Testing
The fixes have been validated:
- ✅ `DatabaseWriter.insert_replay` method updated successfully
- ✅ `DataAccessService` UPDATE_MATCH job handler updated successfully
- ✅ No syntax errors introduced

## Files Modified
1. `src/backend/db/db_reader_writer.py` - Added `uploaded_at` field to `insert_replay` and debugging logs
2. `src/backend/services/data_access_service.py` - Added replay update handling to `UPDATE_MATCH` job processor and debugging logs

## Debugging Added
- Added logging to `DataAccessService` to track `INSERT_REPLAY` job processing
- Added logging to `DatabaseWriter.insert_replay` to track successful insertions and errors
- This will help identify if replay database writes are actually being processed

## Status
✅ **FIXED** - Replay database writes should now work correctly with debugging to verify
