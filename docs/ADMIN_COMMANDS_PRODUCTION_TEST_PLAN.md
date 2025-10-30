# Admin Commands: Production Test Plan

## 🎯 Quick Test Sequence (15 minutes)

### Setup
- **Main Account:** Admin with Discord ID in `data/misc/admins.json`
- **Alt Account:** Regular player for testing

---

## Test 1: Queue Removal (CRITICAL FIX)

**Tests:** Queue sync, username resolution, notification

```bash
# Alt: Join queue
/queue

# Main: Remove alt by username
/admin remove_queue user="@AltUsername" reason="Production test"
[Click: Admin Confirm]
```

**Expected:**
- ✅ Alt removed from matchmaking queue immediately
- ✅ Alt receives DM: "🚨 Admin Action: Removed from Queue..."
- ✅ Alt CANNOT get matched in next cycle
- ✅ Admin sees success confirmation

**If this fails:** Queue sync is broken

---

## Test 2: MMR Adjustment (NEW FEATURE)

**Tests:** MMR operations, username resolution, notifications

```bash
# Main: Adjust alt's MMR
/admin adjust_mmr user="@AltUsername" race="bw_zerg" operation="Add" value="50" reason="Test bonus"
[Click: Admin Confirm]
```

**Expected:**
- ✅ Alt's MMR increases by 50
- ✅ Alt receives DM: "📊 Admin Action: MMR Adjusted..."
- ✅ Shows old MMR → new MMR with change (+50)
- ✅ Leaderboard reflects new MMR

---

## Test 3: Queue Clear (CRITICAL FIX)

**Tests:** Emergency controls, mass notifications

```bash
# Alt1 & Alt2: Both join queue
/queue

# Main: Clear entire queue
/admin clear_queue reason="Emergency test"
[Click: Admin Confirm]
```

**Expected:**
- ✅ Both alts removed from queue
- ✅ Both receive DM: "🚨 Admin Action: Queue Cleared..."
- ✅ Shows count of removed players
- ✅ Queue actually empty (verify with `/admin snapshot`)

---

## Test 4: System Snapshot (READ-ONLY)

**Tests:** Inspection tools

```bash
# Main: Get system state
/admin snapshot
```

**Expected:**
- ✅ Shows memory usage
- ✅ Shows DataFrame statistics
- ✅ Shows queue size (should be 0 after Test 3)
- ✅ Shows active matches
- ✅ Shows write queue depth

---

## Test 5: Player State (USERNAME RESOLUTION)

**Tests:** User lookup by different methods

```bash
# Main: Lookup by mention
/admin player user="@AltUsername"

# Main: Lookup by username (no @)
/admin player user="AltUsername"

# Main: Lookup by Discord ID
/admin player user="123456789012345678"
```

**Expected:**
- ✅ All three methods find the same player
- ✅ Shows MMR, queue status, active matches
- ✅ Shows recent match history

---

## Test 6: Match Conflict Resolution (IF APPLICABLE)

**Tests:** Conflict resolution + notifications

*Skip if no conflicts exist*

```bash
# Get conflict match ID from logs or:
/admin snapshot
# Look for matches with result = -2

# Main: Resolve conflict
/admin resolve match_id="123" winner="Player 1 Wins" reason="Replay verified P1 win"
[Click: Admin Confirm]
```

**Expected:**
- ✅ Match result updated
- ✅ MMR calculated and applied
- ✅ Both players receive DM: "⚖️ Admin Action: Match Conflict Resolved..."
- ✅ Shows MMR changes in notification

---

## Test 7: Abort Reset (BONUS)

**Tests:** Player stat modification

```bash
# Main: Reset abort count
/admin reset_aborts user="@AltUsername" new_count="3" reason="Grace period"
[Click: Admin Confirm]
```

**Expected:**
- ✅ Alt's abort count updated to 3
- ✅ Shows old count → new count
- ✅ Persisted to database

---

## Test 8: Button Security

**Tests:** Admin button restrictions

```bash
# Main: Start any admin command with confirmation
/admin adjust_mmr user="@AltUsername" race="bw_zerg" operation="Add" value="10" reason="Test"
[DON'T click buttons yet]

# Alt: Try to click the "Admin Confirm" button on Main's message
```

**Expected:**
- ✅ Alt sees error: "🚫 Admin Button Restricted"
- ✅ Message shows which admin can interact
- ✅ Only Main can click the buttons

---

## 🚨 Critical Tests (MUST PASS)

### Priority 1: Queue Sync
- **Test 1** (remove_queue) - Alt must be removed from REAL queue
- **Test 3** (clear_queue) - Queue must actually clear

**Why Critical:** This was the original bug you reported

### Priority 2: Notifications
- All commands must send DM notifications
- Players must know when admin actions affect them

### Priority 3: Username Resolution
- All three formats (@user, user, ID) must work
- Makes admin commands practical to use

---

## ⚡ Express Test (5 minutes)

**If short on time, run this minimal sequence:**

1. Alt joins queue
2. `/admin clear_queue reason="Quick test"`
3. Verify alt removed (check `/admin snapshot`, queue size = 0)
4. Verify alt received DM
5. `/admin adjust_mmr user="@AltUsername" race="bw_zerg" operation="Add" value="10" reason="Test"`
6. Verify MMR changed
7. Verify alt received DM

**If all pass:** System working correctly

---

## 📋 Expected Log Output

Watch terminal for these confirmations:

```
[AdminService] Removed player 123456789 from matchmaking queue
   Synced removal of player 123456789 from QueueService
[AdminService] Sent notification to user 123456789

[AdminService] Updated MMR via DataAccessService: 123456789/bw_zerg: 1500 -> 1550 (operation: add 50)
[AdminService] Invalidated leaderboard cache
[AdminService] Refreshed ranking service
[AdminService] Sent notification to user 123456789

[AdminService] EMERGENCY: Cleared matchmaker queue (2 players)
[AdminService] EMERGENCY: Cleared QueueService
[AdminService] Sent notification to user 123456789
[AdminService] Sent notification to user 987654321
```

---

## 🐛 Troubleshooting

### If Queue Commands Don't Work:
- Check logs for "Synced to QueueService"
- Verify Matchmaker and QueueService both show changes
- Check bot restart (must sync on startup)

### If Notifications Don't Work:
- Check alt's DM settings (must allow DMs from server)
- Check logs for "Cannot DM user (DMs disabled or blocked)"
- Fallback: Commands still work, just no notification

### If Username Resolution Fails:
- Ensure alt has registered with bot (`/setup`)
- Ensure username in database matches Discord username
- Fallback: Use numeric Discord ID

---

## ✅ Success Criteria

**All systems working if:**
1. ✅ Queue commands affect REAL matchmaking queue
2. ✅ Players receive DM notifications
3. ✅ Can use @username instead of Discord IDs
4. ✅ Only calling admin can click buttons
5. ✅ All actions logged to audit trail
6. ✅ No crashes or linter errors

**Test Duration:** 15 minutes full, 5 minutes express

**Ready to test!** 🚀

