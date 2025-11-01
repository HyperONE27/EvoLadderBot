# Discord API Call Analysis for Concurrency Planning

## Executive Summary

This analysis documents all outbound Discord API calls made by the bot, with special focus on the `/queue` flow. The goal is to identify peak API call scenarios and opportunities for rate limiting to stay under 50 API calls/second.

**Key Findings:**
- **Peak Risk:** Match found notifications (2 API calls per match, simultaneous)
- **Heartbeat Load:** Queue searching updates (1 call per player every 10 seconds)
- **Smoothable Operations:** Heartbeat updates, replay verification messages, admin notifications
- **Critical Path:** Initial slash command responses, match found notifications, user interactions

---

## 1. API Call Inventory by Command

### 1.1 `/queue` Command Flow

#### **Initial Queue Setup** (Per User Invocation)
1. **Initial Response** - `send_ephemeral_response(interaction, embed, view)`
   - **API Call:** `interaction.response.send_message(ephemeral=True)`
   - **Frequency:** Once per `/queue` invocation
   - **Latency:** User-facing, critical path
   - **Smoothable:** ❌ No (user expectation is immediate response)

#### **Join Queue Button Click**
2. **Defer Interaction** - `interaction.response.defer()`
   - **API Call:** `interaction.response.defer()`
   - **Frequency:** Once per join attempt
   - **Latency:** Critical (prevents "interaction failed" errors)
   - **Smoothable:** ❌ No (must respond within 3 seconds)

3. **Update to Searching State** - `interaction.edit_original_response(embed, view)`
   - **API Call:** `interaction.edit_original_response()`
   - **Frequency:** Once per player joining queue
   - **Latency:** User-facing, critical
   - **Smoothable:** ❌ No (user expects immediate confirmation)

#### **Queue Searching Heartbeat Updates**
4. **Periodic Status Updates** - `interaction.edit_original_response(embed, view)`
   - **Location:** `QueueSearchingView.periodic_status_update()`
   - **API Call:** `self.last_interaction.edit_original_response()`
   - **Frequency:** Every 10 seconds per player in queue (`QUEUE_SEARCHING_HEARTBEAT_SECONDS`)
   - **Latency:** Non-critical, informational only
   - **Smoothable:** ✅ YES - **PRIME CANDIDATE FOR RATE LIMITING**
   - **Current Load:** N players × 6 calls/minute = 0.1N calls/second
   - **Peak Scenario:** 100 players queueing = 10 calls/second sustained
   - **Optimization Strategy:**
     - Implement lazy rate limiter with module-scoped queue
     - Batch updates if multiple players need updates simultaneously
     - Increase interval to 15-20 seconds during peak load
     - Skip updates if player is about to receive match notification

#### **Match Found Notification**
5. **Confirmation Embed** - `interaction.edit_original_response(embed, view=None)`
   - **Location:** `QueueSearchingView._listen_for_match()`
   - **API Call:** `self.last_interaction.edit_original_response()`
   - **Frequency:** Once per player when match is found
   - **Latency:** Critical (user must know match is ready)
   - **Smoothable:** ❌ No (time-sensitive notification)

6. **Match Details Message** - `channel.send(embed, view)`
   - **Location:** `QueueSearchingView._listen_for_match()`
   - **API Call:** `await self.channel.send(embed=embed, view=match_view)`
   - **Frequency:** Once per player when match is found (2 calls total per match)
   - **Latency:** Critical (players need match details to play)
   - **Smoothable:** ⚠️ Partial (could delay by 1-2 seconds if needed)
   - **Peak Scenario:** 10 simultaneous matches = 20 API calls in <1 second
   - **Optimization Strategy:**
     - Stagger match notifications by 100-200ms per match
     - This spreads 20 calls over 2 seconds instead of instant burst

### 1.2 Match Interaction Flow

#### **Match Confirmation**
7. **Defer Response** - `interaction.response.defer()`
   - **Location:** `MatchConfirmButton.callback()`
   - **API Call:** `await interaction.response.defer()`
   - **Frequency:** Once per player confirmation
   - **Latency:** Critical (prevents interaction timeout)
   - **Smoothable:** ❌ No

8. **Update View with Confirmation** - `interaction.edit_original_response(view)`
   - **Location:** `MatchConfirmButton.callback()`
   - **API Call:** `await interaction.edit_original_response(view=self.parent_view)`
   - **Frequency:** Once per player confirmation
   - **Latency:** User-facing
   - **Smoothable:** ❌ No

