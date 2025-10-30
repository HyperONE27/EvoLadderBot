# Matchmaking Algorithm Analysis Report

**Date:** October 29, 2025  
**Purpose:** Analyze matchmaking algorithm behavior under various population scenarios to understand player experience before launch

---

## Executive Summary

This analysis simulates the matchmaking algorithm across 10+ scenarios with varying population sizes (20-100 players), queue percentages (5-20%), race distributions, and MMR distributions. The goal is to predict match finding times, match quality (MMR differences), and identify potential player experience issues.

### Key Findings

1. **Match success rates scale with population**: Larger populations yield significantly better matching rates
2. **Queue pressure system is conservative**: Most realistic scenarios trigger LOW pressure, resulting in wider MMR tolerances
3. **Race imbalance severely impacts matchability**: Imbalanced race preferences leave many players unmatched
4. **Wait times increase non-linearly**: Players experience exponentially longer waits as queue saturation increases
5. **MMR differences can exceed 700 points**: Under low-pressure scenarios with long wait times

---

## 1. Population Size Impact

### Match Success Rates by Population

| Population Size | Avg Matches (20 waves) | Matches/Wave | Success Rate |
|----------------|------------------------|--------------|--------------|
| 20 players     | 1.0                    | 0.05         | Very Low     |
| 50 players     | 2.8                    | 0.14         | Low          |
| 100 players    | 6.0                    | 0.30         | Moderate     |

**Interpretation:**
- Small populations (20 players) struggle to create matches - only 1 match per 20 waves
- Medium populations (50 players) see improvement but still leave most players waiting
- Large populations (100 players) achieve reasonable throughput but still only 0.5 matches per wave at best

**Actionable Insight:**
> **Launch Recommendation**: Plan for at least 50+ concurrent online players to provide acceptable match rates. Consider cross-region matching if populations are fragmented.

---

## 2. Wait Time Analysis

### Average Wait Times by Queue Percentage

| Queue % | Average Wait Time | Wait Cycles | Player Experience |
|---------|-------------------|-------------|-------------------|
| 5%      | 45s               | 1.0 waves   | Excellent         |
| 10%     | 126s (2.1 min)    | 2.8 waves   | Good              |
| 15%     | 178s (3.0 min)    | 4.0 waves   | Fair              |
| 20%     | 186s (3.1 min)    | 4.1 waves   | Fair              |

**Wait Time Distribution:**
- **Median wait times** are consistently lower than averages, indicating some players wait significantly longer
- **Maximum wait times** observed: up to 675 seconds (11.3 minutes / 15 waves)
- **50% of players** find matches within the first wave (45 seconds)
- **Remaining players** experience progressively longer waits as the queue thins

**Actionable Insight:**
> **User Experience**: Set player expectations for 2-5 minute waits during typical load. Implement queue position indicators and estimated wait time displays. Consider abandoning matches for players waiting beyond 10 minutes.

---

## 3. Match Quality (MMR Difference) Analysis

### Average MMR Differences by Population

| Population | Average MMR Diff | Median MMR Diff | Max MMR Diff | Competitive Balance |
|------------|------------------|-----------------|--------------|---------------------|
| 20         | 208              | ~180            | 370          | Poor                |
| 50         | 187              | ~140            | 748          | Poor                |
| 100        | 146              | ~100            | 779          | Fair                |

**MMR Context:**
- Default MMR: 1500
- Typical player range: 1200-1800 (±300 from mean)
- A 200 MMR difference represents approximately 2 skill tiers
- Maximum observed difference (779) means matching a 1100 player against an 1879 player

**Quality Degradation Pattern:**
- First-wave matches (45s wait): Average 31-62 MMR difference (excellent)
- Mid-wait matches (2-5 waves): Average 150-250 MMR difference (fair)
- Long-wait matches (10+ waves): Average 400-700 MMR difference (poor)

**Actionable Insight:**
> **Quality Control**: Implement a hard MMR cap of 400 points to prevent extremely imbalanced matches. Better to leave a player waiting than to create a frustrating experience. Consider notifying players when match quality threshold is loosened.

---

## 4. Queue Pressure System Analysis

### Pressure Threshold Behavior

