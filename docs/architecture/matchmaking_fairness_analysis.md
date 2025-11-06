# Matchmaking Fairness Analysis: Balanced vs Aggressive

## Executive Summary

We tested **Aggressive Fairness** configuration against the **Balanced** configuration to understand the trade-offs between match quality and ensuring everyone gets matched.

**Key Finding**: For your expected launch scenario (20-30 players in queue), **Balanced configuration is recommended**. Aggressive Fairness only provides meaningful benefits in edge cases.

---

## Configuration Comparison

### Balanced (Recommended for Launch)
```
Pressure Thresholds: 10% (MODERATE), 20% (HIGH)
MMR Windows: 
  - HIGH: base=75, growth=25
  - MODERATE: base=100, growth=35
  - LOW: base=125, growth=45
Wait Priority: coefficient=20, exponent=1.25
Skill Balance: 50 MMR threshold
```

### Aggressive Fairness (Edge Case Optimization)
```
Pressure Thresholds: 5% (MODERATE), 12% (HIGH)
MMR Windows:
  - HIGH: base=75, growth=25 (same)
  - MODERATE: base=120, growth=50 (+20 base, +15 growth)
  - LOW: base=160, growth=70 (+35 base, +25 growth)
Wait Priority: coefficient=60, exponent=1.5 (3-6x higher!)
Skill Balance: 75 MMR threshold (more relaxed)
```

---

## Performance Comparison

### Typical Scenarios (10-30 players in queue)

| Scenario | Config | Avg MMR Diff | Matches/Wave | Time |
|----------|--------|--------------|--------------|------|
| **10 players, 20 active** | Balanced | 57.8 | 2.84 | 0.006ms |
| | Aggressive | 57.9 | 2.84 | 0.005ms |
| **20 players, 30 active** | Balanced | 46.2 | 6.94 | 0.017ms |
| | Aggressive | 46.2 | 6.92 | 0.016ms |
| **30 players, 50 active** | Balanced | 40.9 | 11.19 | 0.039ms |
| | Aggressive | 40.4 | 11.13 | 0.037ms |

**Conclusion**: In typical scenarios, the difference is **negligible** (< 1% in all metrics).

---

## When Aggressive Fairness Matters

### 1. Pressure Threshold Differences

Aggressive triggers more aggressive MMR modes sooner:

| Queue Size | Active Pop | Balanced Mode | Aggressive Mode |
|------------|-----------|---------------|-----------------|
| 2 | 30 | LOW | **MODERATE** ⚡ |
| 3 | 30 | LOW | **MODERATE** ⚡ |
| 5 | 30 | MODERATE | **HIGH** ⚡ |
| 10 | 50 | MODERATE | **HIGH** ⚡ |

This means tighter initial windows, but faster expansion.

### 2. MMR Window Expansion (Long-Waiting Players)

For a player who has waited **10 waves** (7.5 minutes at 45s/wave):

| Pressure | Balanced Window | Aggressive Window | Difference |
|----------|-----------------|-------------------|------------|
| **LOW** | 575 MMR | **860 MMR** | **+49%** wider ⚡ |
| **MODERATE** | 450 MMR | **620 MMR** | **+38%** wider ⚡ |
| **HIGH** | 325 MMR | 325 MMR | Same |

**Impact**: Long-waiting players have **dramatically wider** matching windows in Aggressive mode, making matches much more likely.

### 3. Wait Time Priority

Priority bonus for long-waiting players:

| Wait Cycles | Balanced | Aggressive | Ratio |
|-------------|----------|------------|-------|
| 1 wave | 20 | 60 | 3.0x |
| 5 waves | 150 | 671 | **4.5x** |
| 10 waves | 356 | 1,897 | **5.3x** |
| 15 waves | 590 | 3,486 | **5.9x** |

**Impact**: In Aggressive mode, a player who waited 10 waves gets **5.3x higher priority** than in Balanced mode. This essentially guarantees they match first.

### 4. Example: Match Probability Increase

Player with 1500 MMR, 10 potential matches with MMR spread 1400-1700:

| Wait Cycles | Balanced Matches | Aggressive Matches | Improvement |
|-------------|------------------|--------------------| ------------|
| 0 | 8/10 (80%) | 8/10 (80%) | None |
| 1 | 8/10 (80%) | **9/10 (90%)** | +1 match |
| 2 | 9/10 (90%) | **10/10 (100%)** | +1 match |
| 3+ | 10/10 (100%) | 10/10 (100%) | Same |