9. **Confirmation Feedback** - `interaction.followup.send(ephemeral=True)`
   - **Location:** `MatchConfirmButton.callback()`
   - **API Call:** `await interaction.followup.send()`
   - **Frequency:** Once per player confirmation
   - **Latency:** Non-critical, informational
   - **Smoothable:** ✅ YES (could be queued briefly)

#### **Match Abort**
10. **Update Abort Button State** - `interaction.response.edit_message(embed, view)`
    - **Location:** `MatchAbortButton.callback()` (first click)
    - **API Call:** `await interaction.response.edit_message()`
    - **Frequency:** Once per abort attempt (first click)
    - **Latency:** User-facing (confirmation prompt)
    - **Smoothable:** ❌ No

11. **Finalize Abort** - `interaction.response.edit_message(embed, view)`
    - **Location:** `MatchAbortButton.callback()` (second click)
    - **API Call:** `await interaction.response.edit_message()`
    - **Frequency:** Once per completed abort
    - **Latency:** User-facing
    - **Smoothable:** ❌ No

12. **Abort Notification Embed** - `channel.send(embed)`
    - **Location:** `MatchFoundView._send_abort_notification_embed()`
    - **API Call:** `await self.channel.send(embed=abort_embed)`
    - **Frequency:** Once per aborted match (sent to both players)
    - **Latency:** Non-critical, informational
    - **Smoothable:** ✅ YES - **RATE LIMITER CANDIDATE**
    - **Notes:** Follow-up notification after match is already aborted

#### **Replay Upload**
13. **Replay Verification Result** - `channel.send(embed)`
    - **Location:** `store_replay_background()`
    - **API Call:** `await channel.send(embed=final_embed)`
    - **Frequency:** Once per replay upload
    - **Latency:** Non-critical (informational only)
    - **Smoothable:** ✅ YES - **RATE LIMITER CANDIDATE**
    - **Notes:** Already runs in background task, can be delayed further

14. **Replay Invalid Notification** - `channel.send(embed)`
    - **Location:** `on_message()` (replay processing)
    - **API Call:** `await message.channel.send(embed=error_embed)`
    - **Frequency:** Once per invalid replay
    - **Latency:** Non-critical
    - **Smoothable:** ✅ YES

#### **Match Result Reporting**
15. **Result Selection Update** - `interaction.response.edit_message(embed, view)`
    - **Location:** `MatchResultSelect.callback()`
    - **API Call:** `await interaction.response.edit_message()`
    - **Frequency:** Once per result selection
    - **Latency:** User-facing
    - **Smoothable:** ❌ No

16. **Result Confirmation Update** - `interaction.response.edit_message(embed, view)`
    - **Location:** `MatchResultConfirmSelect.callback()`
    - **API Call:** `await interaction.response.edit_message()`
    - **Frequency:** Once per result confirmation
    - **Latency:** User-facing
    - **Smoothable:** ❌ No

#### **Match Completion Notifications**
17. **Final Result Embed (Gold)** - `channel.send(embed)`
    - **Location:** `MatchFoundView._send_final_notification_embed()`
    - **API Call:** `await self.channel.send(embed=notification_embed)`
    - **Frequency:** Once per completed match (sent to both players)
    - **Latency:** Important but not critical
    - **Smoothable:** ⚠️ Partial - **STAGGER RECOMMENDED**
    - **Peak Scenario:** 10 matches completing simultaneously = 20 API calls
    - **Optimization Strategy:**
      - Introduce 200-500ms stagger per match completion
      - This spreads notifications over 2-5 seconds

18. **Conflict Notification Embed** - `channel.send(embed)`
    - **Location:** `MatchFoundView._send_conflict_notification_embed()`
    - **API Call:** `await self.channel.send(embed=conflict_embed)`
    - **Frequency:** Once per conflicted match (sent to both players)
    - **Latency:** Non-critical
    - **Smoothable:** ✅ YES - **RATE LIMITER CANDIDATE**

### 1.3 Other Commands

#### `/profile` Command
19. **Profile Response** - `send_ephemeral_response(interaction, embed)`
    - **Frequency:** Once per invocation
    - **Latency:** User-facing, critical
    - **Smoothable:** ❌ No

