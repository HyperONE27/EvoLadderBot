# Matchmaking Rewrite Progress

## Completed

### ✅ Step 1: Foundational Services (Completed)
- **NotificationService**: Fully implemented and tested (9 tests passing)
  - Push-based notification system using `asyncio.Queue`
  - Eliminates polling for match notifications
  - Thread-safe with async locks
  
- **QueueService**: Fully implemented and tested (13 tests passing)
  - Centralized queue state management
  - Prevents race conditions
  - Efficient bulk operations for matched players

## Current Status

We are at the beginning of Step 2 (Database Layer). However, we've identified that a full async database rewrite is a large undertaking that could be done incrementally.

## Recommended Next Steps (Pragmatic Approach)

### Immediate: Hybrid Database Approach
Instead of a complete database rewrite, we can get immediate benefits by:

1. **Keep the current synchronous database adapters**
2. **Offload blocking DB calls using `loop.run_in_executor()`** in critical paths:
   - MMR lookups in `add_player()`
   - Match creation in `attempt_match()`
   
This gives us ~90% of the performance benefit with 10% of the implementation effort.

### After Hybrid Works: Integrate New Services

1. **Wire NotificationService into matchmaking flow**:
   - Replace `handle_match_result` callback with `notification_service.publish_match_found()`
   - Update `QueueSearchingView` to subscribe and listen instead of poll

2. **Wire QueueService into matchmaking flow**:
   - Replace `matchmaker.players` list with `queue_service`
   - Update `add_player` and `remove_player` to use the service

3. **Test end-to-end**:
   - Full user journey from `/queue` to match found
   - Verify instant notifications work

### Future (Optional): Full Async Database
- Can be done later as a separate, focused effort
- Use `aiopg` or `asyncpg` for true async Postgres
- Migrate incrementally, starting with hot paths

## Why This Approach?

1. **Incremental Value**: Each step delivers working, testable improvements
2. **Risk Management**: Smaller changes are easier to debug and roll back
3. **Performance**: Executor-based offloading is sufficient for current needs
4. **Focus**: Keeps us focused on solving the notification delay problem

## Files Ready to Integrate

- `src/backend/services/notification_service.py`
- `src/backend/services/queue_service.py`
- Tests: All 22 tests passing

## Next Commit Plan

Implement the hybrid database approach by:
1. Adding executor-based DB offloading to `add_player()`
2. Adding executor-based DB offloading to `attempt_match()` where match creation happens
3. This unblocks the event loop without requiring full async DB migration