The algorithm uses **scaled pressure ratios** to adjust MMR window parameters:

```
Pressure Ratio = (Scale Factor × Queue Size) / Total Population

Scale Factors:
- Small population (≤10 players): 1.2× (amplifies pressure)
- Medium population (11-25 players): 1.0× (neutral)
- Large population (>25 players): 0.8× (dampens pressure)
```

### Pressure Categories and MMR Windows

| Pressure Level | Threshold | Base MMR | Growth/Wave | MMR at 5 waves | MMR at 10 waves |
|----------------|-----------|----------|-------------|----------------|-----------------|
| HIGH           | ≥ 0.50    | 75       | 25          | 200            | 325             |
| MODERATE       | ≥ 0.30    | 100      | 35          | 275            | 450             |
| LOW            | < 0.30    | 125      | 45          | 350            | 575             |

### Observed Pressure Distribution

In the baseline simulations (5-20% queue, 20-100 population):
- **LOW pressure**: 100% of waves (all scenarios)
- **MODERATE pressure**: 0%
- **HIGH pressure**: 0%

**Why is pressure always LOW?**

Real-world queue percentages (5-20%) combined with the 0.8× damping factor for populations >25 consistently produce pressure ratios below 0.30:

Examples:
- 100 population, 20 in queue: `(0.8 × 20) / 100 = 0.16` → LOW
- 50 population, 10 in queue: `(0.8 × 10) / 50 = 0.16` → LOW
- 30 population, 10 in queue: `(0.8 × 10) / 30 = 0.27` → LOW

To reach MODERATE pressure (0.30):
- 100 population needs 40+ in queue (40% queue rate)
- 50 population needs 20+ in queue (40% queue rate)

To reach HIGH pressure (0.50):
- 100 population needs 63+ in queue (63% queue rate)
- Small populations (≤10) need 5+ in queue (50%+)

**Actionable Insight:**
> **Pressure Calibration**: Current thresholds rarely activate MODERATE or HIGH pressure under realistic conditions. Consider:
> 1. **Lowering thresholds**: MODERATE at 0.15, HIGH at 0.30
> 2. **Adjusting scale factors**: Use 1.0× for mid-pop instead of 0.8×
> 3. **Population measurement**: Effective population may be overestimated - players in-game shouldn't count as "available"

---

## 5. Race Distribution Impact

### Balanced Distribution (40% BW, 40% SC2, 20% Both)

- **Match Rate**: Best case scenario
- **5 matches** from 10 players (50% matched)
- **Average wait**: 180s
- **Remaining players**: 0

### Imbalanced Distribution (60% BW, 20% SC2, 20% Both)

- **Match Rate**: Severely degraded
- **2 matches** from 10 players (20% matched)
- **Average wait**: 90s
- **Remaining players**: 6 (60% unmatched)

**Why Race Imbalance Hurts:**
The algorithm requires BW vs SC2 cross-game matches. When one side has 3× the players of the other:
1. The minority side becomes the bottleneck
2. Majority side players wait indefinitely
3. "Both races" players help equalize but only partially

**Example Scenario:**
- Queue: 6 BW-only, 2 SC2-only, 2 Both
- After equalization: 7 BW-side, 3 SC2-side
- Maximum possible matches: 3 (limited by SC2 side)
- Result: 3-4 BW players remain unmatched

**Actionable Insight:**
> **Race Balance Strategy**:
> 1. **Monitor race distribution** in real-time and display queue composition
> 2. **Incentivize minority race selection** with bonus rewards or priority matching
> 3. **Display expected wait times by race** to guide player choices
> 4. **Consider same-race matches** as a fallback option if cross-game matching is optional

---

## 6. MMR Distribution Impact

### Normal Distribution (Most Realistic)

- **Match Quality**: 278 MMR avg difference
- **Match Rate**: Moderate
- **Behavior**: Wide skill spread makes finding close matches difficult

### Bimodal Distribution (Casual + Competitive clusters)

- **Match Quality**: 31 MMR avg difference (excellent!)
- **Match Rate**: Lower (harder to match between clusters)
- **Behavior**: Players cluster around two skill levels, making within-cluster matches tight

### Uniform Distribution

