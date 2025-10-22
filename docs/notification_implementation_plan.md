# Notification Service Integration Plan

## Current Implementation (Polling-Based)

### How it works now:
1. User clicks "Join Queue"
2. `QueueSearchingView` is created with a `periodic_match_check()` task
3. This task polls `match_results` dictionary every 1 second
4. When `matchmaker` finds a match, it calls `handle_match_result()` which adds to `match_results`
5. The polling task eventually sees it and updates the view

### Problems:
- Up to 1 second delay inherent in polling
- Event loop congestion can make it worse
- Silent failures (bare `except: pass`)
- Global dictionary is fragile shared state

## New Implementation (Push-Based)

### How it will work:
1. User clicks "Join Queue"
2. `QueueSearchingView` subscribes to `notification_service` and gets a personal `asyncio.Queue`
3. View creates a `_listen_for_match()` task that `await`s on the queue
4. When `matchmaker` finds a match, it calls `notification_service.publish_match_found()`
5. This instantly wakes up the waiting task, which immediately updates the view

### Benefits:
- **Instant notification**: No polling delay
- **Simpler code**: Just one `await` statement
- **Robust**: Proper async patterns, no shared state
- **Event loop friendly**: Task is blocked (not busy-waiting)

## Implementation Steps

### Step 1: Import New Services
Add imports to `queue_command.py`:
```python
from src.backend.services.notification_service import get_notification_service, initialize_notification_service
from src.backend.services.queue_service import get_queue_service, initialize_queue_service
```

### Step 2: Initialize Services in app_context
Add to `src/backend/services/app_context.py`:
```python
from src.backend.services.notification_service import initialize_notification_service
from src.backend.services.queue_service import initialize_queue_service

notification_service = initialize_notification_service()
queue_service = initialize_queue_service()
```

### Step 3: Replace QueueSearchingView.periodic_match_check()
Replace the polling method with a push-based listener:

**Old:**
```python
async def periodic_match_check(self):
    while self.is_active:
        await asyncio.sleep(1)
        if self.player.discord_user_id in match_results:
            # Handle match found
```

**New:**
```python
async def _listen_for_match(self):
    notification_queue = await notification_service.subscribe(self.player.discord_user_id)
    try:
        # This blocks until a match is published
        match_result = await notification_queue.get()
        # Handle match found immediately
    finally:
        await notification_service.unsubscribe(self.player.discord_user_id)
```

### Step 4: Update Matchmaker Callback
Replace `handle_match_result()` to use notification service instead of global dict:

**Old:**
```python
def handle_match_result(match_result: MatchResult, ...):
    match_results[match_result.player_1_discord_id] = match_result
    match_results[match_result.player_2_discord_id] = match_result
```

**New:**
```python
async def handle_match_result(match_result: MatchResult, ...):
    await notification_service.publish_match_found(match_result)
```

### Step 5: Update CancelQueueButton
Ensure proper cleanup when cancelling:
```python
await notification_service.unsubscribe(self.player.discord_user_id)
if self.view.match_task:
    self.view.match_task.cancel()
```

## Testing Strategy

1. **Unit tests**: Already done (22 passing tests for services)
2. **Integration test**: Test the full flow manually:
   - Two users `/queue` at the same time
   - Verify both get instant notifications when matched
   - Test cancel during queue
   - Test timeout scenarios
3. **Performance test**: Measure notification latency (should be < 50ms)

## Rollback Plan

If issues arise:
1. The changes are isolated to `queue_command.py` and matchmaker callback
2. Git revert is straightforward since it's in a feature branch
3. Old polling code is preserved in git history

## Success Criteria

- ✅ Match notifications appear instantly (< 100ms from match creation)
- ✅ No polling loops remain in queue code
- ✅ All existing functionality (cancel, timeout) still works
- ✅ No memory leaks (subscriptions properly cleaned up)

