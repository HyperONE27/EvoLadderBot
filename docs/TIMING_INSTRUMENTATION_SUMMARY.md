# Timing Instrumentation Implementation Summary

## What Was Done

Comprehensive performance timing has been added throughout the critical paths of the matchmaking and queue system using the existing `FlowTracker` utility.

## Files Modified

### 1. **`src/backend/services/matchmaking_service.py`**
Added timing to:
- `add_player()`: Track MMR lookup performance
  - Start MMR lookups
  - MMR lookups complete
  - Lock acquisition
- `attempt_match()`: Track complete matchmaking cycle
  - Player list copy
  - Wait cycle increment
  - Player categorization
  - List equalization
  - Match finding
  - Database match creation (per match)
  - Match callback invocation (per match)
  - Queue cleanup

### 2. **`src/bot/commands/queue_command.py`** 
Added comprehensive timing to ALL match workflows:

#### `JoinQueueButton.callback` - **Critical User-Facing Path**
- Defer interaction
- Validate race selection
- Get user info
- Check duplicate queue
- Create queue preferences
- Create player object
- Add player to matchmaker
- Create searching view
- Register view manager
- Build and send embed

#### `QueueSearchingView._listen_for_match` - **Match Notification Path**
- Subscribe to notifications
- Waiting for match (blocks until notification)
- Match notification received
- Process match result
- Create match found view
- Register for replay detection
- Generate match embed (offloaded to executor)
- Update Discord message
- Cleanup

#### `MatchResultConfirmSelect.callback` - **Result Reporting Path**
- Update confirmation status
- Update UI state
- Update Discord message
- Record player report

#### `on_message` - **Replay Upload Path**
- Download replay
- Parse replay (via process pool)
- Validate replay data
- Store replay
- Send replay embed
- Update all match views

#### `MatchFoundView.get_embed` - **Embed Generation (Critical!)**
- Player info lookup (2 DB queries)
- Rank lookup (2 ranking service calls)
- Match data lookup (1 DB query)
- Abort count lookup (2 DB queries)
- Total embed generation time

#### `MatchFoundView.handle_completion_notification` - **Match Finalization**
- Notification received
- Process completion/abort/conflict status
- Disable components
- Update embed
- Send final notification embed
- Complete flow

#### `MatchAbortButton.callback` - **Match Abort Flow**
- Check confirmation state
- Show confirmation prompt (first click)
- Update button UI
- Execute abort (second click)
- Time between first click and confirmation
- Update UI after abort
- Send abort UI update

#### `MatchResultSelect.callback` - **Result Selection**
- Validate replay uploaded
- Store selected result
- Update confirmation dropdown
- Update message

#### `MatchResultSelect.record_player_report` - **Report Submission**
- Convert result to report value
- Database write timing
- Total report recording time

### 3. **`src/backend/services/notification_service.py`**
Added timing to:
- `publish_match_found()`: Track notification push performance
  - Logs warning if > 10ms
  - Logs debug if <= 10ms

### 4. **`src/backend/services/match_completion_service.py`**
Added timing to:
- `check_match_completion()`: Track completion check latency
  - Warns if > 100ms
  - Logs if > 50ms
- `_handle_match_completion()`: Track completion handling
  - MMR calculation timing
  - Final results fetching
  - Player notification timing
  - Total completion time

### 5. **`docs/PERFORMANCE_ANALYSIS.md`** (New)
Comprehensive analysis document covering:
- Matchmaking rewrite status assessment
- Expected bottlenecks identification
- Optimization recommendations (immediate, medium-term, long-term)
- Testing strategy
- Performance targets
- Architectural issues

## How to Use the Timing Logs

### 1. **Start the Bot**
The timing logs will automatically appear in console output:

```
⚡ FAST [queue_command] 245.32ms (success)
  • guard_checks_start: 0.23ms
  • guard_checks_complete: 12.45ms
  • load_preferences_complete: 89.23ms
  • send_response_complete: 123.45ms
```