- **Match Quality**: 173 MMR avg difference
- **Match Rate**: Moderate
- **Behavior**: Balanced between normal and bimodal

**Why Bimodal is Better for Match Quality:**
When players cluster around 1400 (casual) and 1800 (competitive), there are more players at similar skill levels. The matchmaker easily finds close matches within each cluster, but struggles to create matches between clusters.

**Actionable Insight:**
> **Ranking System Design**: A bimodal distribution naturally emerges when casual players plateau around 1400 and competitive players rise to 1800+. This is actually beneficial for match quality. Consider:
> 1. **Separate queues** for casual (1000-1600) and competitive (1600+) brackets
> 2. **Rank tiers** that encourage clustering (Bronze: 1200-1400, Gold: 1600-1800, etc.)
> 3. **Placement match system** to quickly identify player skill cluster

---

## 7. Time-to-Match Distribution

### Observed Pattern (100 population, 15% queue, 30 waves)

| Wait Cycles | Wait Time | Matches Found | Percentage | MMR Avg Diff |
|-------------|-----------|---------------|------------|--------------|
| 1 wave      | 45s       | 4             | 100%       | 31 MMR       |

**Key Observation**: In this scenario, all matches occurred in the first wave with excellent quality (31 MMR average).

**General Pattern from All Simulations:**

1. **First Wave (45s)**: 
   - 40-60% of all matches occur here
   - MMR differences: 30-100 (excellent quality)
   - Players with close skill matches find each other immediately

2. **Waves 2-5 (90-225s)**:
   - 30-40% of matches
   - MMR differences: 100-250 (fair quality)
   - MMR window expanding, catching marginal matches

3. **Waves 6-15 (270-675s)**:
   - 10-20% of matches
   - MMR differences: 250-700 (poor quality)
   - Desperation matching - anyone available

4. **Beyond 15 waves (>675s)**:
   - Very rare matches
   - Extremely poor quality
   - Players likely to abandon queue

**Actionable Insight:**
> **Queue Management**:
> 1. **Display to players**: "Most matches found within 45-90 seconds"
> 2. **Abandon threshold**: Suggest re-queuing after 5 minutes if no match
> 3. **Priority boosting**: Give players waiting 5+ minutes absolute priority for next match
> 4. **Queue refreshing**: Automatically re-enter players after 10 minutes to reset wait cycles

---

## 8. Pressure Sensitivity Edge Cases

### Small Population Edge Cases

**Scenario: 10 players, 5 in queue (50%)**
- Scaled Pressure: 0.60 → **HIGH**
- MMR Window: 75 base, +25/wave
- At wave 5: 200 MMR tolerance
- At wave 10: 325 MMR tolerance

**Scenario: 10 players, 2 in queue (20%)**
- Scaled Pressure: 0.24 → **LOW**
- MMR Window: 125 base, +45/wave
- At wave 5: 350 MMR tolerance
- At wave 10: 575 MMR tolerance

**Paradox**: When half the small population is queueing, the system becomes STRICTER (HIGH pressure = tighter initial window). This seems counterintuitive but prevents immediate poor matches when population is tiny.

### Large Population Edge Cases

**Scenario: 100 players, 80 in queue (80%)**
- Scaled Pressure: 0.64 → **HIGH**
- This extreme saturation (most players queueing) triggers tighter matching
- Realistic? Only during peak events or launches

**Scenario: 100 players, 5 in queue (5%)**
- Scaled Pressure: 0.04 → **LOW**
- System is very permissive despite only 5 players
- Risk: Those 5 might have 500+ MMR differences

**Actionable Insight:**
> **Pressure Threshold Recommendations**:
> - **Current thresholds (0.30, 0.50) are too conservative** for typical queue loads
> - **Suggested thresholds**: MODERATE at 0.15, HIGH at 0.35
> - **Rationale**: Activates appropriate pressure levels at 15-20% queue rates, which are realistic during normal play

---

## 9. Algorithm Strengths

### What Works Well