#### `/leaderboard` Command
20. **Initial Leaderboard** - `send_ephemeral_response(interaction, embed, view)`
    - **Frequency:** Once per invocation
    - **Latency:** User-facing, critical
    - **Smoothable:** ❌ No

21. **Pagination/Filter Updates** - `interaction.response.edit_message(embed, view)`
    - **Location:** `LeaderboardView.update_view()`
    - **API Call:** `await interaction.response.edit_message()`
    - **Frequency:** Per pagination/filter action
    - **Latency:** User-facing
    - **Smoothable:** ❌ No

#### `/admin` Commands
22. **Admin Snapshot** - `interaction.followup.send(embed)`
    - **Frequency:** Per admin invocation
    - **Latency:** Non-critical
    - **Smoothable:** ✅ YES

23. **Admin Player State** - `interaction.followup.send(embed)`
    - **Frequency:** Per admin invocation
    - **Latency:** Non-critical
    - **Smoothable:** ✅ YES

24. **Admin Match State** - `interaction.followup.send(embed, file)`
    - **Frequency:** Per admin invocation
    - **Latency:** Non-critical
    - **Smoothable:** ✅ YES

25. **Admin Resolution Notifications** - `user.send(embed)` (DMs to players)
    - **Location:** `admin_resolve()` command
    - **API Call:** `await send_player_notification(player_uid, player_embed)`
    - **Frequency:** 2 calls per admin resolution (one per player)
    - **Latency:** Non-critical (informational)
    - **Smoothable:** ✅ YES - **PRIME RATE LIMITER CANDIDATE**
    - **Notes:** Admin actions are typically infrequent

26. **Admin MMR Adjustment Notifications** - `user.send(embed)` (DMs)
    - **Location:** `admin_adjust_mmr()` command
    - **Frequency:** 1 call per adjustment
    - **Latency:** Non-critical
    - **Smoothable:** ✅ YES - **RATE LIMITER CANDIDATE**

27. **Admin Queue Removal Notifications** - `user.send(embed)` (DMs)
    - **Location:** `admin_remove_queue()` command
    - **Frequency:** 1 call per removal
    - **Latency:** Non-critical
    - **Smoothable:** ✅ YES - **RATE LIMITER CANDIDATE**

28. **Admin Queue Clear Notifications** - `user.send(embed)` (DMs, multiple)
    - **Location:** `admin_clear_queue()` command
    - **Frequency:** N calls (one per player in queue)
    - **Latency:** Non-critical
    - **Smoothable:** ✅ YES - **RATE LIMITER CANDIDATE**
    - **Peak Scenario:** Clearing 100-player queue = 100 API calls
    - **Optimization Strategy:**
      - **MUST use rate limiter with 200ms delay per notification**
      - This spreads 100 calls over 20 seconds

---

## 2. Peak Concurrency Scenarios

### Scenario A: Multiple Simultaneous Matches
**Situation:** 20 matches found in the same matchmaking wave (every 45 seconds)

**API Calls:**
- Match found confirmations: 20 matches × 2 players = **40 calls** (instant)
- Match details messages: 20 matches × 2 players = **40 calls** (instant)
- **Total: 80 API calls within 1-2 seconds**

**Risk:** ⚠️ **HIGH** - Exceeds 50/sec limit

**Mitigation:**
```python
# Stagger match notifications by 100ms per match
for i, match in enumerate(matches):
    await asyncio.sleep(i * 0.1)  # 100ms stagger
    await notify_match_found(match)
# This spreads 80 calls over ~2 seconds = 40 calls/sec
```

### Scenario B: Heavy Queue Load
**Situation:** 100 players queueing simultaneously

**API Calls:**
- Heartbeat updates: 100 players × 1 call per 10 seconds = **10 calls/second** (sustained)
- Join queue actions: 100 players × 2 calls (defer + update) = **200 calls over ~10 seconds** (burst)

**Risk:** ⚠️ **MODERATE** - Sustained load + bursts

**Mitigation:**
```python
# Lazy rate limiter for heartbeat updates
class HeartbeatRateLimiter:
    def __init__(self, min_interval=0.2):  # 200ms between calls
        self.last_call = 0
        self.min_interval = min_interval
        self.queue = asyncio.Queue()
    
    async def send_heartbeat(self, interaction, embed, view):
        await self.queue.put((interaction, embed, view))
    
    async def worker(self):
        while True:
            interaction, embed, view = await self.queue.get()
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            await interaction.edit_original_response(embed=embed, view=view)
            self.last_call = time.time()
```

