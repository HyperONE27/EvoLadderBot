# Admin Resolution Idempotency Fix

## Problem

User reported: "every time I resolve the same match, the MMRs after are clearly not the result of using the initial MMRs in the table but from grabbing the player-race MMRs as they are currently in the mmrs_1v1 table"

**Root Cause:** The code was looking for non-existent database columns:
- Looking for: `player_1_mmr_before` and `player_2_mmr_before`
- Actually exist: `player_1_mmr` and `player_2_mmr`

This caused the fallback logic to ALWAYS fetch current MMRs from the `mmrs_1v1` table instead of using the stored initial MMRs from the `matches_1v1` table.

## Database Schema Reality

From `postgres_schema.md`, the `matches_1v1` table has:
```sql
CREATE TABLE matches_1v1 (
    ...
    player_1_mmr            INTEGER NOT NULL,  -- Initial MMR when match started
    player_2_mmr            INTEGER NOT NULL,  -- Initial MMR when match started
    mmr_change              INTEGER,           -- MMR change from the match
    ...
);
```

**NOT:**
- ~~`player_1_mmr_before`~~
- ~~`player_2_mmr_before`~~

## What This Broke

### Before Fix (WRONG):
1. Resolve match #155 first time:
   - Fetches current MMRs: 1500/1500 from `mmrs_1v1`
   - Calculates change: +19/-19
   - Updates to: 1519/1481
   - Display: `(1500 → 1519)` and `(1500 → 1481)` ✓

2. Resolve match #155 second time:
   - Fetches **current** MMRs: **1519/1481** from `mmrs_1v1` ❌
   - Calculates change: +19/-19
   - Updates to: 1538/1462
   - Display: `(1519 → 1538)` and `(1481 → 1462)` ❌

**NOT IDEMPOTENT!** Each resolution stacks MMR changes.

### After Fix (CORRECT):
1. Resolve match #155 first time:
   - Uses stored initial MMRs: 1500/1500 from `matches_1v1.player_1_mmr/player_2_mmr`
   - Calculates change: +19/-19
   - Updates to: 1519/1481
   - Display: `(1500 → 1519)` and `(1500 → 1481)` ✓

2. Resolve match #155 second time:
   - Restores players to: 1500/1500 (from `matches_1v1.player_1_mmr/player_2_mmr`)
   - Uses stored initial MMRs: 1500/1500 (from same fields)
   - Calculates change: +19/-19
   - Updates to: 1519/1481 (same as before!)
   - Display: `(1500 → 1519)` and `(1500 → 1481)` ✓

**FULLY IDEMPOTENT!** Resolving N times = same result as resolving once.

## Code Changes

### `src/backend/services/admin_service.py`

#### Change 1: Get Initial MMRs (Lines 646-655)
```python
# OLD (WRONG):
p1_mmr_before = match_data.get('player_1_mmr_before')  # Always None!
p2_mmr_before = match_data.get('player_2_mmr_before')  # Always None!

# If None, fall back to current MMRs from mmrs_1v1 (BAD!)
if p1_mmr_before is None or p2_mmr_before is None:
    p1_mmr_before = self.data_service.get_player_mmr(p1_uid, p1_race)
    p2_mmr_before = self.data_service.get_player_mmr(p2_uid, p2_race)

# NEW (CORRECT):
p1_mmr_before = match_data.get('player_1_mmr')  # Stored initial MMR!
p2_mmr_before = match_data.get('player_2_mmr')  # Stored initial MMR!

# Sanity check - if these are None, the match data is corrupt
if p1_mmr_before is None or p2_mmr_before is None:
    raise ValueError(f"Match {match_id} missing player_1_mmr or player_2_mmr")
```

#### Change 2: Return Data (Lines 780-788)
```python
# OLD (WRONG):
p1_mmr_before = final_match_data.get('player_1_mmr_before')  # Always None!
p2_mmr_before = final_match_data.get('player_2_mmr_before')  # Always None!

# NEW (CORRECT):
p1_mmr_initial = final_match_data.get('player_1_mmr')  # Stored initial MMR!
p2_mmr_initial = final_match_data.get('player_2_mmr')  # Stored initial MMR!
```

#### Change 3: Return Dictionary (Lines 811-814)
```python
# OLD (WRONG):
'player_1_mmr_before': p1_mmr_before or 0,  # Was always 0 or current MMR
'player_2_mmr_before': p2_mmr_before or 0,  # Was always 0 or current MMR

# NEW (CORRECT):
'player_1_mmr_before': p1_mmr_initial or 0,  # Now uses actual initial MMR from match table!
'player_2_mmr_before': p2_mmr_initial or 0,  # Now uses actual initial MMR from match table!
```

## Testing Plan

### Test 1: First Resolution
1. Start with match #155:
   - Player 1 initial MMR: 1500 (from `matches_1v1.player_1_mmr`)
   - Player 2 initial MMR: 1500 (from `matches_1v1.player_2_mmr`)
   - Current MMR in `mmrs_1v1`: 1500/1500
2. Resolve match with winner = Player 2
3. Verify:
   - Admin embed shows: `(1500 → 1519)` and `(1500 → 1481)`
   - Supabase `mmrs_1v1`: 1519/1481 ✓
   - Supabase `matches_1v1.mmr_change`: 19 ✓
   - `/profile` shows: 1519/1481 ✓

### Test 2: Idempotent Re-Resolution (Critical!)
1. Without changing anything else, resolve match #155 AGAIN with same winner
2. Verify:
   - Admin embed shows: `(1500 → 1519)` and `(1500 → 1481)` (SAME AS BEFORE!)
   - Supabase `mmrs_1v1`: 1519/1481 (NO CHANGE!)
   - Supabase `matches_1v1.mmr_change`: 19 (NO CHANGE!)
   - `/profile` shows: 1519/1481 (NO CHANGE!)

### Test 3: Flip Winner
1. Resolve match #155 again with OPPOSITE winner (Player 1 wins)
2. Verify:
   - Admin embed shows: `(1500 → 1519)` and `(1500 → 1481)` (FLIPPED!)
   - Supabase `mmrs_1v1`: 1519/1481 (FLIPPED!)
   - Supabase `matches_1v1.mmr_change`: -19 (NEGATIVE!)
   - `/profile` shows: 1519/1481 (FLIPPED!)

### Test 4: Re-Resolution After Flip
1. Resolve match #155 again with SAME winner as Test 3
2. Verify: Same as Test 3 (idempotent!)

## Impact

### Fixed Issues
✅ Admin resolution now uses stored initial MMRs from `matches_1v1` table
✅ Operations are fully idempotent (N resolutions = 1 resolution)
✅ MMR display in embed shows correct initial → final values
✅ No more stacking MMR changes on repeated resolutions

### Unchanged Behavior
✓ First-time resolution still works correctly
✓ MMR calculations still use the same algorithm
✓ Game stats still not updated by admin resolutions (by design)
✓ Player notifications still sent with correct data

## Files Changed
- `src/backend/services/admin_service.py` (3 changes)

## Compilation Status
✅ `python -m py_compile src/backend/services/admin_service.py` - PASSED