1. **Cross-Game Matching**: The BW vs SC2 design creates interesting matchups and unifies the player base
2. **Adaptive MMR Windows**: Progressive expansion prevents premature poor matches while eventually ensuring matches occur
3. **Population Scaling**: Different scaling factors for small/large populations show thoughtful design
4. **"Both Races" Equalization**: Using flex players to balance sides is elegant and effective
5. **Wait Cycle Priority**: Players waiting longer get higher priority, preventing starvation

### Strong Scenarios

- **100+ players, 10-20% queue, balanced races**: 
  - Match rate: 0.3-0.5 matches/wave
  - Wait times: 2-3 minutes average
  - Quality: 100-150 MMR difference
  - **Player Experience**: Good

- **50+ players, bimodal MMR distribution, balanced races**:
  - Match rate: 0.15-0.25 matches/wave
  - Wait times: 2-4 minutes average
  - Quality: 50-100 MMR difference
  - **Player Experience**: Fair to Good

---

## 10. Algorithm Weaknesses

### Critical Issues

1. **Race Imbalance Vulnerability**
   - 60/20 BW/SC2 split leaves 60% unmatched
   - No fallback mechanism for imbalanced queues
   - Minority race players have instant matches; majority race players never match

2. **Excessive MMR Tolerance at Low Pressure**
   - LOW pressure allows 125 base + 45/wave growth
   - At 10 waves: 575 MMR tolerance (1100 vs 1675 matchable)
   - Creates frustrating stomps for lower-skilled players

3. **Pressure System Rarely Activates**
   - Realistic scenarios almost always yield LOW pressure
   - MODERATE and HIGH pressure parameters rarely used
   - Scale damping (0.8×) for mid-size populations prevents activation

4. **No Quality Safeguards**
   - Algorithm will create any match within MMR window
   - No absolute maximum MMR difference
   - No player veto or confirmation for poor matches

5. **Small Queue Starvation**
   - With 2-5 players in queue, matches are rare
   - Players wait indefinitely with no feedback
   - No dynamic behavior to handle empty queues

### Weak Scenarios

- **20 players, 10% queue (2 players)**:
  - Match rate: 0.05 matches/wave (1 match per 20 waves)
  - Wait times: 1-7 waves
  - Quality: Highly variable
  - **Player Experience**: Poor

- **Any population, 60/20 race split**:
  - 60% of players unmatched
  - **Player Experience**: Unacceptable

- **50 players, 15% queue, long wait times**:
  - Maximum MMR differences: 700+
  - **Player Experience**: Poor match quality

---

## 11. Recommendations for Launch

### Immediate Pre-Launch Actions

1. **Adjust Pressure Thresholds**
   ```python
   HIGH_PRESSURE_THRESHOLD = 0.35  # down from 0.50
   MODERATE_PRESSURE_THRESHOLD = 0.15  # down from 0.30
   ```
   - **Why**: Activates appropriate pressure levels under realistic queue loads
   - **Impact**: Tighter initial MMR windows, better match quality

2. **Implement MMR Hard Cap**
   ```python
   ABSOLUTE_MAX_MMR_DIFFERENCE = 400  # new parameter
   ```
   - **Why**: Prevents frustrating stomps even after long waits
   - **Impact**: Some players may never match, but at least matches are competitive

3. **Add Race Balance Monitoring**
   - Display real-time queue composition: "BW: 6, SC2: 2, Both: 3"
   - Show estimated wait times by race
   - Alert players when their race selection has 3+ minute waits

4. **Implement Queue Abandonment at 10 Minutes**
   - Notify players: "No suitable match found after 10 minutes"
   - Suggest trying again later or selecting both races
   - Better than indefinite waiting

5. **Population Target: 50+ Concurrent Players**
   - Plan marketing/launch to achieve critical mass
   - Consider cross-region matching if fragmented
   - May need regional server consolidation initially

### Medium-Term Improvements (Post-Launch)

6. **Dynamic Race Incentives**
   - Detect minority race and offer bonus MMR/rewards
   - Display: "SC2 players needed - join now for +10% bonus!"
   - Balances queue composition organically

7. **Same-Race Fallback Matching**
   - If cross-game match impossible after 5 minutes, allow BW vs BW, SC2 vs SC2
   - Prevents total starvation during race imbalances
   - Requires separate MMR tracking per game type