### Scenario C: Match Completion Burst
**Situation:** 20 matches complete simultaneously

**API Calls:**
- Final result embeds: 20 matches × 2 players = **40 calls** (instant)
- MMR update embeds (if any): variable

**Risk:** ⚠️ **MODERATE-HIGH** - Approaches limit

**Mitigation:**
```python
# Stagger completion notifications
async def send_completion_notifications(matches):
    for i, match in enumerate(matches):
        await asyncio.sleep(i * 0.3)  # 300ms stagger
        await send_match_completion(match)
# Spreads 40 calls over 6 seconds = ~7 calls/sec
```

### Scenario D: Admin Emergency Actions
**Situation:** Admin clears queue with 100 players

**API Calls:**
- Player notifications: **100 DM calls** (instant without limiter)

**Risk:** 🚨 **CRITICAL** - Would exceed limit by 2x

**Mitigation:**
```python
# MANDATORY rate limiter for admin bulk actions
async def send_bulk_notifications(player_ids, embed):
    for i, player_id in enumerate(player_ids):
        await asyncio.sleep(i * 0.2)  # 200ms per notification
        await send_player_notification(player_id, embed)
# 100 calls over 20 seconds = 5 calls/sec
```

---

## 3. Rate Limiter Implementation Strategy

### 3.1 Module-Scoped Lazy Rate Limiter

**Target Operations:**
1. Queue searching heartbeat updates
2. Replay verification messages
3. Admin bulk notifications
4. Match abort notifications
5. Conflict notifications

**Implementation:**

```python
# src/bot/utils/rate_limiter.py
import asyncio
import time
from typing import Callable, Any
from collections import deque

class LazyRateLimiter:
    """
    Lazy rate limiter for non-critical Discord API calls.
    
    Uses a queue-based approach with configurable delay between calls.
    Designed for operations that can tolerate 100ms-500ms delays.
    """
    
    def __init__(self, min_delay_ms: int = 200, max_queue_size: int = 1000):
        """
        Initialize the rate limiter.
        
        Args:
            min_delay_ms: Minimum delay between API calls in milliseconds
            max_queue_size: Maximum number of queued operations
        """
        self.min_delay = min_delay_ms / 1000.0  # Convert to seconds
        self.max_queue_size = max_queue_size
        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.last_call_time = 0
        self.worker_task = None
        self._running = False
    
    def start(self):
        """Start the rate limiter worker."""
        if not self._running:
            self._running = True
            self.worker_task = asyncio.create_task(self._worker())
    
    def stop(self):
        """Stop the rate limiter worker."""
        self._running = False
        if self.worker_task:
            self.worker_task.cancel()
    
    async def submit(self, coro_func: Callable, *args, **kwargs):
        """
        Submit a coroutine for rate-limited execution.
        
        Args:
            coro_func: Async function to call
            *args, **kwargs: Arguments to pass to the function
        """
        try:
            await self.queue.put((coro_func, args, kwargs))
        except asyncio.QueueFull:
            # Drop the request if queue is full
            # This is acceptable for non-critical operations
            print(f"[RateLimiter] Queue full, dropping request")
    
    async def _worker(self):
        """Worker that processes queued operations with rate limiting."""
        while self._running:
            try:
                # Get next operation
                coro_func, args, kwargs = await self.queue.get()
                
                # Calculate required delay
                now = time.time()
                elapsed = now - self.last_call_time
                if elapsed < self.min_delay:
                    delay = self.min_delay - elapsed
                    await asyncio.sleep(delay)
                
                # Execute the operation
                try:
                    await coro_func(*args, **kwargs)
                except Exception as e:
                    print(f"[RateLimiter] Error executing operation: {e}")
                
                # Update last call time
                self.last_call_time = time.time()
                
                # Mark task as done
                self.queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[RateLimiter] Worker error: {e}")

# Global rate limiters for different use cases
heartbeat_limiter = LazyRateLimiter(min_delay_ms=200)  # 5 calls/sec max
notification_limiter = LazyRateLimiter(min_delay_ms=200)  # 5 calls/sec max
admin_limiter = LazyRateLimiter(min_delay_ms=200)  # 5 calls/sec max

# Initialize on bot startup
def initialize_rate_limiters():
    heartbeat_limiter.start()
    notification_limiter.start()
    admin_limiter.start()
```

