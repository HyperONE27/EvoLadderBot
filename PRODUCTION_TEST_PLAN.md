# 🧪 Admin Commands - Production Test Plan

## ✅ Completed Implementations

### Phase 1: Critical Fixes
- ✅ Bot instance notification debugging added
- ✅ Queue-locked state bug fixed
- ✅ Resolve Match command now works on any match
- ✅ Queue locks cleared after admin actions

### Phase 2: Polish
- ✅ Reset Aborts confirmation shows old count
- ✅ Match command has interpretation guide

---

## 🎯 Production Test Checklist

### Pre-Test Setup
- [ ] Deploy to production/staging environment
- [ ] Verify bot is online and responsive
- [ ] Have 2 test accounts ready (one admin, one regular player)
- [ ] Have Discord DMs enabled on test accounts

---

## Test Suite 1: Bot Instance & Notifications

### Test 1.1: Verify Bot Instance is Set
**Expected in logs:**
```
[BotInstance] ✅ Bot instance set successfully: True
[BotInstance] Bot user: YourBotName#1234
```

**If fails:** Bot notifications will not work. Check `bot_setup.py` line 412.

---

### Test 1.2: Admin Adjust MMR with Notification
**Steps:**
1. `/admin adjust_mmr user:@testplayer race:bw_terran operation:Add value:50 reason:Test`
2. Click "Admin Confirm"

**Expected Results:**
- ✅ Admin sees success message with old/new MMR
- ✅ Player receives DM notification with:
  - Title: "📊 Admin Action: MMR Adjusted"
  - Old MMR, New MMR, Change
  - Reason and Admin name
- ✅ Console shows: `[AdminCommand] ✅ Bot instance available, sending notification to <uid>`

**If fails:** Check logs for `[AdminCommand] ❌ ERROR: Cannot send notification`

---

### Test 1.3: Admin Reset Aborts with Notification
**Steps:**
1. `/admin reset_aborts user:@testplayer new_count:5 reason:Test reset`
2. Verify confirmation shows "Current Aborts: X"
3. Click "Admin Confirm"

**Expected Results:**
- ✅ Confirmation embed shows current abort count
- ✅ Player receives DM notification
- ✅ Success embed shows old count → new count

---

## Test Suite 2: Queue-Locked State Fix

### Test 2.1: Remove Player from Queue
**Setup:**
1. Have test player join queue (`/queue`)
2. Select race and click "Join Queue"
3. Verify player is searching for match

**Test Steps:**
1. Admin: `/admin remove_queue user:@testplayer reason:Testing queue removal`
2. Click "Admin Confirm"
3. Player: Try to `/queue` again immediately

**Expected Results:**
- ✅ Player is removed from queue
- ✅ Player receives DM notification about removal
- ✅ **CRITICAL:** Player can immediately re-queue without "already in queue" error
- ✅ Console shows: `[AdminService] Cleared queue view for player <uid>`

**If fails:** Player gets "You are already in a queue or an active match" error
- Check `_clear_player_queue_lock` was called
- Check `queue_searching_view_manager` import

---

### Test 2.2: Clear Entire Queue
**Setup:**
1. Have 2 test players join queue
2. Both should be in "Searching for match" state

**Test Steps:**
1. Admin: `/admin clear_queue reason:Testing queue clear`
2. Click "Admin Confirm"
3. Both players: Try to `/queue` again immediately

**Expected Results:**
- ✅ Both players removed from queue
- ✅ Both players receive DM notifications
- ✅ **CRITICAL:** Both can immediately re-queue
- ✅ Console shows cleared queue locks for both players

---

### Test 2.3: Queue Lock After Match Resolution
**Setup:**
1. Create a match with conflicting reports (or any stuck match)
2. Note the match ID

**Test Steps:**
1. Admin: `/admin resolve match_id:<id> winner:Player1Win reason:Testing`
2. Click "Admin Confirm"
3. Both players: Try to `/queue`

**Expected Results:**
- ✅ Match is resolved
- ✅ Both players receive DM notifications
- ✅ **CRITICAL:** Both can immediately queue again
- ✅ Console shows: `[AdminService] Cleared queue locks for both players in match <id>`

---

## Test Suite 3: Resolve Match Command

### Test 3.1: Resolve Any Match (Not Just Conflicted)
**Setup:**
1. Have any match in database (in_progress, completed, or conflicted)
2. Note the match ID

**Test Steps:**
1. Admin: `/admin resolve match_id:<id> winner:Draw reason:Admin override`
2. Click "Admin Confirm"

**Expected Results:**
- ✅ Works on ANY match status (not just conflicted)
- ✅ If already completed, console shows warning but still processes
- ✅ Both players notified
- ✅ MMR updated correctly
- ✅ Match result changed

