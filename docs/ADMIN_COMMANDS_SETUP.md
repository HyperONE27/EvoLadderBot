# Admin Commands Setup Guide

This guide explains how to set up and use the admin command system in EvoLadderBot.

## Overview

The admin system provides:
- **Layer 1: Inspection Tools** - View system state, conflicts, player/match details (read-only, safe)
- **Layer 2: Controlled Modifications** - Resolve conflicts, adjust MMR, manage queue (atomic updates)
- **Layer 3: Emergency Controls** - Clear queue, restart services (use with caution)

All admin actions are logged to the database for audit trail purposes.

## Setup

### 1. Database Migration

Run the migration script to create the `admin_actions` table:

```bash
python scripts/add_admin_actions_table.py
```

This creates:
- `admin_actions` table for audit logging
- Indexes for efficient querying
- Foreign key constraints for data integrity

### 2. Environment Configuration

Add admin role and user IDs to your environment variables:

```env
# Admin Role IDs (comma-separated Discord role IDs)
ADMIN_ROLE_IDS=123456789012345678,234567890123456789

# Admin User IDs (comma-separated Discord user IDs)
ADMIN_USER_IDS=345678901234567890,456789012345678901
```

**How to get Discord IDs:**
1. Enable Developer Mode in Discord (User Settings → Advanced → Developer Mode)
2. Right-click on a role → Copy ID (for role IDs)
3. Right-click on a user → Copy ID (for user IDs)

**Railway/Production:**
- Set these as environment variables in your Railway dashboard
- Navigate to: Project → Variables → Add Variable

**Local Development:**
- Add to your `.env` file or export in your shell
- The bot will automatically load them from environment variables

### 3. Verify Installation

After starting the bot, verify admin commands are available:

```
/admin snapshot    - Should show system state
/admin conflicts   - Should list any match conflicts
```

If you see "Access Denied", verify:
1. Your Discord ID is in `ADMIN_USER_IDS` **OR**
2. You have a role whose ID is in `ADMIN_ROLE_IDS`

## Admin Commands Reference

### Inspection Commands (Layer 1 - Read-Only)

#### `/admin snapshot`
Get complete system state snapshot including:
- Memory usage (RSS, VMS, percentage)
- DataFrame statistics (rows, size for each table)
- Queue status (number of players, wait times)
- Active matches count
- Write queue depth and success rate
- Process pool health

**Use case:** Diagnose performance issues, check system health

---

#### `/admin conflicts`
List all matches with conflicting reports (match_result = -2).

Shows:
- Match ID
- Player names and races
- Each player's report (I won, I lost, etc.)
- Whether replays were uploaded

**Interactive GUI:** Select a conflict from dropdown to resolve it with buttons.

**Use case:** Quickly find and resolve disputes

---

#### `/admin player <discord_id>`
View complete player state including:
- Basic info (name, country, region, remaining aborts)
- MMR for all races (with games played/won/lost)
- Queue status (in queue? wait time? selected races?)
- Active matches (with reports and status)
- Recent match history

**Interactive GUI:** Includes "Adjust MMR" button for quick modifications.

**Use case:** Debug stuck players, investigate complaints

---

#### `/admin match <match_id>`
View complete match state including:
- Match data (result, status, players)
- Player information
- Monitoring status (is_monitored, is_processed, has_waiter)
- Reports from both players
- Replay paths

Outputs full state as JSON file for detailed inspection.

**Use case:** Debug match completion issues, investigate conflicts

---

### Modification Commands (Layer 2 - Controlled)

#### `/admin resolve <match_id> <winner> <reason>`
Manually resolve a match conflict.

**Parameters:**
- `match_id`: The match ID with conflict
- `winner`: 
  - `1` = Player 1 wins
  - `2` = Player 2 wins
  - `0` = Draw
  - `-1` = Invalidate (no MMR change)
- `reason`: Explanation for audit log (required)

