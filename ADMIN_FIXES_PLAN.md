# 🎯 Admin Commands & Features - Implementation Plan

## 🔴 CRITICAL: Bot Instance Issue (Blocks All Notifications)

### Issue
All admin notifications failing with: `[AdminCommand] Cannot send notification: bot instance not available`

### Root Cause
The global `_bot_instance` in `process_pool_health.py` is not set when admin commands try to send notifications.

### Solution
**Priority: IMMEDIATE**

1. **Verify bot_setup.py calls `set_bot_instance(bot)`**
   - Check `src/bot/bot_setup.py` line ~412
   - Ensure it's called AFTER bot is ready
   - Timing: After event loop is running

2. **Add debugging to confirm bot instance is set**
   ```python
   # In process_pool_health.py
   def set_bot_instance(bot):
       global _bot_instance
       _bot_instance = bot
       print(f"[BotInstance] Set successfully: {bot is not None}")
   ```

3. **Fallback pattern if needed**
   - Store bot in a more accessible location
   - Consider passing bot to admin_service during initialization
   - Or use `interaction.client` directly in admin_command.py

**Estimated Time:** 30 minutes  
**Blocks:** All notification features

---

## 🟠 HIGH PRIORITY: Queue-Locked State Bug

### Issue
When admins clear/remove players from queue, players remain in "queue-locked" state and cannot re-queue.

### Root Cause Analysis Needed
1. **Find where queue-locked state is stored**
   - Check `QueueService._queued_players`
   - Check `Matchmaker.players`
   - Check `match_completion_service.monitored_matches`
   - Check player preferences or flags

2. **Trace the queue join flow**
   - Where is queue-locked checked?
   - What sets it?
   - What clears it?

### Solution Strategy
```
PHASE 1: Investigation (30 min)
- Search for "queue" checks in /queue command
- Find the guard that prevents re-queueing
- Document the state lifecycle

PHASE 2: Fix Admin Commands (1 hour)
- Update emergency_clear_queue() to clear locked state
- Update force_remove_from_queue() to clear locked state
- Add helper method: _clear_player_queue_lock(discord_uid)

PHASE 3: Fix Match Resolution (30 min)
- Ensure resolve_match_conflict() clears queue lock
- Ensure match completion clears queue lock
- Ensure match abort clears queue lock
```

**Estimated Time:** 2 hours  
**Blocks:** Clear Queue, Remove Queue features

---

## 🟡 MEDIUM PRIORITY: Admin Command Improvements

### 1. Reset Aborts - Confirmation Embed
**Issue:** Confirm embed doesn't show old abort count

**Solution:**
```python
# In admin_command.py, admin_reset_aborts confirmation embed
embed_description = (
    f"**Player:** <@{uid}>\n"
    f"**Current Aborts:** {current_aborts}\n"  # ← ADD THIS
    f"**New Count:** {new_count}\n"
    f"**Reason:** {reason}\n\n"
    f"This will update the player's abort counter. Confirm?"
)
```

**Time:** 15 minutes

---

### 2. Player Command - Match /profile Format
**Issue:** Should follow /profile command formatting with extra admin sections

**Solution:**
1. **Find /profile command formatting**
   - Read `src/bot/commands/` for profile command
   - Extract formatting logic

2. **Refactor format_player_state()**
   ```python
   def format_player_state(state: dict) -> dict:
       fields = []
       
       # Use same formatting as /profile
       fields.extend(format_basic_info_like_profile(state))
       fields.extend(format_mmrs_like_profile(state))
       
       # Add admin-only sections
       fields.append(format_queue_details(state))  # Admin only
       fields.append(format_active_matches_pruned(state))  # Prune to 5 most recent
       fields.append(format_recent_matches(state))  # Admin only
       
       return {'title': '...', 'fields': fields}
   ```

3. **Prune active matches**
   - Show max 5 most recent
   - Add "(and X more...)" if truncated

**Time:** 1 hour

---

### 3. Snapshot Command - Enhanced Details
**Issue:** Needs players in queue, ongoing matches, more metrics

**Solution:**
```python
# In admin_service.py, get_system_snapshot()
snapshot['queue_details'] = {
    'players': [
        {
            'discord_uid': p.discord_user_id,
            'username': p.user_id,
            'races': p.preferences.selected_races,
            'wait_time': time.time() - p.queue_join_time
        }
        for p in matchmaker.players
    ]
}

snapshot['ongoing_matches'] = {
    'match_ids': list(match_completion_service.monitored_matches),
    'match_summaries': [
        {
            'match_id': mid,
            'players': [p1_name, p2_name],
            'status': match_data['status'],
            'duration': time.time() - match_data['created_at']
        }
        for mid in match_completion_service.monitored_matches
    ]
}

snapshot['metrics'] = {
    'avg_queue_wait_time': ...,
    'matches_completed_today': ...,
    'matches_aborted_today': ...,
    'peak_queue_size_today': ...
}
```