**Old Behavior (Fixed):**
- ❌ Would reject with "Match is not in conflict state"

---

### Test 3.2: Resolve with Each Result Type
**Test each resolution type:**

**3.2a: Player 1 Win**
1. `/admin resolve match_id:<id> winner:Player1Win reason:Test`
2. Verify P1 gains MMR, P2 loses MMR

**3.2b: Player 2 Win**
1. `/admin resolve match_id:<id> winner:Player2Win reason:Test`
2. Verify P2 gains MMR, P1 loses MMR

**3.2c: Draw**
1. `/admin resolve match_id:<id> winner:Draw reason:Test`
2. Verify both players' MMR adjusted for draw

**3.2d: Invalidate**
1. `/admin resolve match_id:<id> winner:Invalidate reason:Test`
2. Verify NO MMR changes for either player
3. Verify match marked as invalidated

**Expected for all:**
- ✅ Match resolved successfully
- ✅ Both players notified with resolution
- ✅ Players can re-queue immediately

---

## Test Suite 4: Admin Command Improvements

### Test 4.1: Reset Aborts Shows Old Count
**Steps:**
1. Check player's current abort count
2. `/admin reset_aborts user:@testplayer new_count:10 reason:Test`
3. **Look at confirmation embed BEFORE clicking**

**Expected:**
- ✅ Confirmation shows: "Current Aborts: <old_value>"
- ✅ Confirmation shows: "New Count: 10"
- ✅ After confirming, success shows old → new

---

### Test 4.2: Match Command Has Field Guide
**Steps:**
1. `/admin match match_id:<any_id>`

**Expected:**
- ✅ Embed has "📖 Field Guide" section
- ✅ Explains status codes
- ✅ Explains report codes (0/1/2/-1/-3)
- ✅ Explains confirmation status codes
- ✅ If monitored, shows "🔍 Monitoring Status" section
- ✅ JSON file still attached

---

### Test 4.3: Player Command Field Display
**Steps:**
1. `/admin player user:@testplayer`

**Expected:**
- ✅ Shows as separate fields (not one long description)
- ✅ Basic Info field
- ✅ MMRs field (or multiple if many races)
- ✅ Queue Status field
- ✅ Active Matches field
- ✅ No "400 Bad Request" error
- ✅ All fields under 4096 chars each

---

### Test 4.4: Snapshot Command
**Steps:**
1. Have some players in queue
2. Have some active matches
3. `/admin snapshot`

**Expected:**
- ✅ Shows memory usage
- ✅ Shows DataFrame sizes
- ✅ Shows queue size
- ✅ Shows active matches count
- ✅ Shows write queue stats
- ✅ Success rate percentage

**Future Enhancement (Not yet implemented):**
- ⏰ Detailed queue player list
- ⏰ Ongoing match summaries
- ⏰ Additional metrics

---

## Test Suite 5: Error Handling & Edge Cases

### Test 5.1: Invalid User Input
**Steps:**
1. `/admin adjust_mmr user:NonExistentUser123 ...`

**Expected:**
- ✅ Shows: "❌ Could not find user: NonExistentUser123"
- ✅ Does not crash or error out

---

### Test 5.2: Player with DMs Disabled
**Steps:**
1. Have test player disable DMs from server members
2. Admin: `/admin adjust_mmr user:@testplayer ...`
3. Confirm action

**Expected:**
- ✅ Admin action completes successfully
- ✅ Console shows: `[AdminCommand] Cannot DM user <uid> (DMs disabled or blocked)`
- ✅ No crash, graceful handling
- ✅ Admin still sees success message

---

### Test 5.3: Username Resolution
**Test each format:**

**5.3a: Discord Mention**
```
/admin player user:@TestPlayer
```

**5.3b: Username Without @**
```
/admin player user:TestPlayer
```

**5.3c: Discord ID**
```
/admin player user:123456789
```

**Expected for all:**
- ✅ Successfully resolves to player
- ✅ Shows correct player info

---

### Test 5.4: Concurrent Admin Actions
**Steps:**
1. Admin 1: Start MMR adjustment, don't confirm yet
2. Admin 2: Start same MMR adjustment on same player
3. Admin 1: Confirm
4. Admin 2: Confirm

**Expected:**
- ✅ Both confirmations work (last one wins)
- ✅ No deadlocks or crashes
- ✅ Both audit log entries recorded

---

## Test Suite 6: Button Security