### 3.2 Integration Points

**Heartbeat Updates (queue_command.py):**
```python
# In QueueSearchingView.periodic_status_update()
async def periodic_status_update(self):
    while self.is_active:
        # ... existing code ...
        async with self.status_lock:
            if not self.is_active:
                continue
            try:
                # BEFORE:
                # await self.last_interaction.edit_original_response(...)
                
                # AFTER:
                from src.bot.utils.rate_limiter import heartbeat_limiter
                await heartbeat_limiter.submit(
                    self.last_interaction.edit_original_response,
                    embed=self.build_searching_embed(),
                    view=self
                )
            except Exception:
                pass
```

**Admin Bulk Notifications (admin_command.py):**
```python
# In admin_clear_queue()
async def confirm_callback(button_interaction: discord.Interaction):
    # ... existing code ...
    
    # BEFORE:
    # for player_id in notif['player_uids']:
    #     await send_player_notification(player_id, player_embed)
    
    # AFTER:
    from src.bot.utils.rate_limiter import admin_limiter
    for player_id in notif['player_uids']:
        await admin_limiter.submit(
            send_player_notification,
            player_id,
            player_embed
        )
```

**Match Notifications (queue_command.py):**
```python
# In handle_match_result()
def handle_match_result(match_result: MatchResult, register_completion_callback):
    # ... existing code ...
    
    # BEFORE:
    # asyncio.create_task(notification_service.publish_match_found(match_result))
    
    # AFTER (with staggering):
    import random
    jitter = random.uniform(0, 0.2)  # 0-200ms random jitter
    
    async def delayed_notification():
        await asyncio.sleep(jitter)
        await notification_service.publish_match_found(match_result)
    
    asyncio.create_task(delayed_notification())
```

---

## 4. API Call Budget Analysis

### 4.1 Baseline Load (Normal Operations)

**Assumptions:**
- 50 players actively queueing at any time
- 10 matches per hour
- 5 command invocations per minute (profile, leaderboard, etc.)

**API Calls Per Second:**
- Heartbeat updates: 50 players ÷ 10 seconds = **5 calls/sec**
- Match notifications: 10 matches × 4 calls ÷ 3600 seconds = **0.01 calls/sec**
- Command responses: 5 calls ÷ 60 seconds = **0.08 calls/sec**
- **Total Baseline: ~5 calls/sec**

### 4.2 Peak Load (Heavy Activity)

**Assumptions:**
- 200 players queueing
- 40 matches per hour (peak matchmaking wave)
- 20 command invocations per minute

**API Calls Per Second:**
- Heartbeat updates (with rate limiter): **5 calls/sec** (limited)
- Match notifications (burst): **80 calls in 2 seconds** = **40 calls/sec** (peak)
- Command responses: 20 ÷ 60 = **0.33 calls/sec**
- **Total Peak: ~45 calls/sec**

### 4.3 Headroom Analysis

**Current Capacity:** 50 calls/sec (Discord rate limit)
**Peak Load:** 45 calls/sec
**Headroom:** **5 calls/sec (10% buffer)**

**Risk Assessment:**
- ⚠️ **LOW BUFFER** - Only 10% headroom during peak
- 🎯 **RECOMMENDATION:** Implement staggering for match notifications
- ✅ **SAFE** with proposed rate limiters in place

---

## 5. Implementation Priority

### Priority 1: Critical (Implement Immediately)
1. **Admin bulk action rate limiter** - Prevents critical limit violations
2. **Match notification staggering** - Prevents peak bursts

### Priority 2: High (Implement Soon)
3. **Heartbeat update rate limiter** - Reduces sustained load
4. **Match completion notification staggering** - Smooths completion bursts

### Priority 3: Medium (Implement If Needed)
5. **Replay verification rate limiter** - Minor optimization
6. **Conflict/abort notification rate limiter** - Edge case optimization

---

## 6. Monitoring Recommendations

### 6.1 Metrics to Track
- API calls per second (moving average)
- Rate limiter queue depth
- Dropped/delayed operations
- User-reported lag on match notifications

### 6.2 Alerting Thresholds
- **Warning:** >40 calls/sec sustained for 10 seconds
- **Critical:** >45 calls/sec sustained for 5 seconds
- **Queue Depth:** >100 operations queued

