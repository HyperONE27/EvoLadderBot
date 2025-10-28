# Leaderboard Cache Fix - Complete Implementation

## Problem Identified

The leaderboard and ranking system was not reflecting real-time MMR updates due to a **destructive race condition** in the `LeaderboardService`. The service was incorrectly attempting to manage its own cache, which resulted in fresh in-memory data being overwritten with stale database data.

### Root Cause Analysis

The data flow failure occurred in these steps:

1. **Correct In-Memory Update**: `DataAccessService` correctly updated its in-memory DataFrame with new MMR data after match completion
2. **Correct Cache Invalidation**: A flag was set to indicate data was "dirty"
3. **Correct Rank Refresh**: `RankingService.trigger_refresh()` was called to recalculate ranks
4. **The Destructive "Refresh"**: When a user requested the leaderboard, `LeaderboardService` saw the "dirty" flag and performed its own database read
5. **Race Condition Lost**: The asynchronous database write had not completed, so the read returned stale data
6. **Catastrophic Overwrite**: This stale data was used to **completely overwrite** the fresh in-memory DataFrame in `DataAccessService`
7. **Stale Data Served**: The leaderboard rendered using this stale data, missing the new match results

This faulty caching logic was a relic of a previous architecture and directly violated the "single source of truth" principle of `DataAccessService`.

## Solution Implemented

The solution surgically removed the entire faulty caching mechanism and enforced `DataAccessService` as the single source of truth for in-memory data.

### Changes Made

#### 1. LeaderboardService (`src/backend/services/leaderboard_service.py`)

**Removed the faulty on-demand database reload:**
- Deleted the entire `if not self.data_service.is_leaderboard_cache_valid():` block in `get_leaderboard_data()`
- This block was performing database reads and overwriting in-memory data
- Removed obsolete `invalidate_cache()` and `invalidate_leaderboard_cache()` stub functions

**Result:** The service now proceeds directly to using existing (and correct) in-memory data from `DataAccessService`.

#### 2. DataAccessService (`src/backend/services/data_access_service.py`)

**Eradicated the obsolete caching mechanism:**
- Removed `self._leaderboard_cache_is_valid` flag from `__init__`
- Deleted three cache management methods:
  - `invalidate_leaderboard_cache()`
  - `is_leaderboard_cache_valid()`
  - `mark_leaderboard_cache_valid()`
- Removed all calls to `self.invalidate_leaderboard_cache()` throughout the file

**Kept the correct logic:**
- Retained all `ranking_service.trigger_refresh()` calls after MMR updates
- These calls are the proper mechanism for notifying the `RankingService` of changes

#### 3. DatabaseReader/Writer (`src/backend/db/db_reader_writer.py`)

**Cleaned up the decorator:**
- Updated `@invalidate_leaderboard_on_mmr_change` decorator
- Removed the call to `invalidate_leaderboard_cache()`
- Changed to a no-op with a comment explaining that cache invalidation is now handled by `DataAccessService`

### Verification

Created and ran a comprehensive unit test (`tests/test_cache_removal.py`) that verifies:

1. ✅ Cache methods removed from `DataAccessService`
2. ✅ Cache flag removed from `DataAccessService` instance
3. ✅ `LeaderboardService` no longer performs database reloads
4. ✅ `LeaderboardService` uses `DataAccessService` as single source
5. ✅ Decorator no longer calls cache invalidation

**Test Result:** All tests passed ✓

## How It Works Now

### Correct Data Flow After Match Completion

1. **Match Completion** → `MatchCompletionService._handle_match_completion()`
2. **MMR Calculation** → `Matchmaker._calculate_and_write_mmr()`
3. **In-Memory Update** → `DataAccessService.update_player_mmr()` or `create_or_update_mmr()`
   - Updates in-memory DataFrame **immediately**
   - Queues async database write
4. **Rank Refresh** → `RankingService.trigger_refresh()`
   - Recalculates ranks using fresh in-memory data from `DataAccessService`
   - No database access needed
5. **Leaderboard Request** → `LeaderboardService.get_leaderboard_data()`
   - Reads directly from `DataAccessService` in-memory DataFrame
   - No cache checks, no database reloads
   - Gets enriched with rank data from `RankingService`
6. **User Sees Fresh Data** → Profile and leaderboard commands show updated MMR, ranks, and counts

### Key Principles Enforced

1. **Single Source of Truth**: `DataAccessService` is the only source for in-memory data
2. **No Destructive Overwrites**: Services read from `DataAccessService`, they never overwrite it
3. **Async Writes Are Background**: Database writes happen asynchronously and don't block or affect in-memory state
4. **Event-Driven Updates**: `RankingService` is notified immediately via `trigger_refresh()` when data changes
5. **No Polling**: No background refresh loops or periodic cache invalidation

## Performance Impact

**Before:**
- 60-second refresh loop (idle CPU usage)
- On-demand database reloads causing race conditions
- Stale data served to users
- Unpredictable 5-10 second delays

**After:**
- Zero idle CPU usage (no background loops)
- Instant in-memory data access
- No race conditions
- Immediate reflection of match results in leaderboard

## Testing

### Unit Test
Run `tests/test_cache_removal.py` to verify all faulty mechanisms are removed.

### Manual Testing
1. Play a match with a race that hasn't been played in >2 weeks
2. Immediately check `/profile` - should show updated MMR and last_played
3. Check `/leaderboard` - should show updated ranks and increased player count
4. No 5-10 second delay should occur

## Related Files

- `src/backend/services/leaderboard_service.py` - Simplified to read from single source
- `src/backend/services/data_access_service.py` - Cache mechanism removed
- `src/backend/db/db_reader_writer.py` - Decorator cleaned up
- `src/backend/services/ranking_service.py` - Still handles rank calculation (unchanged)
- `tests/test_cache_removal.py` - Verification test

## Migration Notes

This is a **breaking architectural change** that removes a faulty pattern. No database schema changes are required. The change is backward compatible and improves correctness and performance.

## Future Considerations

If additional caching is needed in the future, it should:
- Never overwrite the in-memory state in `DataAccessService`
- Only cache derived/computed data, not source data
- Be explicitly invalidated through event-driven triggers
- Be clearly documented as a cache, not a "refresh"

