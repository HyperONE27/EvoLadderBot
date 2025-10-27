# Abort Notification Fix - Implementation Summary

## Problem Description

The system was failing to send abort notifications to players when matches were automatically aborted due to timeout (when neither player confirmed within `ABORT_TIMER_SECONDS`). The logs showed:

```
Notifying 0 callbacks for match 48 abort.
```

This indicated that while the backend correctly identified and processed the timeout-based abort, it failed to invoke the notification callbacks registered by the frontend views.

## Root Cause Analysis

The issue was a **communication breakdown between the backend and frontend**:

1. **Frontend Registration**: The `MatchFoundView` in `queue_command.py` correctly registered a callback (`handle_completion_notification`) with the backend when the match was found.

2. **Backend Timeout Detection**: The `match_completion_service.py` had an internal timer (`_monitor_match_completion`) that detected when players failed to confirm in time.

3. **The Gap**: When the timeout occurred, `_handle_unconfirmed_abort` was called, which:
   - Set the player report codes to `-4` (unconfirmed)
   - Called `check_match_completion` using `asyncio.create_task` (fire-and-forget)
   - This created a race condition where the callback notification might not execute properly

4. **Callback Invocation Failure**: The `_handle_match_abort` method would retrieve callbacks from `self.notification_callbacks`, but due to timing issues or premature cleanup, it found 0 callbacks to notify.

## Solution Implemented

### 1. Backend: `match_completion_service.py`

#### Change 1: Fixed `_handle_unconfirmed_abort` (Line 441-480)

**Before:**
```python
asyncio.create_task(self.check_match_completion(match_id))
```

**After:**
```python
await self.check_match_completion(match_id)
```

**Rationale**: Changed from fire-and-forget task creation to awaiting the completion check. This ensures that the notification callbacks are invoked synchronously within the same execution context, preventing race conditions and premature cleanup.

#### Change 2: Enhanced `_handle_match_abort` (Line 399-461)

**Added:**
- Explicit retrieval of latest match data to ensure report codes are available
- Enhanced error handling for cases where final results cannot be fetched
- Explicit inclusion of `p1_report` and `p2_report` in the callback data payload

**Key Change:**
```python
await callback(
    status="abort", 
    data={
        "match_id": match_id, 
        "match_data": final_match_data,
        "p1_report": latest_match_data.get('player_1_report'),
        "p2_report": latest_match_data.get('player_2_report'),
    }
)
```

**Rationale**: Ensures that the frontend receives all necessary information to distinguish between different abort scenarios (timeout vs. player-initiated).

### 2. Frontend: `queue_command.py`

#### Change 1: Updated `handle_completion_notification` (Line 1165-1237)

**Added:**
```python
await self._send_abort_notification_embed(
    p1_report=data.get('p1_report'),
    p2_report=data.get('p2_report')
)
```

**Rationale**: Passes the report codes from the backend data payload to the notification method, allowing it to display the correct abort reason.

#### Change 2: Enhanced `_send_abort_notification_embed` (Line 1335-1431)

**Added:**
- Optional parameters `p1_report` and `p2_report` with fallback to fetching from match data
- Enhanced logic to distinguish between different abort scenarios:
  - Both players failed to confirm (`-4` and `-4`)
  - Only Player 1 failed to confirm (`-4` and `None`)
  - Only Player 2 failed to confirm (`None` and `-4`)
  - Player-initiated abort (`-3`)

**Key Logic:**
```python
if p1_report == -4 and p2_report == -4:
    reason = "The match was automatically aborted because neither player confirmed in time."
elif p1_report == -4:
    reason = f"The match was automatically aborted because **{p1_name}** did not confirm in time."
elif p2_report == -4:
    reason = f"The match was automatically aborted because **{p2_name}** did not confirm in time."
elif p1_report == -3:
    reason = f"The match was aborted by **{p1_name}**. No MMR changes were applied."
```

**Rationale**: Provides clear, specific messages to players explaining exactly why the match was aborted.

## Testing Recommendations

1. **Timeout Scenario - Both Players**: 
   - Create a match, neither player clicks confirm
   - Verify both players receive abort notification after `ABORT_TIMER_SECONDS`
   - Verify message: "neither player confirmed in time"

2. **Timeout Scenario - One Player**:
   - Create a match, only one player clicks confirm
   - Verify both players receive abort notification
   - Verify message specifies which player failed to confirm

3. **Manual Abort Scenario**:
   - Create a match, one player clicks abort
   - Verify both players receive abort notification
   - Verify message specifies which player initiated the abort

4. **Log Verification**:
   - Monitor logs for "Notifying N callbacks" message
   - Verify N is > 0 for timeout-based aborts
   - Verify no errors during callback execution

## Files Modified

- `src/backend/services/match_completion_service.py`
  - `_handle_unconfirmed_abort()` method (line 441)
  - `_handle_match_abort()` method (line 399)

- `src/bot/commands/queue_command.py`
  - `handle_completion_notification()` method (line 1165)
  - `_send_abort_notification_embed()` method (line 1335)

## Impact Assessment

- **No Breaking Changes**: All modifications are backward-compatible
- **Performance**: Minimal impact - synchronous await adds negligible latency
- **Reliability**: Significantly improved - eliminates race conditions
- **User Experience**: Enhanced - players now receive clear, specific abort notifications

## Follow-up Actions

1. Monitor production logs for "Notifying 0 callbacks" messages
2. Verify user reports of missing abort notifications decrease
3. Consider adding metrics to track callback invocation success rate
4. Review other uses of `asyncio.create_task` for similar race conditions

