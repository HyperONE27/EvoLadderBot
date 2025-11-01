# 🧪 Test Both Resolution Paths

## Quick Test Plan

### Test 1: Fresh Match (Path 1 - Simulated Reports)
```
1. Find a match that's in progress (no reports yet)
   OR create one by having players match but not report

2. Run: /admin resolve match_id:X winner:Player1Win reason:Test fresh path

3. Check console logs for:
   ✅ "Match X is in fresh state 'IN_PROGRESS' - using simulated reports"
   ✅ "Simulated both players reporting result=1"
   ✅ "Triggering normal completion flow"
   ✅ "Both reports match, handling completion"
   ✅ "MMR calculated: +X"
   ✅ "Notifying 2 callbacks"

4. Check results:
   ✅ Both players receive DM notifications
   ✅ MMR saved in Supabase (not 0!)
   ✅ /profile shows new MMR
   ✅ Match status = 'completed'
   ✅ Snapshot doesn't show match anymore
```

---

### Test 2: Conflict Match (Path 2 - Direct Manipulation)
```
1. Create a conflict:
   - Player 1 reports: "I Won"
   - Player 2 reports: "I Won"
   - Match enters CONFLICT state

2. Verify conflict exists:
   /admin snapshot → Should show match in active matches

3. Run: /admin resolve match_id:Y winner:Player2Win reason:Test terminal path

4. Check console logs for:
   ✅ "Match Y is in terminal state 'CONFLICT' - using direct manipulation"
   ✅ "Removed match Y from processed_matches"
   ✅ "Updated match Y state: result=2, reports=2"
   ✅ "Calling _handle_match_completion directly"
   ✅ "MMR calculated: -X"
   ✅ "Cleared queue locks for both players"

5. Check results:
   ✅ Both players receive DM notifications (admin + completion)
   ✅ MMR saved in Supabase
   ✅ /profile shows updated MMR
   ✅ Match status = 'completed'
   ✅ Snapshot doesn't show match anymore
```

---

## The Key Difference

**Fresh Match Console:**
```
using simulated reports
→ Triggering normal completion flow
→ (async processing by completion service)
```

**Terminal Match Console:**
```
using direct manipulation
→ Calling _handle_match_completion directly
→ (synchronous, waits for completion)
```

---

## Success Criteria

Both tests should result in:
- ✅ MMR calculated correctly
- ✅ MMR saved to Supabase (check `mmr_change` column)
- ✅ Players notified
- ✅ Match no longer monitored
- ✅ Players can re-queue immediately

---

## If Something Fails

**Path 1 Issues:**
- Check if `check_match_completion` was called
- Check if reports were actually written
- Check if completion service is running

**Path 2 Issues:**
- Check if match was removed from processed_matches
- Check if status was reset to in_progress
- Check if _handle_match_completion was called directly

---

## Quick Verification

After resolving any match:

**1. Check Supabase `matches` table:**
```sql
SELECT id, status, match_result, mmr_change, player_1_report, player_2_report
FROM matches_1v1
WHERE id = <match_id>;
```

**Expected:**
- `status` = 'completed'
- `match_result` = 1 or 2 or 0 (not null)
- `mmr_change` = some number (NOT 0 or null)
- `player_1_report` = 1 or 2 or 0 (matches result)
- `player_2_report` = 1 or 2 or 0 (matches result)

**2. Check Supabase `mmr` table:**
```sql
SELECT discord_uid, race, mmr, games_played
FROM mmr_1v1
WHERE discord_uid IN (<player1_uid>, <player2_uid>)
  AND race IN ('<race1>', '<race2>');
```

**Expected:**
- MMR values changed from before
- games_played incremented by 1

**3. Check with /admin snapshot:**
```
/admin snapshot
```

**Expected:**
- Match should NOT appear in "Active Matches" section

---

## The Smoking Gun

**THIS is the test that proves it works:**

```
1. Resolve a match (any state)
2. Check Supabase matches.mmr_change column
3. If it's NOT 0 and NOT null → SUCCESS! ✅
4. If it's 0 or null → Still broken ❌
```

That's the ultimate verification.