**Time:** 1.5 hours

---

### 4. Match Command - Interpretation Guide
**Issue:** JSON payload complete but needs admin guide

**Solution:**
Create inline help in the embed:
```python
embed.add_field(
    name="📖 Field Guide",
    value=(
        "**status:** in_progress/completed/aborted/conflicted\n"
        "**player_X_report:** 0=Draw, 1=Won, 2=Lost, -1=Aborted, -3=I Aborted\n"
        "**match_result:** Same codes as reports\n"
        "**match_result_confirmation_status:** 0=None, 1=P1 Only, 2=P2 Only, 3=Both\n"
        "**is_monitored:** Match completion service tracking\n"
        "**is_processed:** Already finalized"
    ),
    inline=False
)
```

**Time:** 15 minutes

---

## 🔴 CRITICAL: Resolve Match Command - Completely Broken

### Issues
1. Never recognizes conflicted state
2. Should be able to resolve ANY match regardless

### Root Cause
**Hypothesis:** Checking `match_result == 'conflicted'` but field might be numeric or status field is elsewhere

### Investigation Steps
```bash
# 1. Check what "conflicted" looks like in database
SELECT * FROM matches_1v1 WHERE match_result = 'conflicted';
SELECT * FROM matches_1v1 WHERE status = 'conflicted';

# 2. Find conflict detection logic
grep -r "conflicted\|conflict" src/backend/services/match_completion_service.py
```

### Solution
```python
# In admin_service.py, resolve_match_conflict()

# REMOVE strict conflicted check
# if match_data['status'] != 'conflicted':
#     return {'success': False, 'error': 'Match is not in conflicted state'}

# REPLACE with:
# Allow resolution if:
# - Match is not completed
# - OR match has mismatched reports
# - OR admin explicitly overrides

if match_data['status'] == 'completed':
    # Only allow if force=True parameter
    if not force_override:
        return {
            'success': False,
            'error': 'Match already completed. Use force=True to override.'
        }
```

### Enhanced Solution
```python
def resolve_match_conflict(
    self,
    match_id: int,
    resolution: str,
    admin_discord_id: int,
    reason: str,
    force_override: bool = False  # ← NEW
) -> dict:
    """
    Resolve ANY match result.
    
    Args:
        force_override: If True, allows resolving even completed matches
    """
    
    match_data = self.data_service.get_match(match_id)
    
    if not match_data:
        return {'success': False, 'error': 'Match not found'}
    
    # Check if match can be resolved
    if match_data['status'] == 'completed' and not force_override:
        return {
            'success': False,
            'error': 'Match completed. Add force_override=True to change result.'
        }
    
    # Rest of resolution logic...
    # Calculate MMR changes based on resolution
    # Update match_result
    # Update player MMRs
    # Clear queue-locked state for both players ← IMPORTANT!
    # Notify both players
```

**Time:** 2 hours

---

## 🟢 LOW PRIORITY: New Features

### 1. Matchmaking Algorithm Improvements
**Current Issues:**
- Need to review matchmaking algorithm effectiveness
- Check for common pain points

**Investigation:**
```python
# Analyze match quality
matches = data_service.get_recent_matches(days=7)
mmr_differences = [abs(m['p1_mmr'] - m['p2_mmr']) for m in matches]
avg_diff = sum(mmr_differences) / len(mmr_differences)
# If avg_diff > 200, algorithm needs tuning
```

**Potential Improvements:**
- Tighten MMR range for first 30 seconds
- Widen gradually after
- Consider race preferences weight
- Add region preference bonus

**Time:** 3-4 hours

---

### 2. Match Confirmation Reminder
**Feature:** Send reminder to players who don't confirm after half the abort timer

**Solution:**
```python
# In match_completion_service.py, _monitor_match_completion()

abort_deadline = matchmaker.ABORT_TIMER_SECONDS  # e.g., 600s
reminder_time = abort_deadline / 2  # 300s

# After match created:
await asyncio.sleep(reminder_time)

# Check confirmations
confirmations = self.match_confirmations.get(match_id, set())
if player_1_uid not in confirmations:
    await send_reminder_dm(player_1_uid, match_id)
if player_2_uid not in confirmations:
    await send_reminder_dm(player_2_uid, match_id)
```

**Time:** 1.5 hours

---

### 3. BW Protoss Shield Battery Lag Warning
**Feature:** Dismissable message about Shield Battery lag for BW Protoss matches

