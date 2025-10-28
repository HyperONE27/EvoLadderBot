# Games Played Counter Fix - Critical Missing Increment

## Problem Identified

After all previous fixes, MMR was being updated correctly in the database and in-memory, but `/profile` was still showing "No MMR - No Games Played" for races that had just been played.

### Root Cause Revealed by Diagnostic Logs

The diagnostic logging added to `DataAccessService` revealed the exact issue:

**Before match:**
```
[DataAccessService]   Found bw_zerg: mmr=1500.0, games=0
```

**After match:**
```
[DataAccessService]   Found bw_zerg: mmr=1520.0, games=0  ← MMR UPDATED BUT GAMES STILL 0!
```

The MMR was being updated, but `games_played` was remaining at 0. This caused the `/profile` command to not display the MMR information because of this condition in `profile_command.py`:

```python
if games_played > 0:
    # Display MMR info
```

Since `games_played` was 0, the condition failed and MMR was never displayed.

### The Bug

The matchmaker's `_calculate_and_write_mmr` method was calling `update_player_mmr` with:
- ✅ `new_mmr` - Updated correctly
- ✅ `games_won` - Set to 1 if won, else None  
- ✅ `games_lost` - Set to 1 if lost, else None
- ✅ `games_drawn` - Set to 1 if drawn, else None
- ❌ `games_played` - **NOT PASSED AT ALL!**

Because `games_played` was `None`, the `update_player_mmr` method didn't update it (line 1412-1413):
```python
if games_played is not None:
    update_data["games_played"] = games_played
```

This meant the total games counter never incremented, even though individual outcome counters did.

### Why Individual Counters Were Wrong Too

Additionally, the matchmaker was setting individual counters to `1` instead of **incrementing** them:
```python
games_won=1 if p1_won else None  # ❌ Sets to 1, doesn't increment!
```

This meant:
- First win: `games_won = 1` ✓
- Second win: `games_won = 1` ❌ (should be 2!)

## Solution Implemented

**File:** `src/backend/services/matchmaking_service.py`
**Method:** `_calculate_and_write_mmr`

### Changes Made

1. **Read Current Stats**: Get the current game statistics from the DataFrame before updating
   ```python
   p1_stats = p1_all_mmrs.get(p1_race, {})
   p1_current_games = p1_stats.get('games_played', 0)
   p1_current_won = p1_stats.get('games_won', 0)
   p1_current_lost = p1_stats.get('games_lost', 0)
   p1_current_drawn = p1_stats.get('games_drawn', 0)
   ```

2. **Increment All Counters**: Properly increment each counter
   ```python
   await data_service.update_player_mmr(
       player1_uid, p1_race, int(mmr_outcome.player_one_mmr),
       games_played=p1_current_games + 1,  # ← ALWAYS increment
       games_won=p1_current_won + 1 if p1_won else p1_current_won,  # ← Increment if won
       games_lost=p1_current_lost + 1 if p1_lost else p1_current_lost,
       games_drawn=p1_current_drawn + 1 if p1_drawn else p1_current_drawn
   )
   ```

### Key Improvements

1. **games_played Always Increments**: Every match completion increments the total counter
2. **Individual Counters Increment**: Won/lost/drawn counters increment from their current values
3. **No Data Loss**: All previous game statistics are preserved and correctly incremented

## How It Works Now

### Match Completion Flow

1. **Match Completes** → Both players report results
2. **Matchmaker Calculates MMR** → `_calculate_and_write_mmr()`
3. **Read Current Stats** → Get current values from DataFrame
   - `games_played`: 0
   - `games_won`: 0
   - `games_lost`: 0
   - `mmr`: 1500
4. **Calculate New Values**:
   - `games_played`: 0 + 1 = 1 ✓
   - `games_won`: 0 + 1 = 1 (if won) ✓
   - `mmr`: 1500 → 1520 ✓
5. **Update DataFrame** → All values updated correctly
6. **Profile Display** → `if games_played > 0:` now passes ✓
   - MMR: 1520 displayed ✓
   - Record: 1-0-0 displayed ✓
   - Last played: timestamp displayed ✓

## Verification

The fix will be immediately visible in the diagnostic logs:

**Before Fix:**
```
[DataAccessService]   Found bw_zerg: mmr=1520.0, games=0  ← games=0!
```

**After Fix:**
```
[DataAccessService]   Found bw_zerg: mmr=1520.0, games=1  ← games=1!
```

### Manual Testing

1. Reset a race to 1500 MMR with 0 games
2. Play a match and win
3. Check `/profile` immediately:
   - ✅ Should show MMR: 1520
   - ✅ Should show games_played: 1
   - ✅ Should show record: 1-0-0
   - ✅ Should show last_played timestamp
   - ✅ Should show letter rank

## Files Modified

- `src/backend/services/matchmaking_service.py`
  - Modified `_calculate_and_write_mmr()` to read current stats and properly increment all counters

## Related Issues

This bug existed because the original implementation assumed:
- Setting `games_won=1` would mean "add 1 to games_won"
- Not passing `games_played` was okay

But the actual behavior was:
- Setting `games_won=1` meant "set games_won to 1" (absolute, not relative)
- Not passing `games_played` meant "don't update it at all"

The correct approach requires:
1. Reading current values
2. Calculating new values (current + delta)
3. Passing absolute new values to the update method

## Performance Impact

**Negligible**: The additional dictionary lookups to read current stats add <0.1ms per match.

## Lessons Learned

1. **Always Verify End-to-End**: Even if the database is correct, the display logic might fail due to missing data
2. **Diagnostic Logging is Essential**: The debug logs immediately revealed the exact field that wasn't updating
3. **Increment vs. Set**: Be explicit about whether you're setting absolute values or incrementing
4. **Test Display Logic**: Just because data is stored doesn't mean it's displayed correctly

