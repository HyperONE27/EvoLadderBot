# API Call Distribution Analysis

**Objective:** Verify Discord API usage stays within 5-10 calls/second target

---

## Scenario: 200 Peak Concurrent Users

### User Distribution

**Active Players (180 users = 90 matches):**
- In active matches (playing games)
- Match duration: 10 minutes average

**Queueing Players (20 users):**
- Waiting for matchmaking
- Queue duration: 0-90 seconds

---

## Discord API Call Rate Calculation

### From Active Matches (90 simultaneous)

**Match lifecycle spread over 10 minutes:**
- Total calls per match: 24-28 (from Phase Analysis)
- Match duration: 600 seconds

**Call distribution is NOT uniform** - heavily clustered at start/end:
- **Phase 1-2 (Queue → Start):** 12-14 calls in first 90 seconds
- **Phase 3 (Playing):** 0 calls for 540 seconds (9 minutes)
- **Phase 4-6 (Upload → Complete):** 12-14 calls in last 70 seconds

**Staggered completion assumption:**
- Matches don't all complete simultaneously
- Distributed uniformly: 9 matches/minute (90 matches / 10 min)
- Peak clustering: Up to 3-5 matches per 10-second window

### Sustained Rate (Uniform Distribution)

**Match completions per minute:** 9 matches

**Calls per completion:** 12-14 (Phases 4-6)

**Sustained rate:** 9 × 13 / 60 = **~2.0 calls/second**

### Peak Burst Rate (Clustered Completions)

**Worst case: 5 matches complete within 10 seconds**
- Calls: 5 × 13 = 65 calls
- Rate: 65 / 10 = **6.5 calls/second** (10-second burst)

**More realistic: 3 matches within 10 seconds**
- Calls: 3 × 13 = 39 calls
- Rate: 39 / 10 = **3.9 calls/second**

---

### From Queue Activity (20 users)

**Queue searching view updates:**
- Heartbeat timer: 10 seconds
- 20 users × 1 call per 10s = **2.0 calls/second**

**New players joining queue:**
- Assuming steady flow: ~0.3 players/second (20 players / 60s average queue time)
- Calls per join: 2-3
- Rate: 0.3 × 2.5 = **0.75 calls/second**

---

### From Leaderboard Browsing

**Assumption:** 10% of concurrent users browse leaderboard
- 20 users viewing leaderboard
- Average session: 30 seconds
- Average pages: 5 per session

**Call rate:**
- 20 users × 5 pages / 30 seconds = **3.3 calls/second**

**Note:** Not all users browse constantly, so actual average is lower.  
**Realistic rate:** ~1-2 calls/second sustained

---

### From Other Commands

**Setup/Profile/etc.:**
- Infrequent usage during active play
- Estimate: ~0.5 calls/second

---

## Aggregate Discord API Load

### Sustained (Normal Operation)

| Source | Calls/Second |
|--------|--------------|
| Match operations | 2.0 |
| Queue heartbeats | 2.0 |
| Queue joining | 0.75 |
| Leaderboard browsing | 1.5 |
| Other commands | 0.5 |
| **Total** | **6.75** |

**Result:** ✅ **Within 5-10 target**

---

### Peak Burst (Match Completion Cluster)

| Source | Calls/Second |
|--------|--------------|
| Match completions (burst) | 6.5 |
| Queue heartbeats | 2.0 |
| Queue joining | 0.75 |
| Leaderboard browsing | 1.5 |
| Other commands | 0.5 |
| **Total** | **11.25** |

**Result:** ⚠️ **Slightly above target, but temporary (10-second burst)**

**Note:** Still well below Discord's 50/sec limit

---

## Database Call Rate Calculation

### Database Reads: 0 per second

All reads served from in-memory DataFrames:
- Player info
- MMR data
- Match history
- Preferences
- Leaderboard

**Result:** ✅ **Zero database read load**

---

### Database Writes (Sustained)

**From 90 active matches:**
- 9 completions/minute
- 17 writes per match
- Rate: 9 × 17 / 60 = **2.55 writes/second**

**From queue activity:**
- 20 queuing players
- 2 writes per queue action
- Assuming 1 queue/minute turnover: 20 / 60 × 2 = **0.67 writes/second**

**From other commands:**
- Setup/profile changes: **~0.2 writes/second**

**From command logging:**
- All commands logged: ~1 per user per minute
- 200 users: 200 / 60 = **3.3 writes/second**

### Total Database Write Rate

| Source | Writes/Second |
|--------|---------------|
| Match completions | 2.55 |
| Queue operations | 0.67 |
| Other commands | 0.20 |
| Command logging | 3.30 |
| **Total** | **6.72** |

**Result:** ✅ **Well within capacity (50-100/sec background worker)**