### Test 6.1: Button Restriction to Original Admin
**Steps:**
1. Admin 1: `/admin adjust_mmr ...` (don't confirm)
2. Admin 2: Click "Admin Confirm" button on Admin 1's message

**Expected:**
- ✅ Admin 2 sees: "🚫 Admin Button Restricted"
- ✅ Message says "Only <Admin 1> can interact with these buttons"
- ✅ Action does NOT execute
- ✅ Admin 1 can still click later (view stays alive)

---

### Test 6.2: Button Timeout
**Steps:**
1. Admin: `/admin adjust_mmr ...`
2. Wait GLOBAL_TIMEOUT seconds (default 5 minutes)
3. Try to click button

**Expected:**
- ✅ Buttons become disabled/grayed out
- ✅ Clicking shows "Interaction failed" (expected Discord behavior)
- ✅ Console shows: `[AdminConfirmationView] View timed out for admin <id>`

---

## 🔍 Verification Commands

### Check Queue State
```python
# In Python console or debug:
from src.bot.commands.queue_command import queue_searching_view_manager, match_results

# Check if player has active queue view
await queue_searching_view_manager.has_view(discord_uid)  # Should be False after admin remove

# Check if player in match_results
discord_uid in match_results  # Should be False after admin remove
```

### Check Player MMR
```python
from src.backend.services.data_access_service import DataAccessService
data_service = DataAccessService()

# Get player MMR
mmr = data_service.get_player_mmr(discord_uid, 'bw_terran')
print(f"Player MMR: {mmr}")
```

### Check Admin Action Log
```python
from src.backend.services.app_context import admin_service

# View recent admin actions
print(admin_service.action_log[-10:])  # Last 10 actions
```

---

## ⚠️ Known Issues & Workarounds

### Issue: Bot Instance Not Available
**Symptoms:** All notifications fail with "bot instance not available"

**Debug Steps:**
1. Check startup logs for: `[BotInstance] ✅ Bot instance set successfully: True`
2. If missing, check `bot_setup.py` line 412
3. Restart bot

**Workaround:** None - must fix bot_setup

---

### Issue: Queue Lock Persists
**Symptoms:** Player can't re-queue after admin removal

**Debug Steps:**
1. Check console for: `[AdminService] Cleared queue view for player <uid>`
2. If missing, check `_clear_player_queue_lock` was called
3. Manual fix:
```python
await admin_service._clear_player_queue_lock(discord_uid)
```

---

## 📊 Success Criteria

### Phase 1 (Critical) - ALL MUST PASS
- [ ] Bot notifications work for all admin commands
- [ ] Players can re-queue after admin removal
- [ ] Players can re-queue after match resolution
- [ ] Resolve command works on any match

### Phase 2 (Polish) - SHOULD PASS
- [ ] Reset aborts shows old count
- [ ] Match command has field guide
- [ ] Player command displays without errors
- [ ] Snapshot shows all info

### Overall
- [ ] No crashes or unhandled exceptions
- [ ] All admin actions logged
- [ ] All player notifications sent (unless DMs disabled)
- [ ] Button security works correctly
- [ ] No queue-locked states persist

---

## 📝 Test Report Template

```markdown
## Test Run: [Date]

**Environment:** Production / Staging
**Tester:** [Name]
**Bot Version:** [Commit Hash]

### Phase 1 Results
- [ ] Bot Instance & Notifications: PASS / FAIL
- [ ] Queue-Locked State Fix: PASS / FAIL
- [ ] Resolve Match Command: PASS / FAIL

### Phase 2 Results
- [ ] Reset Aborts Improvement: PASS / FAIL
- [ ] Match Command Guide: PASS / FAIL
- [ ] Player Command Display: PASS / FAIL
- [ ] Snapshot Command: PASS / FAIL

### Issues Found
1. [Description]
   - Severity: Critical / High / Medium / Low
   - Steps to reproduce:
   - Expected vs Actual:

### Notes
[Any additional observations]

### Recommendation
[ ] APPROVE for production
[ ] NEEDS FIXES before production
[ ] RETEST required
```

---

## 🚀 Quick Smoke Test (5 minutes)

For quick verification after deployment:

1. **Bot Status:** Verify bot is online
2. **Notification Test:** `/admin adjust_mmr` → Confirm → Check player DM
3. **Queue Lock Test:** Player queues → Admin removes → Player re-queues
4. **Resolve Test:** `/admin resolve` on any match → Verify works
5. **Button Security:** Have 2nd admin try clicking 1st admin's button

If all pass: ✅ Core functionality working
If any fail: ❌ Investigate immediately

---

## 📞 Support

**If tests fail:**
1. Check console logs for specific error messages
2. Verify bot_setup completed successfully
3. Check GLOBAL_TIMEOUT is set in environment
4. Verify admins.json is loaded correctly
5. Check Discord API status

**Critical errors to watch for:**
- `[AdminCommand] ❌ ERROR: Cannot send notification`
- `[AdminService] WARNING: Error clearing queue lock`
- `400 Bad Request (error code: 50035)` (embed too large)
- `Interaction failed` (timeout or button security)

