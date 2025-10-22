# 🔴 CRITICAL PERFORMANCE BOTTLENECKS - ANALYSIS FROM LIVE DATA

## Executive Summary

**Status:** System is critically slow, with operations taking **20-33 SECONDS** instead of sub-3 seconds.

## 🔴 Critical Issues Found (In Order of Impact)

### 1. **CATASTROPHIC: Match Notification Display - 20-33 SECONDS** ⚠️⚠️⚠️
**Impact:** 20,078ms - 33,922ms (CRITICAL - 10x over Discord timeout!)

```
🔴 CRITICAL [listen_for_match] 31503.69ms (match_displayed_successfully)
  • waiting_for_match: 0.20ms
  • match_notification_received: 29215.31ms  ⚠️ 29 SECONDS!
  • register_for_replay_detection: 705.42ms
  • generate_match_embed_complete: 1111.63ms
  • update_discord_message_complete: 469.94ms
```

**ROOT CAUSE:** `match_notification_received` checkpoint is **misleading**. The delay is actually from:
- `await notification_service.subscribe_to_match_found()` blocking for ~29 seconds
- This happens BEFORE the match is even created
- Users join queue at 18:38:41, match created at 18:39:00 (19 seconds later)
- Then another 1-2 seconds to display

**Real Issue:** The matchmaker loop runs every **45 seconds** (line 92: "checking for matches every 45 seconds")
**Fix:** Reduce matchmaker interval OR trigger immediate match attempt when 2+ players queue

---

### 2. **CRITICAL: Replay Upload Updates - 11-12 SECONDS** ⚠️⚠️
**Impact:** 11,340ms - 12,174ms per replay upload

```
🔴 CRITICAL [replay_upload] 12174.19ms (success)
  • download_replay_complete: 750.75ms
  • parse_replay_complete: 2026.75ms
  • store_replay_complete: 1521.51ms
  • update_all_match_views: 3148.05ms  ⚠️ 3 seconds just to update views!
  • update_views_complete: 4725.49ms  ⚠️ ANOTHER 4.7 seconds!
```

**ROOT CAUSE:** Sequential embed regeneration + Discord API calls:
```python
# This creates 4+ embeds sequentially (lines 401-420 in logs)
⚠️ [MatchEmbed PERF] TOTAL get_embed() took 1231.22ms
⚠️ [MatchEmbed PERF] TOTAL get_embed() took 1277.21ms
⚠️ [MatchEmbed PERF] TOTAL get_embed() took 1320.92ms
⚠️ [MatchEmbed PERF] TOTAL get_embed() took 1448.01ms
```

**Each embed generation takes 1-1.5 seconds because:**
- Player info lookup: 475-700ms
- Match data lookup: 200-300ms
- Abort count lookup: 370-600ms

**Fix:**
1. Parallelize embed generation with `asyncio.gather()`
2. Parallelize Discord API calls
3. Cache player info and abort counts

---

### 3. **CRITICAL: Match Embed Generation - 1-1.5 SECONDS** ⚠️⚠️
**Impact:** 1,000ms - 1,500ms per embed

```
⚠️ [MatchEmbed PERF] TOTAL get_embed() took 1502.92ms
  [MatchEmbed PERF] Player info lookup: 797.64ms  ⚠️
  [MatchEmbed PERF] Match data lookup: 208.30ms
  [MatchEmbed PERF] Abort count lookup: 495.13ms  ⚠️
```

**ROOT CAUSE:** `get_embed()` is called synchronously (in executor) but does 3-4 DB queries:
```python
# src/bot/commands/queue_command.py ~line 870-920
p1_info = db_reader.get_player_by_discord_uid(...)  # 500-800ms
p2_info = db_reader.get_player_by_discord_uid(...)  # 500-800ms
match_data = db_reader.get_match_1v1(...)          # 200-330ms
p1_aborts = user_info_service.get_remaining_aborts(...)  # 350-600ms
p2_aborts = user_info_service.get_remaining_aborts(...)  # 350-600ms
```

**Fix:**
1. Batch these queries into a single DB call
2. Pre-fetch player info when match is created
3. Cache abort counts (they rarely change)
4. Make `get_embed()` async so we can use `asyncio.gather()` for parallel queries

---

### 4. **SEVERE: Match Result Confirmation - 2-3 SECONDS** ⚠️
**Impact:** 2,009ms - 3,483ms per confirmation

```
🔴 CRITICAL [confirm_match_result] 3482.83ms (success)
  • update_discord_message_complete: 2702.92ms  ⚠️
  • record_player_report_complete: 779.20ms
```

**ROOT CAUSE:** Regenerating embed (1-1.5s) + Discord API call + DB write
**Fix:** Same as #3 - faster embed generation

---

### 5. **SEVERE: Match Abort - 6+ SECONDS** ⚠️
**Impact:** 6,187ms just for the abort check, plus notification time

```
Line 913: ⏱️ [Abort PERF] Time between first click and confirmation: 4395.97ms
Line 915: execute_abort_complete: 1750.15ms
Line 1007: check_match_completion for match 104 took 7511.19ms

Plus 2 notification embeds taking 2-3 seconds EACH:
🔴 CRITICAL [match_completion_notification_abort] 3412.45ms
🔴 CRITICAL [match_completion_notification_abort] 3166.37ms
```

**ROOT CAUSE:**
1. Discord interaction timeout (line 900: "404 Not Found - Unknown interaction")
   - The abort button took >3 seconds to respond, so Discord killed the interaction
2. Slow embed generation for abort notifications
3. Slow match completion check