---

### Database Writes (Peak Burst)

**5 matches complete simultaneously:**
- 5 × 17 = 85 writes queued instantly
- Background worker processes at ~50-100/sec
- Queue clears in: 85 / 75 = **~1.1 seconds**

**Result:** ✅ **Easily absorbed by write queue**

---

## Supabase Storage API Calls

### Replay Uploads

**From 90 active matches:**
- 9 completions/minute
- 2 replays per match
- Rate: 18 replays / 60 seconds = **0.3 uploads/second**

**File size:** 400 KB average  
**Transfer time:** ~500ms each  
**Bandwidth:** 0.3 × 400 KB = **120 KB/second**

**Result:** ✅ **Trivial load**

---

## System Resource Usage

### CPU Utilization

**Process Pool (Replay Parsing):**
- 2 workers at 0.5s per replay
- Utilization: 0.3 replays/sec × 0.5s = **15% of pool capacity**

**Background Writer:**
- Processing 6.7 writes/second
- ~10-20ms per write
- Utilization: 6.7 × 0.015 = **~10% of single core**

**Bot Main Process:**
- Event handling, UI updates
- Estimate: **10-20% of single core**

**Total CPU:** ~1-1.5 cores utilized (normal operation)

---

### Memory Utilization

**In-memory DataFrames:** ~130 MB (at 1,500 player DB)  
**Process Pool Workers:** ~100 MB  
**Bot Process:** ~100 MB  
**OS Overhead:** ~50 MB  

**Total:** ~380 MB

**Typical VPS:** 512 MB - 1 GB  
**Utilization:** ~40-75%

**Result:** ✅ **Comfortable headroom**

---

## Network Bandwidth

### Inbound (To Bot)

**Discord events:** ~1-2 KB per interaction  
**Replay uploads:** 0.3 files/sec × 400 KB = 120 KB/sec  

**Total:** ~125 KB/second = **1 Mbps**

---

### Outbound (From Bot)

**Discord API calls:** 8-10/sec × ~2 KB each = 20 KB/sec  
**Supabase uploads:** 120 KB/sec (passthrough)  

**Total:** ~140 KB/second = **1.1 Mbps**

---

**Combined:** ~2.1 Mbps (negligible for modern hosting)

---

## Summary: 200 Concurrent Users

| Metric | Rate | Capacity | Utilization | Status |
|--------|------|----------|-------------|--------|
| **Discord API (sustained)** | 6.75/sec | 50/sec | 13.5% | ✅ Excellent |
| **Discord API (burst)** | 11.25/sec | 50/sec | 22.5% | ✅ Good |
| **DB Reads** | 0/sec | N/A | 0% | ✅ Perfect |
| **DB Writes** | 6.72/sec | 75/sec | 9% | ✅ Excellent |
| **Replay Parsing** | 0.3/sec | 4/sec | 7.5% | ✅ Excellent |
| **Memory** | 380 MB | 512-1024 MB | 40-75% | ✅ Good |
| **CPU** | 1.5 cores | 2-4 cores | 37-75% | ✅ Good |
| **Bandwidth** | 2.1 Mbps | 100+ Mbps | 2% | ✅ Perfect |

---

## Conclusion

**At 200 peak concurrent users:**

✅ **Discord API: 6.75 calls/second sustained - WITHIN TARGET (5-10)**  
✅ **Database reads: 0/second - ZERO LOAD**  
✅ **Database writes: 6.7/second - MINIMAL LOAD**  
✅ **All bottlenecks well below capacity thresholds**

**System operates comfortably at target scale with significant headroom.**

---

## Load Increase Scenarios

### 250 Concurrent Users (+25%)

- Discord API: 8.4/sec sustained → ✅ Still in target
- Replay parsing: 9% utilization → ✅ No issue
- DB writes: 8.4/sec → ✅ No issue

### 300 Concurrent Users (+50%)

- Discord API: 10.1/sec sustained → ⚠️ At upper target limit
- Replay parsing: 11% utilization → ✅ No issue
- DB writes: 10/sec → ✅ No issue

### 400 Concurrent Users (+100%)

- Discord API: 13.5/sec sustained → ⚠️ Above target, but <30% of limit
- Replay parsing: 15% utilization → ✅ No issue
- DB writes: 13.4/sec → ✅ No issue
- **Recommendation:** Increase worker pool to 4

---

## Key Insight

**Your 5-10 Discord API calls/second target is easily met** at 200 concurrent users. The in-memory architecture eliminates database reads entirely, which is the secret to staying well below API limits that would plague traditional bot architectures.

Even if you scaled to 300 concurrent (+50%), you'd still be at the upper end of your target range and using only 20% of Discord's actual limit.

**The architecture is very well-suited for your target scale.** ✅