**Solution:**
```python
# In match notification logic (when match found)
if 'bw_protoss' in [p1_race, p2_race]:
    warning_embed = discord.Embed(
        title="⚠️ Performance Tip: BW Protoss",
        description=(
            "Shield Batteries can cause lag in some game versions.\n\n"
            "**Recommended:**\n"
            "• Use latest Brood War patch\n"
            "• Avoid excessive Shield Batteries early game\n"
            "• Consider Dragoons over Shield Battery walls"
        ),
        color=discord.Color.gold()
    )
    
    # Create view with "Dismiss" button
    view = DismissView()
    await player.send(embed=warning_embed, view=view, ephemeral=True)
```

**Time:** 1 hour

---

### 4. Owner-Only Admin Management Command
**Feature:** `/owner add_admin` and `/owner remove_admin` commands

**Solution:**
```python
# In admin_command.py

def owner_only():
    """Decorator restricting command to owner role"""
    async def predicate(interaction: discord.Interaction) -> bool:
        # Load admins.json
        admin_data = load_admin_data()
        user_id = interaction.user.id
        
        for admin in admin_data:
            if admin['discord_id'] == user_id and admin.get('role') == 'owner':
                return True
        
        await interaction.response.send_message("Owner only", ephemeral=True)
        return False
    
    return app_commands.check(predicate)


owner_group = app_commands.Group(name="owner", description="Owner commands")

@owner_group.command(name="add_admin")
@owner_only()
async def add_admin(
    interaction: discord.Interaction,
    user: discord.User,
    role: str = "admin"  # "admin" or "owner"
):
    """Add a new admin to the bot"""
    
    # Load current admins
    admins = load_admin_data()
    
    # Check if already admin
    if any(a['discord_id'] == user.id for a in admins):
        await interaction.response.send_message(
            f"{user.mention} is already an admin",
            ephemeral=True
        )
        return
    
    # Add new admin
    admins.append({
        'discord_id': user.id,
        'discord_username': user.name,
        'role': role,
        'added_at': datetime.now().isoformat(),
        'added_by': interaction.user.id
    })
    
    # Save to file
    save_admin_data(admins)
    
    # Reload ADMIN_IDS global
    global ADMIN_IDS
    ADMIN_IDS = _load_admin_ids()
    
    await interaction.response.send_message(
        f"✅ Added {user.mention} as {role}",
        ephemeral=True
    )


@owner_group.command(name="remove_admin")
@owner_only()
async def remove_admin(interaction: discord.Interaction, user: discord.User):
    """Remove an admin from the bot"""
    # Similar logic but removes from list
    # Cannot remove self
    # Cannot remove last owner
```

**Time:** 2 hours

---

## 📋 Implementation Order

### Phase 1: Critical Fixes (Day 1)
1. ✅ Bot instance notification fix (30 min) **← START HERE**
2. ✅ Queue-locked state investigation & fix (2 hours)
3. ✅ Resolve Match command fix (2 hours)

**Total: ~4.5 hours**

---

### Phase 2: Admin Command Polish (Day 2)
4. ✅ Reset Aborts confirmation fix (15 min)
5. ✅ Player command /profile formatting (1 hour)
6. ✅ Match command interpretation guide (15 min)
7. ✅ Snapshot command enhancements (1.5 hours)

**Total: ~3 hours**

---

### Phase 3: New Features (Day 3)
8. ✅ Match confirmation reminder (1.5 hours)
9. ✅ BW Protoss lag warning (1 hour)
10. ✅ Owner admin management commands (2 hours)

**Total: ~4.5 hours**

---

### Phase 4: Algorithm Optimization (Day 4 - Optional)
11. ✅ Matchmaking algorithm improvements (3-4 hours)

**Total: ~4 hours**

---

## 🎯 Grand Total Estimate

**Critical Path (Phases 1-2):** ~7.5 hours  
**With New Features (Phases 1-3):** ~12 hours  
**Complete (All Phases):** ~16 hours

**Recommendation:** Focus on Phases 1-2 first to get admin tools fully functional, then tackle Phase 3 features.

---

## 🔍 Testing Checklist

After each phase:

### Phase 1 Tests
- [ ] Admin adjust MMR → Player receives DM
- [ ] Admin clear queue → Players can re-queue immediately
- [ ] Admin remove queue → Player can re-queue immediately
- [ ] Admin resolve match → Works on any match state

### Phase 2 Tests
- [ ] Reset aborts confirmation shows old count
- [ ] Player command matches /profile format
- [ ] Snapshot shows queue details and ongoing matches
- [ ] Match command has interpretation guide

### Phase 3 Tests
- [ ] Players receive confirmation reminder at 50% abort timer
- [ ] BW Protoss players see lag warning (dismissable)
- [ ] Owner can add/remove admins without restart
- [ ] New admins immediately have access

---

## 📝 Notes

- All notification fixes depend on bot instance fix
- Queue-locked state affects multiple commands
- Consider adding integration tests for admin commands
- Document all admin command usage for team

