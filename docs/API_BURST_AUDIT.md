# Discord API Burst Audit

## Executive Summary

After comprehensive audit of the codebase, **match notifications are the ONLY scenario where Discord API calls burst simultaneously**. All other operations are:
- Sequential (one-at-a-time)
- User-initiated (rate limited by user actions)
- Event-driven but individual (1 match = 2 players)

**Verdict**: Two-phase match notification dispatch is sufficient. No other changes needed.

---

## Audit Results by Category

### 1. Match Notifications ⚠️ **BURST RISK**

**Location**: `src/backend/services/matchmaking_service.py` → `Matchmaker.attempt_match()`

**Pattern**:
```python
for p1, p2 in matches:
    match_result = create_match(...)
    self.match_callback(match_result)  # Fires async task
```

**API Calls**:
- Each match = 4 API calls (2 players × 2 messages each)
  1. Edit "Searching..." → "Match Found!"
  2. Send detailed match embed

**Burst Size**:
- 15 matches = 60 API calls simultaneously
- Exceeds 50/sec Discord global limit

**Status**: ❌ **Needs fixing (two-phase dispatch)**

---

### 2. Match Completions ✅ **NO BURST**

**Location**: `src/backend/services/match_completion_service.py` → `_notify_players_match_complete()`

**Pattern**:
```python
async def _notify_players_match_complete(self, match_id: int, final_results: dict):
    callbacks = self.notification_callbacks.pop(match_id, [])  # 2 callbacks (one per player)
    for callback in callbacks:
        await callback(status="complete", data=final_results)
```

**API Calls**:
- Per match completion: 2-4 API calls (edit existing embeds)
- Sequential: `await` on each callback
- Matches complete at different times (5-15 minute durations)

**Burst Analysis**:
- Even if 10 matches completed at exact same moment:
  - Sequential await → 20-40 API calls over ~2-3 seconds
  - Under rate limit

**Status**: ✅ **Safe - no changes needed**

**Why no burst?**:
1. Matches have variable durations (5-15 minutes)
2. Callbacks are awaited sequentially
3. Each completion is independent event

---

### 3. Match Aborts ✅ **NO BURST**

**Location**: `src/backend/services/match_completion_service.py` → `_handle_match_abort()`

**Pattern**:
```python
async def _handle_match_abort(self, match_id: int):
    callbacks = self.notification_callbacks.pop(match_id, [])  # 2 callbacks
    for callback in callbacks:
        await callback(status="abort", data={...})
```

**API Calls**:
- Per abort: 2-4 API calls (edit existing embeds)
- Sequential: `await` on each callback
- Aborts are rare and triggered individually

**Burst Analysis**:
- Worst case: Mass disconnect → 10 matches abort
  - Sequential await → 20-40 API calls over 2-3 seconds
  - Under rate limit

**Status**: ✅ **Safe - no changes needed**

---

### 4. Leaderboard Display ✅ **NO BURST**

**Location**: `src/bot/commands/leaderboard_command.py`

**Pattern**:
```python
@tree.command(name="leaderboard")
async def leaderboard(interaction: discord.Interaction):
    view = LeaderboardView(...)
    await send_ephemeral_response(interaction, embed=embed, view=view)
```

**API Calls**:
- Per user request: 1 ephemeral response
- User-initiated (slash command)
- Rate limited by user behavior

**Burst Analysis**:
- Even if 50 users ran `/leaderboard` simultaneously:
  - Discord queues commands internally
  - Each is separate interaction (different route)
  - No global rate limit hit

**Status**: ✅ **Safe - no changes needed**