**What it does:**
1. Updates match result in database
2. Updates in-memory DataFrame
3. Calculates and applies MMR changes (unless invalidated)
4. Notifies players of result
5. Logs admin action to database

**Use case:** Resolve disputes when one player clearly cheated, disconnected, or you have external evidence

**Example:**
```
/admin resolve match_id:12345 winner:1 reason:"Player 2 admitted they disconnected"
```

---

#### `/admin adjust_mmr <discord_id> <race> <new_mmr> <reason>`
Adjust a player's MMR for a specific race.

**Parameters:**
- `discord_id`: Player's Discord ID
- `race`: Race to adjust (e.g., `bw_terran`, `sc2_zerg`)
- `new_mmr`: New MMR value (integer)
- `reason`: Explanation for audit log (required)

**What it does:**
1. Updates MMR in database
2. Updates in-memory DataFrame
3. Invalidates leaderboard cache
4. Invalidates player's ranking cache
5. Logs admin action to database

**Use case:** Correct MMR after bugs, apply penalties for misconduct, adjust starting MMR

**Example:**
```
/admin adjust_mmr discord_id:123456789 race:bw_terran new_mmr:1500 reason:"Bug caused incorrect calculation"
```

---

#### `/admin remove_queue <discord_id> <reason>`
Force remove a player from the matchmaking queue.

**Parameters:**
- `discord_id`: Player's Discord ID
- `reason`: Explanation for audit log (required)

**What it does:**
1. Removes player from queue immediately
2. Logs admin action to database

**Use case:** Player stuck in queue, can't leave normally

**Example:**
```
/admin remove_queue discord_id:123456789 reason:"Player reported stuck in queue"
```

---

#### `/admin reset_aborts <discord_id> <new_count> <reason>`
Reset a player's abort count.

**Parameters:**
- `discord_id`: Player's Discord ID
- `new_count`: New abort count (integer)
- `reason`: Explanation for audit log (required)

**What it does:**
1. Updates remaining_aborts in database
2. Updates in-memory DataFrame
3. Logs admin action to database

**Use case:** Forgive legitimate disconnects, reset after false penalties

**Example:**
```
/admin reset_aborts discord_id:123456789 new_count:3 reason:"Aborts were due to server issues"
```

---

### Emergency Commands (Layer 3 - Nuclear)

#### `/admin clear_queue <reason>`
**⚠️ EMERGENCY COMMAND ⚠️**

Clear the entire matchmaking queue immediately.

**Parameters:**
- `reason`: Explanation for audit log (required)

**What it does:**
1. Removes ALL players from queue
2. Returns count of removed players
3. Logs admin action to database

**Use case:** Queue is in corrupted state, matchmaker stuck, need immediate reset

**Warning:** This disrupts all players currently waiting. Use only when necessary.

**Example:**
```
/admin clear_queue reason:"Queue corrupted after server restart"
```

---

## Interactive GUI Features

The admin system includes Discord UI components for better UX:

### Conflict Resolution GUI
When you use `/admin conflicts`:
1. See a list of all conflicts with player names and reports
2. Select a conflict from dropdown menu
3. See detailed conflict information
4. Click buttons: "Player 1 Wins" | "Player 2 Wins" | "Draw" | "Invalidate"
5. Enter reason in modal popup
6. Conflict resolved automatically

**Benefits:** No need to type match IDs, visual confirmation, harder to make mistakes

---

### MMR Adjustment GUI
When you use `/admin player`:
1. See full player state
2. Click "Adjust MMR" button
3. Modal opens with fields for race, new MMR, and reason
4. Submit modal
5. MMR updated automatically

**Benefits:** Context-aware, see current MMR while adjusting, type-safe input

---

## Audit Trail

All admin actions are logged to the `admin_actions` table with:
- Admin Discord ID and username
- Action type (e.g., `resolve_conflict`, `adjust_mmr`)
- Target player/match (if applicable)
- Full action details (JSON)
- Reason provided
- Timestamp

