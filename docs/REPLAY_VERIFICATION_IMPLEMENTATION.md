# Replay Verification Implementation

## Overview

This document describes the implementation of the replay verification feature as specified in `docs/match_replay_check_proposal.md`. This feature verifies that uploaded replays match the assigned match parameters and provides visual feedback to players.

**Status:** ✅ Implemented (Phase 1 - Verification Only)

**Note:** Auto-reporting of match results based on verification is intentionally **NOT** implemented in this phase. That functionality is reserved for a future update.

---

## Implementation Summary

### Phase 1: Backend Verification Logic

**File:** `src/backend/services/match_completion_service.py`

Added the following components:

1. **`VerificationResult` TypedDict** - Defines the structure for verification results:
   - `races_match: bool` - Whether races match
   - `map_match: bool` - Whether map matches
   - `timestamp_match: bool` - Whether timestamp is within 20 minutes
   - `observers_match: bool` - Whether no unauthorized observers present

2. **Public Method:**
   - `start_replay_verification(match_id, replay_id, callback)` - Entry point to start verification in background

3. **Private Methods:**
   - `_verify_replay_task()` - Background worker that orchestrates all checks
   - `_verify_races()` - Checks if replay races match assigned races (supports swapped order)
   - `_verify_map()` - Checks if replay map matches assigned map
   - `_verify_timestamp()` - Checks if match was played within 20 minutes of assignment
   - `_verify_observers()` - Checks for unauthorized observers

### Phase 2: UI Updates

**File:** `src/bot/components/replay_details_embed.py`

1. Added `VerificationResult` TypedDict (duplicated from service for import independence)

2. Updated `get_success_embed()`:
   - Added optional `verification_results` parameter
   - Conditionally displays verification field when results are provided

3. Added `_format_verification_results()` helper method:
   - Formats verification results with ✅/❌ icons
   - Displays detailed status for each check
   - Shows summary message based on overall result

### Phase 3: Integration

**File:** `src/bot/commands/queue_command.py`

Updated `store_replay_background()` function:
- Sends initial "Verifying..." message after replay storage
- Calls `match_completion_service.start_replay_verification()`
- Defines callback to update embed with verification results
- Edits the initial message with final verification results when complete

**Files Modified:** `src/backend/services/replay_service.py` and `src/backend/services/data_access_service.py`

1. **`replay_service.py`:**
   - Modified `store_upload_from_parsed_dict_async()` to return `replay_id` and `match_id`

2. **`data_access_service.py`:**
   - Modified `insert_replay()` to:
     - Generate replay ID immediately
     - Add replay to in-memory dataframe before async DB write
     - Return the generated replay ID

### Phase 4: Testing

**File:** `tests/backend/services/test_replay_verification.py`

Created comprehensive test suite with 17 tests covering:
- Individual verification method tests (races, map, timestamp, observers)
- Edge cases (swapped races, empty observers, JSON vs list observers)
- Full verification scenarios (all pass, all fail)
- Replay file parsing tests using actual test replay files

**Test Results:** ✅ All 17 tests passing

---

## Verification Logic Details

### Race Verification

- Compares sets of races from match assignment and replay
- Handles swapped player positions (e.g., P1=Zerg, P2=Protoss vs P1=Protoss, P2=Zerg)
- Passes if both race sets are equal

### Map Verification

- Simple string comparison between `map_played` and `map_name`
- Case-sensitive exact match required

### Timestamp Verification

- Calculates replay start time: `replay_date - duration`
- Checks if start time is within 20 minutes of `played_at`
- Uses absolute difference to handle clock skew
- Gracefully handles timezone formats

### Observer Verification

- Handles multiple data formats:
  - `None` - No observers
  - Empty list `[]` - No observers
  - Empty JSON string `"[]"` - No observers
  - Non-empty list - Observers present (FAIL)
  - Non-empty JSON string - Observers present (FAIL)

---

## Data Flow

1. User uploads replay → `on_message` handler processes
2. Replay is parsed → `store_replay_background` is called
3. Replay is stored in DB → `replay_id` is returned
4. Initial "Verifying..." embed is sent to channel
5. `match_completion_service.start_replay_verification()` is called
6. Background task runs all verification checks
7. Callback updates embed with final verification results
8. Players see the updated embed with verification status

---

## User Experience

### When All Checks Pass

```
Replay Verification
- Races match: ✅ Races played correspond to races queued with.
- Map name matches: ✅ Map used corresponds to the map assigned.
- Timestamp matches: ✅ Match was initiated within ~20 minutes of match assignment.
- No observers: ✅ No unverified observers detected.
- Winner detection: ✅ Match details verified, please report the winner manually.

✅ No issues detected.
```

### When Checks Fail

```
Replay Verification
- Races match: ❌ Races played correspond to races queued with.
- Map name matches: ❌ Map used corresponds to the map assigned.
- Timestamp matches: ✅ Match was initiated within ~20 minutes of match assignment.
- No observers: ❌ No unverified observers detected.
- Winner detection: ❌ Match details NOT verified, please report the winner manually.

⚠️ One or more match parameters were incorrect. The system will reflect the record.
```

---

## Future Work (Phase 2)

The following features are **explicitly deferred** to a future implementation:

1. **Auto-Reporting:**
   - When all checks pass, automatically report the winner
   - Update `MatchFoundView` to reflect the confirmed result
   - Disable report buttons for the uploader
   - Mark match as reported in the database

2. **Enhanced Verification:**
   - Fuzzy map name matching (handle variations like "LE" vs "Ladder Edition")
   - Player name matching for additional validation
   - Handle edge cases like draws (result=0)

3. **Admin Override:**
   - Allow admins to manually approve/reject verification results
   - Provide audit trail for verification decisions

---

## Files Modified

### Backend Services
- `src/backend/services/match_completion_service.py` - Added verification logic
- `src/backend/services/data_access_service.py` - Modified `insert_replay` to return ID
- `src/backend/services/replay_service.py` - Modified return value to include IDs

### Bot Components
- `src/bot/components/replay_details_embed.py` - Updated to display verification
- `src/bot/commands/queue_command.py` - Integrated verification flow

### Tests
- `tests/backend/services/test_replay_verification.py` - New comprehensive test suite

---

## Testing Instructions

Run the test suite:

```bash
python -m pytest tests/backend/services/test_replay_verification.py -v
```

Expected result: All 17 tests should pass.

---

## Notes

- This implementation follows the principle of "fail explicitly" as specified in the repository rules
- No auto-reporting is implemented to ensure safe rollout
- All verification is read-only and does not modify match state
- The system is designed to be easily extended for auto-reporting in Phase 2