### 2. **Look for Slow Operations**
The logs use emoji indicators:
- ⚡ FAST: < 500ms (good)
- 🟢 OK: 500-1000ms (acceptable)
- 🟡 SLOW: 1000-3000ms (concerning)
- 🔴 CRITICAL: > 3000ms (exceeds Discord timeout)

### 3. **Identify Bottlenecks**
Look for:
- Individual checkpoints > 100ms
- Sequential operations that could be parallel
- Database queries taking > 50ms
- Discord API calls taking > 200ms

### 4. **Example Analysis**

```
🟡 SLOW [join_queue_button] 1847.23ms (success)
  • defer_interaction_start to defer_interaction_complete: 234.56ms  <-- Discord API slow
  • add_player_to_matchmaker_start to add_player_to_matchmaker_complete: 892.34ms  <-- BOTTLENECK!
  • build_and_send_embed_start to build_and_send_embed_complete: 456.78ms  <-- Secondary issue
```

This tells us:
1. The main bottleneck is in `add_player_to_matchmaker` (892ms)
2. Discord defer is also slow (235ms) - might be network
3. Embed generation needs optimization (457ms)

## Key Findings from Analysis

### ✅ What's Working Well
1. **Push-based notifications** - Working as designed, instant notification delivery
2. **Executor-based DB offloading** - Event loop doesn't block on DB calls
3. **Process pool for replay parsing** - Heavy computation offloaded successfully

### ⚠️ What Needs Attention
1. **QueueService not used** - Built but matchmaker doesn't use it
2. **Sequential MMR lookups** - Should be parallel or batched
3. **Embed generation with multiple DB queries** - Should pre-fetch or cache
4. **Sequential Discord API calls** - Should be parallel with `asyncio.gather()`

### 🔴 Critical Issues
1. **~3 second response time** - At the edge of Discord's timeout
2. **Synchronous operations in critical path** - Need parallelization
3. **Multiple DB roundtrips** - Need batching

## Recommended Next Steps

### Immediate (< 1 hour)
1. Run queue sessions and collect actual timing data
2. Identify the single slowest checkpoint
3. Implement quick win: Parallel Discord API updates

### Short-term (1-4 hours)
4. Batch MMR lookups
5. Cache rank data aggressively
6. Parallelize executor calls for multiple races

### Medium-term (1-2 days)
7. Complete QueueService integration
8. Pre-fetch all embed data before generation
9. Optimize database queries

### Long-term (1-2 weeks)
10. Full async database layer with asyncpg
11. Response caching layer
12. Database query optimization and indexing

## Performance Targets

| Operation | Current (Est.) | Target | Status |
|-----------|---------------|--------|--------|
| Queue Command | 150-300ms | < 150ms | 🟢 OK |
| Join Queue Button | 1000-2000ms | < 500ms | 🔴 Critical |
| Match Notification | 300-800ms | < 200ms | 🟡 Needs Work |
| Replay Upload | 500-1500ms | < 800ms | 🟡 Needs Work |
| Result Confirmation | 200-500ms | < 200ms | 🟢 Acceptable |

## Testing Commands

### Basic Queue Flow
```python
# User executes /queue
# [Timing logs for queue_command]

# User clicks "Join Queue"
# [Timing logs for join_queue_button]
# [Timing logs for matchmaker.add_player]

# Match is found
# [Timing logs for listen_for_match]
# [Timing logs for notification_service.publish_match_found]

# User uploads replay
# [Timing logs for replay_upload]

# User confirms result
# [Timing logs for confirm_match_result]
# [Timing logs for match_completion.check_match_completion]
```

### What to Monitor
1. **Total flow time** - Should be < 3000ms
2. **Checkpoint durations** - Identify > 100ms operations
3. **Sequential patterns** - Look for opportunities to parallelize
4. **Database calls** - Count roundtrips, look for N+1 queries
5. **Discord API calls** - Look for batching opportunities

## Conclusion

Comprehensive timing instrumentation is now in place across all critical paths. The logs will reveal:
- **Where** the time is being spent
- **Which** operations are slow
- **How** to optimize them

With this data, you can make informed decisions about optimization priorities and measure the impact of changes.

**Next action:** Run queue sessions and review the timing logs to identify real bottlenecks with actual data.