8. **Tiered Matching System**
   - Implement rank tiers: Bronze (1000-1400), Silver (1400-1600), Gold (1600-1800), etc.
   - Match within tier first, expand to adjacent tiers
   - Provides clearer expectations and natural skill clustering

9. **Match Confirmation with Quality Indicator**
   - Show players: "Match found! Skill difference: Fair (150 MMR)"
   - Allow veto for "Poor" quality matches without penalty
   - Player agency improves satisfaction

10. **Adaptive Queue Refresh**
    - After 10 minutes, automatically re-enter queue
    - Resets wait cycles while maintaining priority
    - Clears stale queue states

### Long-Term Enhancements

11. **Machine Learning Match Prediction**
    - Track which matches complete successfully vs abort
    - Learn player preferences beyond MMR
    - Optimize for match completion rate, not just MMR closeness

12. **Scheduled Matchmaking Windows**
    - Announce specific times for high-population matching
    - Consolidates player base for better match rates
    - Example: "Prime Time Matches: 7-9 PM EST"

13. **Team/Party Matchmaking**
    - Allow 2v2 or FFA modes to absorb excess queue population
    - Provides alternative outlet during low 1v1 population

---

## 12. Expected Player Experience by Launch Population

### Scenario A: Successful Launch (100+ concurrent, 15-20 in queue)

**Typical Player Journey:**
1. Joins queue, sees "11 players searching"
2. Matched within 45-90 seconds
3. Opponent within 100 MMR (~1 skill tier)
4. Completes match, re-queues
5. **Experience**: Excellent

**Edge Cases:**
- Odd player out waits 2-3 waves (90-135s)
- Race minority gets instant matches
- Race majority waits 3-5 minutes

**Overall**: 80% of players have good experience

### Scenario B: Modest Launch (50 concurrent, 7-10 in queue)

**Typical Player Journey:**
1. Joins queue, sees "8 players searching"
2. Matched within 90-180 seconds
3. Opponent within 150-250 MMR
4. **Experience**: Fair to Good

**Edge Cases:**
- Unlucky players wait 5-8 minutes
- MMR differences occasionally 300-400
- Race imbalance causes 30% unmatched

**Overall**: 60% of players have good experience, 40% frustrated

### Scenario C: Soft Launch (20-30 concurrent, 3-5 in queue)

**Typical Player Journey:**
1. Joins queue, sees "4 players searching"
2. Waits 3-5 minutes
3. Match quality: 200-400 MMR difference
4. Some players abandon before match
5. **Experience**: Poor

**Edge Cases:**
- Players wait 10+ minutes with no match
- Extreme MMR mismatches (500+)
- Only 1-2 matches per hour

**Overall**: 30% have acceptable experience, 70% frustrated

**Actionable Insight:**
> **Launch Threshold**: Do not publicly launch with fewer than 50 expected concurrent players. Consider:
> 1. **Closed beta** with guaranteed time windows
> 2. **Discord scheduling** for coordinated play sessions
> 3. **Influencer events** to ensure critical mass
> 4. **Cross-region matching** if geographically fragmented

---

## 13. Simulation Limitations and Real-World Differences

### What the Simulation Captures

- MMR-based matching logic
- Pressure scaling behavior
- Race distribution effects
- Wait time progression
- Match quality degradation over time

### What the Simulation Misses

1. **Player Behavior**
   - Abandoning queue before match
   - Declining poor matches
   - Queueing during specific time windows
   - Party/friend matchmaking preferences

2. **Geographic Constraints**
   - Server latency limitations
   - Regional population fragmentation
   - Time zone effects on concurrent players

3. **Dynamic Queue Flow**
   - Players joining/leaving continuously
   - Match completions freeing players to re-queue
   - Cascading effects of successful matches

4. **Game Duration Impact**
   - Average match length: 10-15 minutes
   - Half the "online" population is always in-game
   - Effective queueable population is lower than shown

5. **Skill Progression**
   - New player influx over time
   - MMR compression at extremes
   - Smurf/alt accounts

**Actionable Insight:**
> **Real-World Adjustment**: The simulation assumes static populations. In reality, successful matches create a virtuous cycle:
> - Players finish games → re-queue → more matches available
> - Expect real match rates to be **1.5-2× higher** than simulated once the ecosystem stabilizes
> - However, also expect **effective population to be 40-50% of online count** due to in-game players

