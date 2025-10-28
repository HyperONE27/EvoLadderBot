# Two-Week Inactivity Filter Implementation

## Overview

This document describes the implementation of a two-week inactivity filter for the ranking system. Players who have not completed a match within the last 14 days are now marked as "Unranked" (U-rank) rather than receiving a letter rank (S, A, B, C, D, E, or F).

## Motivation

The inactivity filter ensures that:
1. **Leaderboard reflects active players**: Only players who are currently active participate in the ranking distribution
2. **Fair competition**: Prevents long-inactive players from occupying rank positions
3. **Accurate representation**: Shows the current competitive landscape, not historical performance

## Implementation Details

### Phase 1: Data Source Correction

**File Modified**: `src/backend/services/data_access_service.py`

**Changes**:
- Removed the dynamic calculation of `last_played` from match aggregation (lines 1043-1076)
- The `get_leaderboard_dataframe()` method now relies solely on the authoritative `last_played` column from the `mmrs_1v1` table
- This column is updated automatically whenever a match is completed via `DatabaseWriter.update_mmr_after_match()`

**Why This Matters**:
- The database maintains the true `last_played` timestamp for each player-race combination
- Dynamically calculating it from matches was redundant and could cause inconsistencies
- The database value is updated by `get_timestamp()` which provides timezone-aware UTC timestamps

### Phase 2: Inactivity Filter Logic

**File Modified**: `src/backend/services/ranking_service.py`

**Changes**:
1. Added imports for datetime handling:
   ```python
   from datetime import datetime, timedelta, timezone
   ```

2. Modified the `refresh_rankings()` method to filter based on three conditions:
   - **Condition 1**: Player must have `games_played > 0`
   - **Condition 2**: Player must have a valid `last_played` timestamp (not `None`)
   - **Condition 3**: The `last_played` timestamp must be within the last 2 weeks

**Algorithm**:
```python
inactivity_threshold = datetime.now(timezone.utc) - timedelta(weeks=2)

for entry in all_mmr_data:
    games_played = entry.get("games_played", 0)
    last_played_str = entry.get("last_played")
    
    is_eligible_for_ranking = True
    
    if games_played == 0:
        is_eligible_for_ranking = False
    elif last_played_str is None:
        is_eligible_for_ranking = False
    else:
        try:
            last_played_datetime = datetime.fromisoformat(last_played_str)
            if last_played_datetime < inactivity_threshold:
                is_eligible_for_ranking = False
        except (ValueError, TypeError):
            is_eligible_for_ranking = False
            # Log warning about malformed timestamp
    
    # Append to ranked_entries or unranked_entries accordingly
```

**Error Handling**:
- Malformed timestamps are caught and logged
- Players with invalid timestamps are treated as inactive (unranked)
- This prevents crashes and ensures system stability

## Testing

### Test Suite: `tests/test_inactivity_ranking_filter.py`

Four comprehensive tests verify the implementation:

1. **`test_ranking_service_filters_inactive_players`**
   - Tests basic filtering with various activity states
   - Verifies active players (1-13 days ago) are ranked
   - Verifies inactive players (15-30 days ago) are unranked
   - Verifies edge cases (0 games, no timestamp) are unranked

2. **`test_exact_two_week_boundary`**
   - Tests behavior at the exact 2-week boundary
   - Confirms players at exactly 14 days are still ranked
   - Confirms players at 14 days + 1 minute are unranked

3. **`test_malformed_timestamp_handling`**
   - Tests graceful handling of invalid timestamps
   - Ensures system doesn't crash on bad data
   - Verifies invalid timestamps result in unranked status

4. **`test_last_played_column_from_database`**
   - Verifies that `last_played` comes from the database
   - Ensures the correct data source is being used

### Manual Demonstration: `tests/manual_test_inactivity_filter.py`

A realistic demonstration script showing:
- 11 players with varying activity levels
- Clear visualization of who gets ranked vs unranked
- Summary statistics and observations

**Sample Output**:
```
Ranked Players (active within 2 weeks): 5
Unranked Players (inactive or new): 6

Player Activity Examples:
  • 6 hours ago   → RANKED (B-rank)
  • 13 days ago   → RANKED (E-rank)
  • 15 days ago   → UNRANKED (U-rank)
  • 30 days ago   → UNRANKED (U-rank)
```

## Database Schema

The `mmrs_1v1` table includes:
```sql
CREATE TABLE mmrs_1v1 (
    ...
    last_played TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    ...
);
```

This column is automatically updated by:
- `DatabaseWriter.create_or_update_mmr_1v1()` - Initial creation or full update
- `DatabaseWriter.update_mmr_after_match()` - After each match completion

Both methods use `get_timestamp()` which returns timezone-aware UTC timestamps in ISO 8601 format.

## Impact on System

### Performance
- **No additional database queries**: Uses existing data already loaded in memory
- **Minimal computational overhead**: Single datetime comparison per player-race
- **Efficient parsing**: Python's `datetime.fromisoformat()` is optimized for ISO 8601

### User Experience
- **More accurate rankings**: Only active players compete for rank positions
- **Encourages activity**: Players must play regularly to maintain their rank
- **Clear feedback**: Unranked status (U-rank) clearly indicates inactivity

### Leaderboard Distribution
- **Dynamic population**: Rank distribution (S=1%, A=7%, etc.) applies only to active players
- **Stable percentages**: The relative distribution remains consistent
- **No dead weight**: Inactive players don't occupy rank slots

## Configuration

The inactivity threshold is currently hardcoded as:
```python
inactivity_threshold = datetime.now(timezone.utc) - timedelta(weeks=2)
```

**Future Enhancement**: This could be made configurable via `src/backend/core/config.py`:
```python
INACTIVITY_THRESHOLD_DAYS = 14  # Two weeks
```

## Edge Cases Handled

1. **Brand new players** (0 games): Unranked
2. **Missing `last_played`**: Unranked (treated as inactive)
3. **Malformed timestamps**: Unranked with logged warning
4. **Exact boundary** (14 days): Still ranked (uses `<` not `<=`)
5. **Timezone differences**: All timestamps are UTC, ensuring consistency

## Files Modified

1. `src/backend/services/data_access_service.py`
   - Removed dynamic `last_played` calculation
   - Lines removed: ~34 lines (1043-1076)

2. `src/backend/services/ranking_service.py`
   - Added datetime imports
   - Replaced simple game count filter with comprehensive inactivity filter
   - Lines added: ~30 lines
   - Updated logging message

## Files Created

1. `tests/test_inactivity_ranking_filter.py`
   - Comprehensive test suite with 4 test cases
   - ~250 lines

2. `tests/manual_test_inactivity_filter.py`
   - Demonstration script
   - ~150 lines

3. `docs/INACTIVITY_FILTER_IMPLEMENTATION.md`
   - This document

## Verification

All tests pass:
```bash
pytest tests/test_inactivity_ranking_filter.py -v
# 4 passed in 0.43s
```

Manual demonstration produces expected output showing clear separation between active and inactive players.

## Future Considerations

1. **Configurable threshold**: Move the 2-week value to configuration
2. **Grace period**: Consider a warning state (e.g., "Inactive Soon") for players approaching the threshold
3. **Activity notifications**: Notify players when they're about to become inactive
4. **Reactivation**: Special handling for returning players after long absences
5. **Statistics tracking**: Log inactivity trends over time for analytics

## Conclusion

The two-week inactivity filter has been successfully implemented and tested. It correctly identifies and excludes inactive players from the ranking calculation while maintaining system stability and performance. The implementation follows the existing codebase patterns and integrates seamlessly with the current architecture.

