# Admin Invalidate Match Fix

## Problem

The `/admin resolve` command would crash when the admin selected the "Invalidate Match" option with the error:

```
ValueError: result must be 0, 1, or 2
```

### Root Cause

When a match is invalidated, the system sets `match_result=-1` (aborted). However, the code was attempting to calculate MMR change for ALL resolutions, including invalidated matches:

```python
# BEFORE (BROKEN):
# Step 6: Calculate MMR for all resolutions
mmr_change = mmr_service.calculate_mmr_change(
    p1_mmr_before,
    p2_mmr_before,
    new_result  # This is -1 for invalidate!
)

# Step 7: Apply MMR (only if not invalidate)
if resolution != 'invalidate':
    # Apply MMR changes
else:
    mmr_change = 0  # Too late - already crashed!
```

**Problem:** The MMR service only accepts `result ∈ {0, 1, 2}` (draw, p1 win, p2 win), but invalidate uses `result=-1`.

---

## Solution

Moved the `resolution != 'invalidate'` check BEFORE the MMR calculation, so invalidated matches skip MMR calculation entirely:

```python
# AFTER (FIXED):
# Step 6: Calculate MMR only for valid resolutions
if resolution != 'invalidate':
    mmr_change = mmr_service.calculate_mmr_change(
        p1_mmr_before,
        p2_mmr_before,
        new_result  # Only called with 0, 1, or 2
    )
    
    # Apply MMR changes
    # ... update player MMRs ...
else:
    # Match invalidated - no MMR changes
    mmr_change = 0
    print(f"Match invalidated (result={new_result}), no MMR changes")
```

---

## Changes Made

**File:** `src/backend/services/admin_service.py`

**Location:** Lines 693-738 (in `_resolve_terminal_match` method)

### Before:
1. Calculate MMR change (crashes if result=-1)
2. Check if resolution is 'invalidate'
3. Apply MMR changes (conditional)

### After:
1. Check if resolution is 'invalidate' FIRST
2. Calculate MMR change ONLY if not invalidate
3. Apply MMR changes (or skip with mmr_change=0)

---

## Behavior

### Invalidate Match Resolution
- **Result:** `match_result=-1` (aborted)
- **MMR Change:** 0 (no MMR calculation)
- **Player MMRs:** Unchanged
- **Match State:** Marked as aborted in database

### Normal Match Resolution
- **Result:** 0 (draw), 1 (p1 wins), or 2 (p2 wins)
- **MMR Change:** Calculated based on original MMRs
- **Player MMRs:** Updated idempotently
- **Match State:** Marked as completed in database

---

## Testing

### Test Case 1: Invalidate Fresh Match
1. Start match between Player A and Player B
2. Admin runs `/admin resolve` with "Invalidate Match"
3. **Expected:**
   - Match set to `match_result=-1`
   - Both player MMRs unchanged
   - No MMR change calculated or stored
   - No error thrown ✅

### Test Case 2: Invalidate Conflicted Match
1. Player A reports: "I won"
2. Player B reports: "I won"
3. Match now in conflict (`match_result=-2`)
4. Admin runs `/admin resolve` with "Invalidate Match"
5. **Expected:**
   - Match set to `match_result=-1`
   - Both player MMRs restored to original, then unchanged
   - `mmr_change=0` stored in database
   - No error thrown ✅

### Test Case 3: Normal Resolution (Sanity Check)
1. Match in conflict
2. Admin runs `/admin resolve` with "Player 1 Won"
3. **Expected:**
   - Match set to `match_result=1`
   - MMR calculated from original MMRs
   - MMRs updated for both players
   - Changes reflected in database ✅

---

## Compilation Status

```bash
python -m py_compile src/backend/services/admin_service.py
```

**Exit Code: 0** ✅

---

## Related Code

### Match Result Codes
```python
-1 = ABORTED (invalidated or player aborted)
-2 = CONFLICT (players disagree)
 0 = DRAW
 1 = PLAYER 1 WON
 2 = PLAYER 2 WON
```

### MMR Service Validation
```python
# src/backend/services/mmr_service.py
def _calculate_actual_scores(self, result: int):
    if result == 0:
        return 0.5, 0.5  # Draw
    elif result == 1:
        return 1.0, 0.0  # P1 wins
    elif result == 2:
        return 0.0, 1.0  # P2 wins
    else:
        raise ValueError("result must be 0, 1, or 2")  # This was being triggered!
```

---

## Impact

### Before Fix
- ❌ Invalidating a match would crash the bot
- ❌ Admin would see error message
- ❌ Match state would be partially updated (result=-1 but not saved)
- ❌ Players would not receive notifications

### After Fix
- ✅ Invalidating a match works correctly
- ✅ Admin sees success confirmation
- ✅ Match state fully updated (`match_result=-1`, `mmr_change=0`)
- ✅ Players receive "match aborted" notifications
- ✅ No MMR calculation attempted for aborted matches

---

## Files Modified

1. `src/backend/services/admin_service.py` - Fixed `_resolve_terminal_match` method

**Total Lines Changed:** ~10

---

## Future Considerations

### If We Add More Resolution Types

If we ever add new resolution types that don't use standard match results (0, 1, 2), we should:

1. Add the new resolution type to the invalidate check:
```python
if resolution in ('invalidate', 'technical_draw', 'no_contest'):
    mmr_change = 0
    # Skip MMR calculation
```

2. OR create a whitelist of resolutions that DO calculate MMR:
```python
if resolution in ('player_1_won', 'player_2_won', 'draw'):
    mmr_change = mmr_service.calculate_mmr_change(...)
else:
    mmr_change = 0
```

**Recommendation:** Use a whitelist approach for safety.

