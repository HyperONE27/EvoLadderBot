# Matchmaking Invariant Fixes - Implementation Summary

**Date:** November 11, 2025  
**Issue:** Players being matched against themselves in production  
**Root Cause:** Missing validation of implicit invariants in matchmaking algorithm

---

## Problems Identified

### Critical Bug
A player was matched against themselves in production, revealing that the matchmaking optimization code violated several implicit invariants.

### Analysis
Through comprehensive flow analysis, we identified 4 missing invariant validations across the 8-stage matchmaking pipeline:

1. **Disjoint lists after equalization** - No validation that BW and SC2 lists don't overlap
2. **Self-match candidate prevention** - No check preventing same player in both lead/follow sides
3. **Safe swap validation** - Refinement could create self-matches through adjacent swaps
4. **Final match validation** - No last line of defense before game creation

---

## Fixes Implemented

### Fix 1: Prevent Self-Match Candidates (Stage 4)
**Location:** `src/backend/services/matchmaking_service.py`, lines 573-575

**Change:** Added validation in `_build_candidate_pairs()` to skip pairs where lead and follow players are the same.

```python
for follow_player in follow_side:
    # Skip self-matching
    if lead_player.discord_user_id == follow_player.discord_user_id:
        continue
```

**Impact:** Prevents self-match candidates from being created during candidate building phase.

---

### Fix 2: Validate Swap Safety (Stage 6)
**Location:** `src/backend/services/matchmaking_service.py`, lines 683-686

**Change:** Added validation in `_refine_matches_least_squares()` before performing swaps.

```python
if error_after < error_before:
    # Ensure swap doesn't create self-matches
    if (p1_lead.discord_user_id == p2_follow.discord_user_id or 
        p2_lead.discord_user_id == p1_follow.discord_user_id):
        continue
```

**Impact:** Prevents refinement swaps from creating self-matches (e.g., swapping `[(Alice, Bob), (Bob, Charlie)]` to `[(Alice, Charlie), (Bob, Bob)]`).

---

### Fix 3: Validate List Disjointness (Stage 2)
**Location:** `src/backend/services/matchmaking_service.py`, lines 784-789

**Change:** Added assertion after `equalize_lists()` to ensure BW and SC2 lists contain no overlapping players.

```python
# Validate equalization produced disjoint sets
bw_ids = {p.discord_user_id for p in bw_list}
sc2_ids = {p.discord_user_id for p in sc2_list}
overlap = bw_ids & sc2_ids
if overlap:
    raise RuntimeError(f"Equalization produced overlapping lists: {overlap}")
```

**Impact:** Catches any logic errors in equalization that could cause a player to appear in both lists.

---

### Fix 4: Final Match Validation (Stage 7)
**Location:** `src/backend/services/matchmaking_service.py`, lines 845-850

**Change:** Added critical validation before match processing.

```python
for p1, p2 in matches:
    # Validate no self-matching
    if p1.discord_user_id == p2.discord_user_id:
        raise RuntimeError(
            f"CRITICAL: Self-match detected for player {p1.user_id} "
            f"(discord_id: {p1.discord_user_id}). This should never happen."
        )
```

**Impact:** Final fail-safe before game creation, provides clear error message for debugging.

---

## Test Suite

Created comprehensive test suite: `tests/backend/services/test_matchmaking_invariants.py`

### Test Coverage (15 tests, all passing ✅)

**Invariant 1 Tests - Disjoint Lists:**
- ✅ Both players assigned uniquely
- ✅ Mixed queue disjointness  
- ✅ Imbalanced populations disjointness

**Invariant 2 Tests - No Self-Match Candidates:**
- ✅ Same player in both lists blocked
- ✅ Single both player no self-match
- ✅ Normal candidates created correctly

**Invariant 3 Tests - Safe Swaps:**
- ✅ Refinement blocks self-match swaps
- ✅ Refinement allows valid swaps

**Invariant 4 Tests - Final Validation:**
- ✅ Self-match raises error

**End-to-End Scenarios:**
- ✅ Single both player cannot match self
- ✅ Two both players match correctly
- ✅ Complex queue all invariants
- ✅ Edge case: all both players

**Equalization Edge Cases:**
- ✅ MMR rebalancing preserves disjointness
- ✅ Population balance constraint enforced

---

## Invariant Summary Table

| # | Invariant | Previously Enforced? | Now Enforced? | Fix Location |
|---|-----------|---------------------|---------------|--------------|
| 1 | `bw_list ∩ sc2_list = ∅` | ❌ | ✅ | After `equalize_lists()` |
| 2 | `lead_player ≠ follow_player` | ❌ | ✅ | `_build_candidate_pairs()` |
| 3 | Swap doesn't create self-pair | ❌ | ✅ | `_refine_matches_least_squares()` |
| 4 | No self-match at final creation | ❌ | ✅ | Match processing loop |
| 5 | Unique participants across matches | ✅ | ✅ | `_select_matches_from_candidates()` |

---

## Defense in Depth Strategy

The fixes implement a **defense in depth** strategy with validation at multiple layers:

1. **Prevention Layer** - Stop self-matches at candidate creation (Fix 2)
2. **Optimization Layer** - Block unsafe swaps during refinement (Fix 3)
3. **Structural Layer** - Ensure list disjointness after equalization (Fix 1)
4. **Final Layer** - Catch any remaining issues before game creation (Fix 4)

This ensures that even if one validation fails, subsequent layers will catch the problem.

---

## Testing Results

```
15 tests passed in 0.32s
```

All tests validate:
- No self-matching in any scenario
- Disjoint player lists maintained throughout
- Swaps don't create invalid matches
- Edge cases handled correctly

---

## Production Impact

**Before:** Players could be matched against themselves, causing game creation failures and poor user experience.

**After:** 
- Four layers of validation prevent self-matches
- Clear error messages for debugging if issues occur
- Comprehensive test coverage ensures fixes work correctly
- No performance impact (O(1) checks added to existing loops)

---

## Related Files Changed

1. `src/backend/services/matchmaking_service.py` - 4 validation fixes added
2. `tests/backend/services/test_matchmaking_invariants.py` - New comprehensive test suite (370 lines)
3. `docs/MATCHMAKING_INVARIANT_FIXES.md` - This documentation

---

## Recommendations

1. **Monitor** - Watch production logs for any RuntimeError messages from new validations
2. **Review** - If errors occur, they indicate bugs in equalization/matching logic that need fixing
3. **Expand** - Consider adding similar validation for other implicit invariants (e.g., MMR windows)
4. **Document** - Update architecture docs to explicitly list all invariants

---

## Additional Fix: Population Balance Constraint

As part of this work, we also fixed an edge case where MMR rebalancing could break population balance:

**Issue:** After equalization balanced the lists (e.g., BW=1, SC2=1), Step 4 MMR rebalancing could move a player and break the balance (e.g., BW=2, SC2=0), preventing any matches.

**Fix:** Added population difference tracking before MMR moves, only allowing moves that don't worsen balance.

**Location:** `src/backend/services/matchmaking_service.py`, lines 468-502

This ensures matchmaking always prioritizes creating matches over perfect MMR balance.