**Fix:**
1. Defer the interaction IMMEDIATELY when abort button clicked
2. Speed up embed generation (see #3)
3. Optimize match completion check

---

### 6. **MODERATE: MMR Lookups - 400-550ms** ⚠️
**Impact:** 364ms - 547ms per player joining queue

```
🟢 OK [matchmaker.add_player] 547.37ms (success)
  • mmr_lookups_complete: 546.69ms  ⚠️
```

**ROOT CAUSE:** Sequential DB queries for each race (2 races = 2 sequential queries)
**Fix:** Batch query or parallel executor calls

---

### 7. **MODERATE: Match Completion Processing - 6 SECONDS** ⚠️
**Impact:** 5,988ms for full completion

```
🏁 [MatchCompletion PERF] Total _handle_match_completion for match 103: 5988.29ms
  [MatchCompletion PERF] MMR calculation took 1666.10ms
  [MatchCompletion PERF] Get final results took 621.02ms
  [MatchCompletion PERF] Notify players took 3700.89ms  ⚠️ 3.7 seconds!
```

**ROOT CAUSE:** Sequential notification embeds (2 players × 1.5s each = 3s)
**Fix:** Parallelize notification sending

---

### 8. **MODERATE: Queue Command Initial Response - 500-2300ms**
**Impact:** 500ms - 2,345ms

```
🟡 SLOW [queue_command] 2345.79ms (success)
  • load_preferences_complete: 381.91ms
  • send_response_complete: 1961.91ms  ⚠️ 2 seconds to send!
```

**ROOT CAUSE:** Discord API is slow sometimes (network latency)
**Fix:** Not much we can control here, but ensure we defer quickly

---

## 📊 Performance Summary

| Operation | Current | Target | Priority |
|-----------|---------|--------|----------|
| Match notification display | 20-33s | <3s | 🔴 CRITICAL |
| Replay upload | 11-12s | <2s | 🔴 CRITICAL |
| Match embed generation | 1-1.5s | <200ms | 🔴 CRITICAL |
| Match result confirmation | 2-3s | <1s | 🔴 CRITICAL |
| Match abort | 6-10s | <2s | 🔴 CRITICAL |
| MMR lookups | 400-550ms | <100ms | 🟡 HIGH |
| Match completion | 6s | <2s | 🟡 HIGH |
| Queue command | 500-2300ms | <500ms | 🟢 MEDIUM |

---

## 🎯 Immediate Action Plan (Prioritized)

### Priority 1: Fix Matchmaker Interval (10x speedup for match finding)
**Current:** Matches check every 45 seconds
**Fix:** Check every 5 seconds OR trigger immediate check when player joins
**File:** `src/backend/services/matchmaking_service.py` line ~60
**Impact:** -25 seconds from match notification

### Priority 2: Optimize get_embed() (5-7x speedup)
**Current:** 1000-1500ms per embed, sequential DB queries
**Fix:**
1. Make `get_embed()` async
2. Batch all DB queries: `get_match_display_data(match_id)` returns everything
3. Cache player info and abort counts for 30 seconds
**Files:** `src/bot/commands/queue_command.py` line ~870-920
**Impact:** -1000ms per embed × 10+ embeds per match = -10+ seconds

### Priority 3: Parallelize Match View Updates
**Current:** Sequential embed generation + Discord updates
**Fix:** Use `asyncio.gather()` for parallel operations
**File:** `src/bot/commands/queue_command.py` line ~1893-1902
**Impact:** -3-4 seconds from replay upload

### Priority 4: Defer Abort Button Immediately
**Current:** Abort takes 4-9 seconds, causing Discord timeout
**Fix:** Add `await interaction.response.defer()` as first line in abort callback
**File:** `src/bot/commands/queue_command.py` `MatchAbortButton.callback`
**Impact:** Prevent 404 errors, -5 seconds perceived time

### Priority 5: Batch MMR Lookups
**Current:** Sequential queries per race
**Fix:** Single batch query `get_player_mmrs_batch(player_id, races)`
**File:** `src/backend/services/matchmaking_service.py` line ~133-192
**Impact:** -200-300ms per player join

---

## 🔧 Implementation Priority

1. **CRITICAL (Do First):**
   - Reduce matchmaker interval to 5 seconds
   - Make `get_embed()` async with parallel queries
   - Add immediate defer to abort button

2. **HIGH (Do Next):**
   - Parallelize match view updates
   - Batch MMR lookups
   - Cache player info/abort counts

3. **MEDIUM (After Above):**
   - Parallelize notification sending
   - Optimize match completion check
   - Add database indexes

---

## 🚨 Database Query Optimization Needed

Every `get_player_by_discord_uid()` call takes **500-800ms**. This is UNACCEPTABLE.

**Possible causes:**
1. Missing database index on `discord_user_id` column
2. Network latency to Supabase
3. Connection pool exhaustion
4. Inefficient query

**Investigate:**
```sql
-- Check if index exists
SELECT * FROM pg_indexes WHERE tablename = 'players' AND indexdef LIKE '%discord_user_id%';

-- Check query plan
EXPLAIN ANALYZE SELECT * FROM players WHERE discord_user_id = 123456;
```

**Expected:** <10ms per query with proper indexing
**Actual:** 500-800ms (50-80x slower!)

---

## Next Steps

1. ✅ Timing instrumentation complete (we have the data!)
2. ⏳ **Create optimization branch**
3. ⏳ **Implement Priority 1-3 fixes**
4. ⏳ **Test and measure improvement**
5. ⏳ **Iterate until all operations < 3s**