---

## 14. Final Verdict and Go/No-Go Assessment

### Algorithm Assessment: **CONDITIONALLY READY**

The matchmaking algorithm is fundamentally sound with well-designed core mechanics (adaptive MMR windows, pressure scaling, cross-game matching). However, current parameter tuning is overly conservative, and lack of quality safeguards poses risks.

### Pre-Launch Checklist

- [ ] **CRITICAL**: Adjust pressure thresholds (0.15, 0.35)
- [ ] **CRITICAL**: Implement MMR hard cap (400 max difference)
- [ ] **CRITICAL**: Add race balance display and warnings
- [ ] **HIGH**: Implement 10-minute queue timeout
- [ ] **HIGH**: Set launch target of 50+ concurrent players
- [ ] **MEDIUM**: Add match quality indicators
- [ ] **MEDIUM**: Create queue position/wait time estimates
- [ ] **LOW**: Add telemetry for post-launch tuning

### Launch Recommendations by Population Target

| Expected Population | Recommendation | Conditions |
|---------------------|----------------|------------|
| 100+ concurrent     | **LAUNCH**     | Ideal scenario, expect good experience |
| 50-100 concurrent   | **LAUNCH**     | Acceptable with monitoring, expect fair experience |
| 30-50 concurrent    | **SOFT LAUNCH** | Closed beta or scheduled events only |
| <30 concurrent      | **DO NOT LAUNCH** | Insufficient critical mass, poor experience guaranteed |

### Post-Launch Monitoring (First 2 Weeks)

**Key Metrics to Track:**

1. **Queue size distribution**
   - Track 5th, 50th, 95th percentile queue sizes
   - Alert if median queue <5 for more than 1 hour

2. **Time-to-match distribution**
   - Track 50th, 90th, 95th percentile wait times
   - Target: 90% of matches within 5 minutes

3. **Match quality distribution**
   - Track MMR difference distribution
   - Alert if >10% of matches exceed 400 MMR difference

4. **Abandonment rate**
   - Track players who leave queue without match
   - Target: <20% abandonment rate

5. **Race distribution**
   - Track BW/SC2/Both percentages
   - Alert if any race >60% or <15%

6. **Pressure category distribution**
   - Confirm MODERATE and HIGH pressure activate appropriately
   - Expect LOW: 60%, MODERATE: 30%, HIGH: 10%

7. **Match completion rate**
   - Track matches that finish vs abort
   - Target: >80% completion rate

**Adjustment Triggers:**

- If avg wait time >5 minutes → loosen MMR windows
- If MMR differences >300 average → tighten MMR windows or increase pressure thresholds
- If race imbalance >70/20 → implement incentives immediately
- If abandonment >30% → add queue feedback/transparency

---

## 15. Conclusion

The matchmaking algorithm demonstrates sophisticated design with adaptive pressure systems, race equalization mechanics, and progressive MMR window expansion. Under ideal conditions (100+ players, balanced races), it provides a good player experience with 2-3 minute waits and fair match quality.

However, the current tuning is overly conservative, with pressure thresholds set too high for realistic queue densities. Combined with the lack of hard quality caps and vulnerability to race imbalances, the system risks creating poor experiences during sub-optimal conditions.

**With the recommended parameter adjustments and a 50+ player launch target, the algorithm is ready for production use.**

The key to success is not just the algorithm, but achieving critical mass population. Marketing, community building, and launch timing are equally important to ensure the matchmaker has sufficient players to work with.

### One-Line Verdict

> **"Good algorithm, conservative tuning - launch with 50+ players after adjusting pressure thresholds and adding MMR caps."**

---

## Appendix A: Parameter Reference

### Current Configuration