**Impact**: After 2 waves, Aggressive guarantees 100% match probability vs 90% in Balanced.

---

## Real-World Impact

### Scenario: 25 Players Online, 5 in Queue (20% queue rate)

**Balanced Mode**:
- Pressure: 0.20 (exactly at HIGH threshold)
- MMR Window wave 0: 75 MMR
- MMR Window wave 5: 200 MMR
- Long-waiter priority (5 cycles): 150 bonus

**Aggressive Mode**:
- Pressure: 0.20 (well above HIGH threshold of 0.12)
- MMR Window wave 0: 75 MMR (same)
- MMR Window wave 5: 200 MMR (same)
- Long-waiter priority (5 cycles): 671 bonus (**4.5x higher!**)

**Difference**: In this scenario, the only significant difference is that long-waiters get much higher priority in Aggressive mode. Windows are the same because both are in HIGH pressure.

### Scenario: 30 Players Online, 2 in Queue (6.7% queue rate)

**Balanced Mode**:
- Pressure: 0.053 (LOW mode)
- MMR Window wave 0: 125 MMR
- MMR Window wave 5: 350 MMR
- MMR Window wave 10: 575 MMR

**Aggressive Mode**:
- Pressure: 0.053 (MODERATE mode - lower threshold!)
- MMR Window wave 0: 120 MMR (tighter initially)
- MMR Window wave 5: 370 MMR (+20 MMR)
- MMR Window wave 10: 620 MMR (+45 MMR, **+8% wider**)

**Difference**: Aggressive starts with a tighter window but expands faster, overtaking Balanced by wave 3.

---

## Recommendations

### Use **Balanced** Configuration If:
✅ You expect 20-30 players in queue regularly  
✅ Most players match within 3-5 waves  
✅ Match quality is important to your community  
✅ You want predictable, fair matching

**This is recommended for your launch scenario.**

### Use **Aggressive Fairness** Configuration If:
⚡ Queue regularly drops below 10 players  
⚡ Players consistently wait 5+ waves (4+ minutes)  
⚡ Community strongly prioritizes "everyone plays" over match quality  
⚡ You have high MMR variance (many beginners + many pros)  
⚡ You're in a low-population period and need to maximize matches

### Switch from Balanced to Aggressive When:
📊 Monitoring shows:
- Average wait time > 5 waves (4 minutes)
- > 20% of players fail to match within 10 waves
- Queue size frequently < 10 players
- Community complaints about "not getting matches"

### Warning Signs You Need Aggressive:
⚠️ Players complaining about long wait times  
⚠️ Queue regularly has < 5 players  
⚠️ High MMR outliers (2000+ or 1000- MMR) never match  
⚠️ Off-peak hours have < 10 active players

---

## Implementation

Current implementation has **Aggressive Fairness** active. To switch:

### Revert to Balanced (Recommended for Launch):
```python
# src/backend/core/config.py
MM_HIGH_PRESSURE_THRESHOLD = 0.20  # Was 0.12
MM_MODERATE_PRESSURE_THRESHOLD = 0.10  # Was 0.05
MM_MODERATE_PRESSURE_PARAMS = (100, 35)  # Was (120, 50)
MM_LOW_PRESSURE_PARAMS = (125, 45)  # Was (160, 70)
MM_WAIT_CYCLE_PRIORITY_COEFFICIENT = 20  # Was 60
MM_WAIT_CYCLE_PRIORITY_EXPONENT = 1.25  # Was 1.5
MM_BALANCE_THRESHOLD_MMR = 50  # Was 75
```

### Keep Aggressive (For Edge Cases):
```python
# Current values - already set
# No changes needed
```

---

## Monitoring Metrics

Track these metrics to decide if you need to switch:

1. **Average Wait Time**: Should be < 3 waves (2.25 minutes)
2. **Match Success Rate**: % of players who match within 10 waves
3. **Queue Size Distribution**: % of waves with < 10 players
4. **MMR Diff Distribution**: Average, median, 90th percentile
5. **Long-Waiter Count**: How many players wait > 5 waves

**Decision Rule**: If > 30% of players wait more than 5 waves OR queue size is < 10 in > 40% of waves, consider switching to Aggressive.

---

## Conclusion

For your expected launch scenario (20-30 players in queue):
- **Balanced** provides excellent match quality with minimal wait times
- **Aggressive** provides only marginal benefits (< 1% difference)
- **Aggressive** should be reserved for low-population periods

**Recommendation**: Start with **Balanced**, monitor metrics, switch to **Aggressive** only if needed.