**View recent admin actions:**
```sql
SELECT 
    performed_at,
    admin_username,
    action_type,
    target_player_uid,
    target_match_id,
    reason
FROM admin_actions
ORDER BY performed_at DESC
LIMIT 20;
```

**View specific admin's actions:**
```sql
SELECT * FROM admin_actions
WHERE admin_discord_uid = 123456789
ORDER BY performed_at DESC;
```

**View actions on specific player:**
```sql
SELECT * FROM admin_actions
WHERE target_player_uid = 987654321
ORDER BY performed_at DESC;
```

---

## Safety Guidelines

### Before Modifying State:
1. ✅ Get current state snapshot (`/admin snapshot` or `/admin player`)
2. ✅ Verify issue exists (check conflict list, player state)
3. ✅ Document reason (always provide clear explanation)
4. ✅ Test in staging first (if possible)
5. ✅ Have rollback plan (know how to reverse)

### After Modification:
1. ✅ Verify change took effect (check snapshot/player state again)
2. ✅ Monitor for side effects (watch for 5-10 minutes)
3. ✅ Document outcome (note in Discord admin channel)
4. ✅ Check audit log was written (query `admin_actions` table)

### Never:
- ❌ Modify database directly without using AdminService
- ❌ Skip providing a reason
- ❌ Use emergency controls unless absolutely necessary
- ❌ Modify state during active matchmaking wave (wait for quiet period)
- ❌ Adjust MMR without checking current value first

---

## Common Scenarios & Solutions

### Scenario 1: Players Disagree on Match Result
**Problem:** Both players uploaded replays but report different winners

**Solution:**
1. `/admin conflicts` - Find the match
2. Select match from dropdown
3. Download both replays (click replay links in conflict details)
4. Watch replays to determine actual winner
5. Click appropriate button (Player 1 Wins / Player 2 Wins / Draw)
6. Enter reason: "Verified via replay review - Player X had clear victory"

**Time:** 5-10 minutes (including replay review)

---

### Scenario 2: Player Stuck in Queue
**Problem:** Player can't leave queue, shows "already in queue" for new searches

**Solution:**
1. `/admin player <discord_id>` - Verify they're stuck
2. Check "Queue Status" section shows "IN QUEUE"
3. `/admin remove_queue discord_id:<id> reason:"Player stuck in queue"`
4. Verify removal: `/admin player <discord_id>` - should show "Not in queue"

**Time:** 1-2 minutes

---

### Scenario 3: MMR Incorrectly Calculated
**Problem:** Bug caused wrong MMR change, player complains

**Solution:**
1. `/admin player <discord_id>` - Check current MMR
2. Review match history to find problematic match
3. Calculate correct MMR (previous MMR ± correct change)
4. Click "Adjust MMR" button
5. Enter race, correct MMR value, and reason
6. Submit modal

**Time:** 3-5 minutes

---

### Scenario 4: Bot Showing Stale Data
**Problem:** Player says they're not in queue but bot thinks they are

**Solution:**
1. `/admin snapshot` - Check system health
2. `/admin player <discord_id>` - Check player state
3. If queue status wrong: `/admin remove_queue` (fixes stuck state)
4. If broader issue: Contact developer (may need force_reload_dataframe - not in UI yet)

**Time:** 2-5 minutes

---

### Scenario 5: Mass Conflict After Server Crash
**Problem:** Server crashed, multiple matches show conflicts

**Solution:**
1. `/admin conflicts` - See all conflicts
2. For each conflict with replays:
   - Select match
   - Review both player reports
   - If both uploaded replays: review to determine winner
   - If only one uploaded replay: that player likely won
   - If neither uploaded replay: consider invalidating
3. Resolve each individually

**Time:** 5 minutes per conflict

**Tip:** Ask players to resubmit reports if crash caused false conflicts

---

## Troubleshooting

### "Access Denied" when using admin commands
**Cause:** You're not configured as an admin