**Why no burst?**:
1. Ephemeral responses (private to user)
2. User-initiated (can't trigger programmatically in bulk)
3. Different Discord route per user

---

### 5. Queue Join/Leave ✅ **NO BURST**

**Location**: `src/bot/commands/queue_command.py`

**Pattern**:
```python
async def queue_command(interaction: discord.Interaction):
    view = QueueSearchingView(player)
    await send_ephemeral_response(interaction, embed=embed, view=view)
```

**API Calls**:
- Per user: 1 ephemeral response when joining queue
- User-initiated (button click)

**Burst Analysis**:
- Even if 30 players join queue in same second:
  - Each is ephemeral (separate route)
  - No shared rate limit bucket
  - No burst

**Status**: ✅ **Safe - no changes needed**

---

### 6. Match Confirmation Prompts ✅ **NO BURST**

**Location**: Already part of match notifications (covered in #1)

**Pattern**:
- Confirmation prompts are sent as part of the match found flow
- Same burst risk as match notifications
- Will be fixed by two-phase dispatch

**Status**: ✅ **Will be fixed by match notification changes**

---

### 7. Replay Upload Notifications ✅ **NO BURST**

**Location**: `src/bot/commands/queue_command.py` → `store_replay_background()`

**Pattern**:
```python
async def store_replay_background(...):
    # Process replay
    # Update match view
    await match_view._edit_original_message(embed, view)
```

**API Calls**:
- Per replay: 1 edit to existing message
- Happens at different times (players upload at different speeds)
- Sequential processing

**Burst Analysis**:
- Replays trickle in over time (not simultaneous)
- Each is independent edit
- No burst possible

**Status**: ✅ **Safe - no changes needed**

---

### 8. Admin Commands ✅ **NO BURST**

**Location**: `src/bot/commands/admin_command.py`

**Pattern**:
```python
@tree.command(name="admin")
async def admin_command(interaction: discord.Interaction):
    # Admin performs single action
    await interaction.response.send_message(...)
```

**API Calls**:
- Per admin action: 1-2 API calls
- Manual one-at-a-time operations
- No bulk operations implemented

**Burst Analysis**:
- Admin actions are manual and individual
- No "bulk MMR adjust" or "mass message" features
- No burst risk

**Status**: ✅ **Safe - no changes needed**

**Note**: If bulk admin operations are added in future, implement batching.

---

### 9. System Announcements ✅ **NOT IMPLEMENTED**

**Location**: N/A

**Pattern**: No broadcast or announcement system exists

**Status**: ✅ **N/A - feature doesn't exist**

**Future Consideration**: If implementing announcements to all players:
- **DO**: Use batching (same as match notifications)
- **DON'T**: Send to 200 players simultaneously

---

### 10. Scheduled Jobs ✅ **NO BURST**

**Location**: N/A (no cron jobs or scheduled tasks)

**Pattern**: 
- Leaderboard recalculation is in-memory (no Discord API)
- No scheduled Discord messages

**Status**: ✅ **Safe - no scheduled API calls**

---

## Burst Risk Matrix

| Feature | Max Concurrent | API Calls | Discord Limit | Burst Risk | Mitigation Needed? |
|---------|----------------|-----------|---------------|------------|-------------------|
| **Match Notifications** | 15+ matches | 60+ calls | 50/sec | ❌ **HIGH** | ✅ **Two-phase dispatch** |
| Match Completions | 10 matches | 20-40 calls (sequential) | 50/sec | ✅ Low | ❌ No |
| Match Aborts | 10 matches | 20-40 calls (sequential) | 50/sec | ✅ Low | ❌ No |
| Leaderboard | 50 users | 50 calls (separate routes) | 50/sec | ✅ Low | ❌ No |
| Queue Join/Leave | 30 users | 30 calls (ephemeral) | 50/sec | ✅ Low | ❌ No |
| Replay Uploads | 20 players | 20 calls (staggered) | 50/sec | ✅ Low | ❌ No |
| Admin Commands | 1 admin | 1-2 calls | 50/sec | ✅ None | ❌ No |

---

## Why Match Notifications Are Unique

Match notifications are the ONLY burst scenario because:

1. ✅ **Programmatically triggered** - not user-initiated
2. ✅ **Bulk operation** - all matches in wave fire at once
3. ✅ **Same time window** - 45-second wave boundaries
4. ✅ **High multiplier** - 4 API calls per match
5. ✅ **Shared route** - all edits/sends use same Discord endpoints

All other operations lack at least one of these properties:
- **Completions/Aborts**: Sequential await (not parallel)
- **Leaderboard/Queue**: User-initiated (naturally rate limited)
- **Replays**: Staggered timing (not simultaneous)
- **Admin**: Manual one-at-a-time (no bulk)

---

## Code Patterns Analysis

### ❌ Burst Pattern (BAD)

```python
# BAD: All API calls fire simultaneously
matches = find_all_matches()
for match in matches:
    asyncio.create_task(send_notification(match))  # Fires immediately
```

**Result**: N × API calls at exact same moment

### ✅ Sequential Pattern (SAFE)

```python
# GOOD: API calls are awaited one-at-a-time
for match in completed_matches:
    await process_completion(match)  # Wait for each
```

**Result**: N × API calls spread over time

### ✅ User-Initiated Pattern (SAFE)

```python
# GOOD: Each user triggers their own call
@tree.command()
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.send_message(...)  # Separate route per user
```

**Result**: Discord internally queues these

---

## Recommendations

### Immediate (Before Launch)

1. ✅ **Implement two-phase match notification dispatch**
   - Only burst scenario identified
   - ~2-3 hours implementation
   - Prevents rate limiting at 15+ matches

### Monitor Post-Launch

2. 📊 **Track "matches per wave" metric**
   - Alert if > 12 matches
   - Early warning for rate limit risk

### If Adding New Features

3. 🔍 **Audit for burst patterns when implementing:**
   - **Broadcast/announcement systems** → Use batching
   - **Bulk admin operations** → Use batching
   - **Scheduled mass messages** → Use batching
   - **Event triggers affecting many users** → Use batching

### Checklist for New Features

Ask these questions:

1. ❓ **Does it trigger programmatically** (not user-initiated)?
2. ❓ **Does it affect multiple users at once** (> 10)?
3. ❓ **Do all API calls fire at the same time**?
4. ❓ **Does each user require multiple API calls**?

If **ALL FOUR** are "yes" → **Use batching**

---

## Conclusion

**Single Point of Risk**: Match notifications in matchmaking waves

**Fix**: Two-phase staggered dispatch

**Status**: All other systems are safe by design (sequential, user-initiated, or individually triggered)

**Confidence**: ✅ High - comprehensive audit completed, no other burst risks identified

