# Performance Analysis & Timing Implementation

## Executive Summary

### Matchmaking Rewrite Status: ⚠️ **PARTIALLY IMPLEMENTED**

The matchmaking rewrite has been **partially implemented** with excellent progress on the notification system, but **key components remain unused**:

✅ **Implemented & Working:**
- NotificationService - Push-based notifications (working perfectly)
- Event-driven architecture with asyncio.Queue
- Executor-based DB offloading in matchmaker
- Match notification display

❌ **Not Implemented (Despite Being Built):**
- QueueService integration with matchmaker (service exists but unused)
- Matchmaker still uses internal `self.players` list instead of QueueService
- Queue command doesn't use QueueService for centralized state management

### Performance Target

**Current Status:** ~3 seconds to respond to interactions
**Target:** < 3 seconds (Discord's interaction timeout)

## Timing Instrumentation Added

Comprehensive `FlowTracker` timing has been added to identify bottlenecks:

### 1. Queue Command Flow (`queue_command.py`)
- Initial command execution
- Guard checks
- Preference loading
- View creation
- Embed generation
- Discord API calls

### 2. Join Queue Button (`JoinQueueButton.callback`)
**Critical Path - This is where users feel the delay!**
- Interaction defer (Discord API)
- Race validation
- User info lookup
- Duplicate queue check
- Queue preferences creation
- Player object creation
- **Matchmaker.add_player() call** (includes MMR lookups)
- Searching view creation
- View registration
- Embed generation and send

### 3. Matchmaker Operations (`matchmaking_service.py`)
- `add_player()`: MMR lookups via executor
- `attempt_match()`: Complete matchmaking cycle
  - Player list copy
  - Wait cycle increment
  - Player categorization
  - List equalization
  - Match finding algorithm
  - **Database match creation** (via executor)
  - Match callback invocation
  - Queue cleanup

### 4. Match Notification Flow (`_listen_for_match`)
- Notification subscription
- Waiting for match (instant with push-based!)
- Match notification received
- Match view creation
- Replay detection registration
- **Embed generation** (potentially slow - includes ranking refresh)
- Discord message update
- Cleanup

### 5. Match Result Reporting (`MatchResultConfirmSelect.callback`)
- Confirmation status update
- UI state update
- **Discord message update** (with embed regeneration)
- Player report recording to database

### 6. Replay Upload Processing (`on_message`)
- Replay file download from Discord
- **Replay parsing** (offloaded to process pool)
- Replay validation
- **Replay storage** (database write)
- Replay embed generation
- **All match views update** (can be multiple Discord API calls)

### 7. Match Completion Service
- `check_match_completion()`: Database reads and report validation
- `_handle_match_completion()`:
  - **MMR calculation and database write**
  - Final results fetching
  - **Player notification callbacks**

### 8. Notification Service
- `publish_match_found()`: Push notifications to both players (should be < 10ms)

## Expected Bottlenecks

Based on the code analysis, here are the likely culprits for the 3-second delay:

### 1. **Embed Generation with Rank Lookups** ⚠️ HIGH PRIORITY
**Location:** `MatchFoundView.get_embed()` (line 862-1068 in queue_command.py)
```python
# This runs SYNCHRONOUSLY and includes:
p1_rank = ranking_service.get_rank(...)  # Database query
p2_rank = ranking_service.get_rank(...)  # Database query
# Plus multiple other DB reads for player info
```

**Problem:** Even though it's offloaded to executor, it's doing multiple synchronous DB queries.
**Impact:** Potentially 100-500ms
**Solution:** Batch these queries or cache ranking data aggressively

### 2. **MMR Lookups in add_player()** ⚠️ MEDIUM PRIORITY
**Location:** `Matchmaker.add_player()` (line 133-192 in matchmaking_service.py)
```python
for race in player.preferences.selected_races:
    mmr_data = await loop.run_in_executor(
        None,
        self.db_reader.get_player_mmr_1v1,
        ...
    )
```

**Problem:** Sequential executor calls for each race (up to 2 races = 2 sequential DB queries)
**Impact:** 50-200ms per player
**Solution:** Batch MMR lookups or parallel executor calls

### 3. **Match View Updates** ⚠️ LOW-MEDIUM PRIORITY
**Location:** `on_message()` replay upload (line 1893-1902)
```python
match_views = await match_found_view_manager.get_views_by_match_id(...)
for _, view in match_views:
    # Multiple Discord API calls in sequence
    await view.last_interaction.edit_original_response(...)
```

**Problem:** Sequential Discord API calls for each player
**Impact:** 100-300ms per player (200-600ms total for 2 players)
**Solution:** Make these calls in parallel with `asyncio.gather()`

### 4. **Database Connection Pool Contention** ⚠️ UNKNOWN
**Location:** All database calls throughout the system

**Problem:** If the connection pool is exhausted or slow, requests queue up
**Impact:** Variable, could be 0-1000ms depending on load
**Solution:** Monitor connection pool usage, increase pool size if needed

## Optimization Recommendations

### Immediate Actions (Quick Wins)

1. **Parallel Match View Updates**
```python
# BEFORE (sequential):
for _, view in match_views:
    await view.last_interaction.edit_original_response(...)

# AFTER (parallel):
update_tasks = []
for _, view in match_views:
    if view.last_interaction:
        task = view.last_interaction.edit_original_response(...)
        update_tasks.append(task)
await asyncio.gather(*update_tasks, return_exceptions=True)
```

2. **Batch MMR Lookups**
```python
# Instead of sequential lookups, create a batch query method
mmr_data = await db_reader.get_player_mmrs_batch(
    player_id,
    races=[bw_race, sc2_race]
)
```

3. **Aggressive Rank Caching**
```python
# Cache rank lookups for 30 seconds - ranks don't change that often
@lru_cache(maxsize=1000)
def get_rank_cached(player_id, race, timestamp):
    return ranking_service.get_rank(player_id, race)

# Use it with 30-second buckets
current_bucket = int(time.time() / 30)
rank = get_rank_cached(player_id, race, current_bucket)
```

### Medium-Term Actions

4. **Complete QueueService Integration**
- Refactor matchmaker to use `QueueService.get_snapshot()` instead of `self.players`
- Remove duplicate state management
- Single source of truth for queue state

5. **Parallel Executor Calls**
```python
# Use asyncio.gather for parallel DB queries
mmr_results = await asyncio.gather(
    loop.run_in_executor(None, db_reader.get_player_mmr_1v1, player_id, bw_race),
    loop.run_in_executor(None, db_reader.get_player_mmr_1v1, player_id, sc2_race),
    return_exceptions=True
)
```

6. **Precompute Expensive Data**
- Pre-load player info when match is created
- Attach to MatchResult object to avoid repeated DB queries
- Reduces redundant queries in embed generation

### Long-Term Actions

7. **Full Async Database Layer**
- Replace psycopg2 with asyncpg
- True async queries without executor overhead
- Better connection pool management

8. **Response Caching**
- Cache frequently accessed data (maps, races, regions)
- Cache player rankings with short TTL
- Cache match embeds for repeated views

9. **Database Query Optimization**
- Add indexes on frequently queried fields
- Use database views for complex joins
- Optimize N+1 query patterns

## Testing Strategy

### How to Use the New Timing Logs

1. **Run a queue session and observe logs:**
```
⚡ FAST [queue_command] 245.32ms (success)
  • guard_checks_start to guard_checks_complete: 12.45ms
  • load_preferences_start to load_preferences_complete: 89.23ms
  • send_response_start to send_response_complete: 123.45ms
```

2. **Identify slow checkpoints:**
- Look for operations > 100ms
- Check for sequential operations that could be parallel
- Look for repeated patterns

3. **Profile specific bottlenecks:**
```python
# Add more granular timing within slow operations
flow.checkpoint("db_query_1_start")
result = await db_call()
flow.checkpoint("db_query_1_complete")
```

### Performance Targets by Operation

| Operation | Current (Est.) | Target | Priority |
|-----------|---------------|--------|----------|
| Join Queue Button | 1000-2000ms | < 500ms | HIGH |
| Match Notification | 300-800ms | < 200ms | HIGH |
| Replay Upload | 500-1500ms | < 800ms | MEDIUM |
| Match Result Confirm | 200-500ms | < 200ms | LOW |
| Queue Command | 150-300ms | < 150ms | LOW |

## Architectural Issues to Address

### 1. QueueService Not Used
**Problem:** Built but not integrated
**Impact:** Duplicate state management, missed benefits of centralized queue
**Fix:** Refactor matchmaker to use `queue_service.get_snapshot()` in `attempt_match()`

### 2. Synchronous Embed Generation
**Problem:** Complex embeds with multiple DB queries generated synchronously
**Impact:** Blocks executor threads, delays responses
**Fix:** Pre-fetch all data needed for embeds, or generate embeds asynchronously

### 3. Sequential Discord API Calls
**Problem:** Updating multiple views in sequence
**Impact:** Cumulative latency (2 players = 2x delay)
**Fix:** Use `asyncio.gather()` for parallel updates

## Next Steps

1. ✅ **Timing instrumentation added** - Now we can measure!
2. ⏳ **Run live tests** - Execute queue sessions and collect timing data
3. ⏳ **Identify bottlenecks** - Analyze logs to find slowest operations
4. ⏳ **Implement quick wins** - Parallel updates, batched queries
5. ⏳ **Measure improvements** - Compare before/after timing
6. ⏳ **Iterate** - Continue optimization until < 3 seconds consistently

## Conclusion

The matchmaking rewrite delivered **excellent push-based notifications** but left QueueService on the shelf. The 3-second delay likely comes from:

1. **Synchronous embed generation with multiple DB queries** (300-500ms)
2. **Sequential MMR lookups** (100-200ms)
3. **Sequential Discord API calls** (200-600ms)
4. **Database connection pool contention** (variable)

With the comprehensive timing instrumentation now in place, we can:
- Identify exact bottlenecks with real data
- Measure impact of optimizations
- Ensure we stay under Discord's 3-second timeout

The foundation is solid - we just need to tighten up the data fetching and parallelization.