### 6.3 Logging Strategy
```python
# Add to rate limiter
import logging
logger = logging.getLogger("rate_limiter")

class LazyRateLimiter:
    async def _worker(self):
        while self._running:
            # Log queue depth every 60 seconds
            if time.time() % 60 < 1:
                logger.info(f"[RateLimiter] Queue depth: {self.queue.qsize()}")
            # ... rest of worker code ...
```

---

## 7. Summary & Recommendations

### Key Takeaways

1. **Current Peak Risk:** Match notification bursts can approach 80 calls in 1-2 seconds
2. **Smooth Operations Identified:** 10+ API call types suitable for rate limiting
3. **Headroom:** With proposed changes, ~10% buffer at peak load

### Immediate Actions

1. ✅ Implement `LazyRateLimiter` module
2. ✅ Apply rate limiter to admin bulk actions (CRITICAL)
3. ✅ Add 100-200ms staggering to match notifications
4. ✅ Apply rate limiter to heartbeat updates
5. ✅ Add monitoring for API call rate

### Long-Term Strategy

- Monitor actual production load patterns
- Adjust rate limiter delays based on observed headroom
- Consider dynamic rate limiting (slower during peak, faster during low load)
- Implement circuit breaker for rate limit approaching

---

## Appendix: Complete API Call Catalog

| # | Location | API Call Type | Frequency | Critical? | Smoothable? |
|---|----------|---------------|-----------|-----------|-------------|
| 1 | Queue initial | `send_message` | Per invocation | ✅ Yes | ❌ No |
| 2 | Join queue | `defer` | Per join | ✅ Yes | ❌ No |
| 3 | Join queue | `edit_original_response` | Per join | ✅ Yes | ❌ No |
| 4 | Heartbeat | `edit_original_response` | Every 10s/player | ❌ No | ✅ YES |
| 5 | Match found | `edit_original_response` | Per match/player | ✅ Yes | ❌ No |
| 6 | Match details | `send` | Per match/player | ✅ Yes | ⚠️ Partial |
| 7 | Confirm defer | `defer` | Per confirmation | ✅ Yes | ❌ No |
| 8 | Confirm update | `edit_original_response` | Per confirmation | ✅ Yes | ❌ No |
| 9 | Confirm feedback | `followup.send` | Per confirmation | ❌ No | ✅ YES |
| 10 | Abort prompt | `edit_message` | Per abort start | ✅ Yes | ❌ No |
| 11 | Abort finalize | `edit_message` | Per abort complete | ✅ Yes | ❌ No |
| 12 | Abort notification | `send` | Per abort | ❌ No | ✅ YES |
| 13 | Replay verify | `send` | Per upload | ❌ No | ✅ YES |
| 14 | Replay invalid | `send` | Per invalid | ❌ No | ✅ YES |
| 15 | Result select | `edit_message` | Per selection | ✅ Yes | ❌ No |
| 16 | Result confirm | `edit_message` | Per confirmation | ✅ Yes | ❌ No |
| 17 | Final result | `send` | Per completion | ⚠️ Important | ⚠️ Partial |
| 18 | Conflict | `send` | Per conflict | ❌ No | ✅ YES |
| 19 | Profile | `send_message` | Per invocation | ✅ Yes | ❌ No |
| 20 | Leaderboard | `send_message` | Per invocation | ✅ Yes | ❌ No |
| 21 | Leaderboard nav | `edit_message` | Per action | ✅ Yes | ❌ No |
| 22-28 | Admin commands | Various | Per action | ❌ No | ✅ YES |

**Legend:**
- ✅ Critical: Must respond immediately for UX or Discord API requirements
- ❌ Non-critical: Can be delayed without user impact
- ⚠️ Partial: Can tolerate small delays (100-500ms)
- ✅ Smoothable: Good candidate for rate limiting
- ❌ Not smoothable: Should not be rate limited

---

## Conclusion

The analysis reveals that with targeted rate limiting and staggering, the bot can comfortably operate below the 50 calls/second limit even during peak load scenarios. The most critical implementations are:

1. **Admin bulk action rate limiter** (prevents worst-case overload)
2. **Match notification staggering** (smooths largest burst source)
3. **Heartbeat update rate limiter** (reduces sustained load)

These three changes provide sufficient headroom for growth and unexpected load spikes.