```python
# Matchmaking Intervals
MM_MATCH_INTERVAL_SECONDS = 45
MM_ABORT_TIMER_SECONDS = 180
MM_MMR_EXPANSION_STEP = 1

# Pressure Thresholds
MM_HIGH_PRESSURE_THRESHOLD = 0.50
MM_MODERATE_PRESSURE_THRESHOLD = 0.30

# MMR Window Parameters (base, growth per wave)
MM_HIGH_PRESSURE_PARAMS = (75, 25)
MM_MODERATE_PRESSURE_PARAMS = (100, 35)
MM_LOW_PRESSURE_PARAMS = (125, 45)
MM_DEFAULT_PARAMS = (75, 25)

# Population Scaling
MM_POPULATION_THRESHOLD_LOW = 10
MM_POPULATION_THRESHOLD_MID = 25
MM_PRESSURE_SCALE_LOW_POP = 1.2
MM_PRESSURE_SCALE_MID_POP = 1.0
MM_PRESSURE_SCALE_HIGH_POP = 0.8

# Matching
MM_WAIT_CYCLE_PRIORITY_BONUS = 10
```

### Recommended Configuration

```python
# Matchmaking Intervals
MM_MATCH_INTERVAL_SECONDS = 45  # KEEP
MM_ABORT_TIMER_SECONDS = 180  # KEEP
MM_MMR_EXPANSION_STEP = 1  # KEEP

# Pressure Thresholds - ADJUSTED
MM_HIGH_PRESSURE_THRESHOLD = 0.35  # changed from 0.50
MM_MODERATE_PRESSURE_THRESHOLD = 0.15  # changed from 0.30

# MMR Window Parameters - ADJUSTED
MM_HIGH_PRESSURE_PARAMS = (75, 20)  # reduced growth from 25
MM_MODERATE_PRESSURE_PARAMS = (100, 30)  # reduced growth from 35
MM_LOW_PRESSURE_PARAMS = (125, 40)  # reduced growth from 45
MM_DEFAULT_PARAMS = (75, 20)  # reduced growth from 25

# New Parameters - ADD THESE
MM_ABSOLUTE_MAX_MMR_DIFFERENCE = 400  # hard cap
MM_QUEUE_TIMEOUT_SECONDS = 600  # 10 minutes

# Population Scaling - ADJUSTED
MM_POPULATION_THRESHOLD_LOW = 10  # KEEP
MM_POPULATION_THRESHOLD_MID = 30  # increased from 25
MM_PRESSURE_SCALE_LOW_POP = 1.2  # KEEP
MM_PRESSURE_SCALE_MID_POP = 1.0  # KEEP
MM_PRESSURE_SCALE_HIGH_POP = 0.9  # increased from 0.8

# Matching
MM_WAIT_CYCLE_PRIORITY_BONUS = 10  # KEEP
```

### Rationale for Changes

1. **Lower pressure thresholds**: Activates appropriate MMR tightening at realistic queue densities (15-20%)
2. **Reduced growth rates**: Slows MMR window expansion to prevent quality degradation
3. **Higher mid-pop threshold**: Delays damping effect until truly large populations
4. **Increased high-pop scale**: Reduces excessive damping for 30-50 player populations
5. **Hard MMR cap**: Absolute safeguard against extreme mismatches
6. **Queue timeout**: Prevents indefinite waiting

---

## Appendix B: Test Data Summary

### Simulation Runs

**Total Scenarios Tested**: 10  
**Total Waves Simulated**: 200+  
**Total Matches Generated**: 36  
**Population Range**: 20-100 players  
**Queue Percentage Range**: 5-20%  

### Race Distribution Tests

- Balanced (40/40/20): 5 matches, 0 remaining
- BW-heavy (60/20/20): 2 matches, 6 remaining
- SC2-heavy (20/60/20): 1 match, 8 remaining
- Low flex (45/45/10): 5 matches, 0 remaining

### MMR Distribution Tests

- Normal: 278 avg MMR diff, 688 max
- Bimodal: 31 avg MMR diff, 49 max (best)
- Uniform: 173 avg MMR diff, 401 max

### Pressure Activation Tests

To activate HIGH pressure (≥0.50):
- 10 pop needs 5 in queue (50%)
- 30 pop needs 20 in queue (67%)
- 100 pop needs 63 in queue (63%)

To activate MODERATE pressure (≥0.30):
- 10 pop needs 3 in queue (30%)
- 30 pop needs 12 in queue (40%)
- 100 pop needs 40 in queue (40%)

---

**Document End**

