# Matchmaking Algorithm Analysis - Executive Summary

**Analysis Date:** October 29, 2025  
**Full Report:** [MATCHMAKING_ALGORITHM_ANALYSIS.md](./MATCHMAKING_ALGORITHM_ANALYSIS.md)

---

## TL;DR - Key Takeaways

### Algorithm Status: ✅ CONDITIONALLY READY

The matchmaking algorithm is well-designed but needs parameter tuning before launch.

### Critical Actions Required:

1. **Adjust pressure thresholds**: Lower from (0.30, 0.50) to **(0.15, 0.35)**
2. **Add MMR hard cap**: Implement **400 MMR maximum difference**
3. **Launch target**: Ensure **50+ concurrent players** minimum
4. **Race balance monitoring**: Display queue composition to players

---

## Quick Findings

### What Works Well ✅

- Cross-game BW vs SC2 matching is innovative
- Adaptive MMR windows prevent premature poor matches
- Wait cycle priority prevents player starvation
- Population scaling shows thoughtful design

### What Needs Fixing ⚠️

- **Pressure thresholds too high**: System almost always stays in LOW pressure mode
- **No quality safeguards**: Can create 700+ MMR difference matches
- **Race imbalance vulnerability**: 60/20 split leaves 60% unmatched
- **Small populations suffer**: <50 players = poor experience

---

## Match Experience by Population

| Population | Matches/Wave | Avg Wait Time | Avg MMR Diff | Player Experience |
|------------|--------------|---------------|--------------|-------------------|
| 20 players | 0.05         | ~2-3 min      | 208 MMR      | ❌ Poor          |
| 50 players | 0.14         | ~3-4 min      | 187 MMR      | ⚠️ Fair          |
| 100 players| 0.30         | ~2-3 min      | 146 MMR      | ✅ Good          |

**Verdict**: Need 50+ concurrent players for acceptable experience.

---

## Recommended Parameter Changes

```python
# CURRENT → RECOMMENDED

# Pressure Thresholds
HIGH_PRESSURE_THRESHOLD = 0.50  →  0.35
MODERATE_PRESSURE_THRESHOLD = 0.30  →  0.15

# MMR Window Growth (per wave)
HIGH_PRESSURE_PARAMS = (75, 25)  →  (75, 20)
MODERATE_PRESSURE_PARAMS = (100, 35)  →  (100, 30)
LOW_PRESSURE_PARAMS = (125, 45)  →  (125, 40)

# NEW: Hard Caps
ABSOLUTE_MAX_MMR_DIFFERENCE = 400  # ADD THIS
QUEUE_TIMEOUT_SECONDS = 600  # ADD THIS (10 min)
```

---

## Launch Decision Framework

### ✅ LAUNCH (100+ concurrent players expected)

- **Expected experience**: Good
- **Match rate**: 0.3-0.5 matches/wave
- **Wait times**: 2-3 minutes average
- **Match quality**: 100-150 MMR difference
- **Action**: Full public launch with recommended parameter changes

### ⚠️ SOFT LAUNCH (50-100 concurrent players expected)

- **Expected experience**: Fair
- **Match rate**: 0.1-0.3 matches/wave
- **Wait times**: 3-5 minutes average
- **Match quality**: 150-250 MMR difference
- **Action**: Closed beta or scheduled events, implement all recommended changes

### ❌ DO NOT LAUNCH (<50 concurrent players expected)

- **Expected experience**: Poor
- **Match rate**: <0.1 matches/wave
- **Wait times**: 5-10+ minutes
- **Match quality**: 200-400+ MMR difference
- **Action**: Delay launch, build community to critical mass first

---

## Race Balance Impact (CRITICAL)

**Balanced Distribution (40% BW, 40% SC2, 20% Both)**
- ✅ 50% match rate
- ✅ 0 players left unmatched

**Imbalanced Distribution (60% BW, 20% SC2, 20% Both)**
- ❌ 20% match rate
- ❌ 60% of players left unmatched

**Action Required**: 
- Monitor race distribution in real-time
- Display queue composition to players
- Incentivize minority race selection
- Consider same-race fallback matching

---

## Post-Launch Monitoring (First 2 Weeks)

Track these metrics daily:

1. **Median queue size**: Target >5 players
2. **90th percentile wait time**: Target <5 minutes
3. **Matches with >400 MMR diff**: Target <10%
4. **Queue abandonment rate**: Target <20%
5. **Race distribution**: Alert if any race >60% or <15%
6. **Pressure activation**: Expect LOW 60%, MODERATE 30%, HIGH 10%

**Adjustment Triggers**:
- Avg wait >5 min → loosen MMR windows
- MMR diff >300 avg → tighten MMR windows
- Race imbalance >70/20 → implement incentives immediately
- Abandonment >30% → add transparency features

---

## Why Current Parameters Are Conservative

**The Problem**: Realistic queue loads (5-20%) rarely trigger MODERATE or HIGH pressure modes.

**Example**:
- 100 players online, 20 in queue (20% - high load)
- Pressure calculation: `(0.8 × 20) / 100 = 0.16`
- Result: **LOW pressure** (needs 0.30 for MODERATE)
- Effect: MMR window starts at 125 and grows by 45/wave
- After 10 waves: 575 MMR tolerance (way too wide!)

**The Fix**: Lower thresholds to 0.15 and 0.35 so realistic loads activate tighter windows.

---

## One-Sentence Verdict

> **"Solid algorithm with conservative tuning - ready to launch with 50+ players after adjusting pressure thresholds (0.15, 0.35) and adding 400 MMR hard cap."**

---

## Next Steps

### Immediate (Before Launch)

1. [ ] Update `config.py` with recommended parameters
2. [ ] Implement MMR hard cap in matching logic
3. [ ] Add queue timeout (10 minutes)
4. [ ] Create race balance display UI
5. [ ] Add match quality indicators
6. [ ] Set up telemetry for post-launch monitoring

### Launch Day

1. [ ] Verify 50+ concurrent player target
2. [ ] Monitor queue sizes hourly
3. [ ] Track race distribution
4. [ ] Watch for excessive wait times

### Week 1

1. [ ] Analyze pressure distribution (should see MODERATE/HIGH activate)
2. [ ] Check MMR difference distribution (<10% above 400)
3. [ ] Monitor abandonment rates
4. [ ] Survey player satisfaction

### Week 2+

1. [ ] Fine-tune parameters based on real data
2. [ ] Implement race incentives if needed
3. [ ] Consider same-race fallback if race imbalance persists
4. [ ] Plan for scheduled matchmaking windows if population is low

---

## Questions?

Refer to the [full analysis document](./MATCHMAKING_ALGORITHM_ANALYSIS.md) for:
- Detailed simulations and test data
- Edge case analysis
- Pressure sensitivity breakdown
- Player journey scenarios
- Algorithm strengths and weaknesses
- Complete parameter reference

---

**Document End**

