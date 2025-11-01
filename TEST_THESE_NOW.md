# 🚨 URGENT: Test These 2 Critical Fixes NOW

## ⚡ Quick Test (2 minutes)

### Test 1: Notifications Work Now
```
/admin adjust_mmr user:@testplayer race:bw_terran operation:Add value:50 reason:Testing notifications
```

**✅ Expected:** Player receives DM
**❌ Before:** No DM, logs showed "bot instance not available"

---

### Test 2: Match Resolution Saves MMR
```
/admin resolve match_id:142 winner:Player1Win reason:Testing MMR save
```

**Then check:**
1. Supabase `matches` table → match_result should be 1, status should be 'completed', mmr_change should have a number
2. Supabase `mmr` table → Players should have updated MMR values
3. `/profile` command → Should show new MMR
4. Match card in Discord → Should show "Player 1 Won" not "Not selected"

**✅ Expected:** All 4 checks pass
**❌ Before:** Calculated but not saved, showed 0 in Supabase

---

## 🔍 What to Look For in Logs

### ✅ SUCCESS (should see):
```
[BotInstance] ✅ Bot instance set successfully: True
[AdminCommand] ✅ Bot instance available, sending notification to <uid>
[AdminService] Updated match 142: result=1, status=completed
[AdminService] MMR calculated and saved: +X
[AdminService] Saved MMR change to match 142
```

### ❌ FAILURE (should NOT see):
```
[AdminCommand] ❌ ERROR: Cannot send notification - bot instance not available
```

---

## 🐛 What Was Fixed

### Bug 1: Bot Instance Import Timing
**Problem:** Imported `_bot_instance` at module load (when None), never updated
**Fix:** Use `get_bot_instance()` function to access dynamically

### Bug 2: Match Resolution Flow
**Problem:** 
- Status set to 'PROCESSING_COMPLETION' not 'completed'
- Used stale match data
- Didn't save MMR change to match record

**Fix:** 
- Set status='completed' immediately
- Get fresh data after update
- Explicitly save MMR change

---

## 📁 Files Changed
- `src/backend/services/process_pool_health.py`
- `src/backend/services/admin_service.py`
- `src/bot/commands/admin_command.py`

All files compile ✅

---

## 🎯 The Smoking Gun Test

**Do this ONE test to verify everything:**
```
1. /admin resolve match_id:142 winner:Player1Win reason:Test
2. Open Supabase matches table
3. Find match 142
4. Check mmr_change column
```

**If mmr_change has a number (not 0, not null) → FIX WORKED ✅**
**If mmr_change is 0 or null → FIX FAILED ❌**

That's it. That's the test that matters most.