**Fix:**
1. Verify your Discord ID: Right-click your name → Copy ID
2. Check environment variables: `ADMIN_USER_IDS` should include your ID
3. If using role-based auth: Check `ADMIN_ROLE_IDS` includes your role
4. Restart bot after changing environment variables

---

### Admin commands not showing in Discord
**Cause:** Commands not synced

**Fix:**
1. Check bot startup logs for "Synced X command(s)"
2. Ensure `register_admin_commands(bot.tree)` is called in `main.py`
3. Wait up to 1 hour for Discord to propagate command updates globally
4. Try in DMs with bot (updates faster than in servers)

---

### Modal/Button not responding
**Cause:** View timeout (5 minutes) or bot restart

**Fix:**
1. Run command again to get fresh UI
2. Buttons/modals are single-use - after submission, run command again

---

### "Match not found in memory" error
**Cause:** Match ID doesn't exist or bot restarted recently

**Fix:**
1. Verify match ID is correct
2. Check database directly: `SELECT * FROM matches_1v1 WHERE id = <match_id>`
3. If match exists in DB but not memory: report to developer (rare desync issue)

---

## Performance Considerations

### Command Response Times
- **Inspection commands** (snapshot, conflicts, player, match): < 1 second
- **Modification commands** (resolve, adjust_mmr): 1-3 seconds
- **Emergency commands** (clear_queue): < 1 second

### Resource Usage
- Admin commands use minimal CPU/memory
- Snapshots are lightweight (no heavy computation)
- All operations are async (non-blocking)

### Concurrency
- Multiple admins can use commands simultaneously
- Modifications use database-level locking
- No risk of race conditions

---

## Advanced: Extending Admin Commands

To add new admin commands:

1. **Add method to AdminService** (`src/backend/services/admin_service.py`):
```python
async def your_new_admin_function(self, param1, param2, admin_discord_id, reason):
    # Update database
    # Update memory
    # Invalidate caches
    # Log action
    return {'success': True, ...}
```

2. **Add Discord command** (`src/bot/commands/admin_command.py`):
```python
@admin_group.command(name="your_command", description="...")
@admin_only()
async def admin_your_command(interaction: discord.Interaction, ...):
    result = await admin_service.your_new_admin_function(...)
    # Send result embed
```

3. **Register command** (already done via `register_admin_commands`)

4. **Test thoroughly** in staging environment

5. **Document** in this file

---

## Security Notes

### Who Can Use Admin Commands?
- Users whose Discord ID is in `ADMIN_USER_IDS`
- Users who have a role whose ID is in `ADMIN_ROLE_IDS`

### Audit Trail
- **All** admin actions are logged
- **Cannot** be disabled or bypassed
- Includes admin ID, username, action type, targets, details, and reason

### Best Practices
1. **Limit admin access** - Only trusted users
2. **Use descriptive reasons** - Future you will thank you
3. **Review audit log regularly** - Check for misuse
4. **Separate staging and production** - Test in staging first
5. **Document major actions** - Keep admin channel notes

---

## Support

### Getting Help
- **Documentation:** This file + `docs/ADMIN_TOOLS_ARCHITECTURE.md`
- **Logs:** Check bot console output for `[AdminService]` messages
- **Database:** Query `admin_actions` table for audit trail
- **Developer:** Contact if you encounter bugs or need new features

### Reporting Issues
When reporting admin command issues, include:
1. Command used (exact syntax)
2. Parameters provided
3. Error message or unexpected behavior
4. Your Discord ID (to verify admin permissions)
5. Bot logs (if accessible)

---

## Summary

The admin system provides:
- ✅ **Safe inspection** - View any system state without risk
- ✅ **Controlled modifications** - Fix issues with atomic updates
- ✅ **Interactive GUI** - Buttons and modals for better UX
- ✅ **Full audit trail** - All actions logged permanently
- ✅ **Emergency controls** - Nuclear options when needed

**Remember:** Always provide clear reasons, verify changes took effect, and document major actions!

