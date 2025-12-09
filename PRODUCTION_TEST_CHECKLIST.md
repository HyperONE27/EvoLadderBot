# Production Testing Checklist

## 🎯 Memory Leak Fix - Production Validation

### Phase 1: Smoke Test (15 minutes)
Run 3 test matches covering all terminal states.

#### Match 1: Complete Flow ✅
- [ ] `/queue` command works
- [ ] Match found, searching view disappears
- [ ] Both players see match embed
- [ ] Upload replay works
- [ ] Select result works
- [ ] Confirm result works
- [ ] Final gold embed appears
- [ ] **Cleanup logs appear** (4 total: 2 searching + 2 match views)

**Expected logs:**
```
🧹 [QueueSearchingView] Deactivated and cleaned up for player X
🧹 [QueueSearchingView] Deactivated and cleaned up for player Y
🧹 [CLEANUP] Starting cleanup for match N
[Cleanup] View cleaned: match=N, channel=...
🧹 [CLEANUP] Starting cleanup for match N
[Cleanup] View cleaned: match=N, channel=...
```

#### Match 2: Abort Flow ❌
- [ ] `/queue` command works
- [ ] Match found
- [ ] One player clicks "Abort"
- [ ] Confirmation dialog appears
- [ ] Player confirms abort
- [ ] Abort embed appears
- [ ] **Cleanup logs appear** (4 total)

#### Match 3: Conflict Flow ⚠️
- [ ] `/queue` command works
- [ ] Match found
- [ ] Both players upload replays
- [ ] Players report DIFFERENT results
- [ ] Conflict embed appears
- [ ] Admin notified
- [ ] **Cleanup logs appear** (4 total)

---

### Phase 2: Regression Checks (10 minutes)

#### Core Functionality
- [ ] Match embeds display correctly
- [ ] Buttons work (Abort, Report Result, Confirm)
- [ ] Dropdown menus work (Result selection)
- [ ] MMR updates correctly
- [ ] Leaderboard updates correctly
- [ ] Replays stored successfully
- [ ] Admin notifications work

#### Edge Cases
- [ ] Player cancels queue → Searching view cleaned up
- [ ] Match times out (no reports) → Still works correctly
- [ ] Multiple matches running simultaneously → No interference
- [ ] Replay upload during match → No issues

---

### Phase 3: Telemetry Validation (Wait 5 min)

After matches complete, wait for next telemetry cycle (every 5 minutes).

**Check logs for:**
```
[Memory] RSS=XMB manager_views=0 channel_map=0 active_views=0 leaked_instances=0-2
```

**Success criteria:**
- [ ] `manager_views` returns to 0 after matches end
- [ ] `channel_map` returns to 0 after matches end  
- [ ] `active_views` returns to 0 after matches end
- [ ] `leaked_instances` stays low (0-5)
- [ ] No warnings: "HIGH manager view count"

---

### Phase 4: Long-Term Monitoring (2-4 hours)

Deploy to production and monitor:

#### Memory Metrics (Railway Dashboard)
- [ ] Memory usage stays flat (not climbing)
- [ ] Memory growth <150MB over 2-4 hours
- [ ] No OOM crashes

#### Log Patterns (Every 30 min)
```bash
# Check cleanup is working
railway logs | grep "\[Cleanup\] View cleaned" | wc -l
# Should equal: (number of matches × 2)

# Check for errors
railway logs | grep -i "cleanup.*error\|cleanup.*exception"
# Should be empty

# Check telemetry
railway logs | grep "\[Memory\]" | tail -5
# Should show low counts
```

---

### 🚨 Rollback Triggers

**Immediately rollback if:**
1. ❌ Any exception in `[Cleanup]` logs
2. ❌ Match flow broken (can't complete/abort/report)
3. ❌ Buttons stop working
4. ❌ Embeds don't display
5. ❌ Telemetry shows leak persists (`active_views` stays >10)
6. ❌ Memory continues climbing (>500MB in 2 hours)

---

### ✅ Success Criteria

**All must be true:**
- ✅ 3 test matches complete without errors
- ✅ Cleanup logs appear for every match
- ✅ Telemetry shows views return to 0
- ✅ No regression in core flows
- ✅ Memory stays flat over 2-4 hours
- ✅ No unexpected errors in logs

---

### 📊 Metrics to Track

| Metric | Before Fix | Target After Fix | How to Check |
|--------|------------|------------------|--------------|
| 12h memory growth | 1GB | <150MB | Railway metrics |
| Views after match | 320+ leaked | 0-2 active | Telemetry logs |
| Cleanup rate | 0% | 100% | Grep cleanup logs |
| Match completion | Working | Still working | Manual test |
| Uptime | Degrades | Indefinite | Railway uptime |

---

## 🎯 Quick Command Reference

### Local Testing
```bash
# Watch for cleanup logs
tail -f logs.txt | grep -E "CLEANUP|Deactivated"

# Count cleanups
grep "View cleaned" logs.txt | wc -l
```

### Production Testing
```bash
# Stream logs and watch for cleanup
railway logs --follow | grep -E "CLEANUP|Deactivated"

# Check telemetry
railway logs | grep "\[Memory\]" | tail -10

# Count successful cleanups
railway logs --since 1h | grep "View cleaned" | wc -l

# Check for errors
railway logs --since 1h | grep -i "error.*cleanup"
```

---

## 📝 Notes

- Cleanup should happen **after** final embeds are sent
- Each match produces **4 cleanup events** (2 searching views + 2 match views)
- Telemetry updates every **5 minutes**
- Memory reduction won't be instant - takes 1-2 GC cycles
- Python GC typically runs every few minutes under normal load

