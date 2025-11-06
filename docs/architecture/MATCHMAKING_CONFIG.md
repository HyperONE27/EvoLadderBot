# Matchmaking Configuration Summary

**Active Configuration**: **Balanced** (Recommended for Launch)

Last Updated: 2024 (Optimization v2.0)

---

## Current Parameters

### Pressure Thresholds
```python
MM_HIGH_PRESSURE_THRESHOLD = 0.20      # 20% queue/active ratio
MM_MODERATE_PRESSURE_THRESHOLD = 0.10  # 10% queue/active ratio
```

**What this means**: 
- Queue pressure triggers based on how many players are queued vs active
- 20% queue = HIGH pressure (tightest windows)
- 10% queue = MODERATE pressure (balanced windows)
- < 10% queue = LOW pressure (wider windows)

### MMR Windows (Base + Growth per Wave)

| Pressure Level | Base MMR | Growth/Wave | Wave 5 | Wave 10 |
|----------------|----------|-------------|---------|---------|
| **HIGH** | 75 | 25 | 200 | 325 |
| **MODERATE** | 100 | 35 | 275 | 450 |
| **LOW** | 125 | 45 | 350 | 575 |

**What this means**:
- Players waiting 0 waves in LOW pressure: ±125 MMR window
- Players waiting 5 waves in LOW pressure: ±350 MMR window
- Players waiting 10 waves in LOW pressure: ±575 MMR window

### Wait Time Priority
```python
MM_WAIT_CYCLE_PRIORITY_COEFFICIENT = 20  # Alpha
MM_WAIT_CYCLE_PRIORITY_EXPONENT = 1.25   # Beta
```

**Priority Formula**: `20 × (wait_cycles)^1.25`

| Wait Cycles | Priority Bonus | Meaning |
|-------------|----------------|---------|
| 0 | 0 | No bonus |
| 1 | 20 | Small boost |
| 5 | 149 | Moderate boost |
| 10 | 356 | Significant boost |
| 15 | 590 | High priority |

### Skill Balance
```python
MM_BALANCE_THRESHOLD_MMR = 50
```

When assigning "both" players (players who selected both BW and SC2), the system tries to keep the average MMR of BW and SC2 sides within 50 MMR of each other.

### Refinement
```python
MM_REFINEMENT_PASSES = 2
```

After initial matching, performs 2 passes of adjacent match swaps to minimize squared MMR differences.

---

## Expected Performance (20-30 Players)

Based on 200-trial simulations:

| Scenario | Avg MMR Diff | Median MMR Diff | Matches/Wave | Processing Time |
|----------|--------------|-----------------|--------------|-----------------|
| 10 players, 30 active | 62.4 | 49.0 | 2.83 | 0.005ms |
| 15 players, 30 active | 51.7 | 32.0 | 4.71 | 0.012ms |
| 20 players, 30 active | 47.9 | 30.0 | 7.09 | 0.019ms |
| 30 players, 50 active | 40.1 | 22.0 | 11.24 | 0.038ms |

**Key Metrics**:
- ✅ Avg MMR difference: 40-50 (competitive)
- ✅ Median MMR difference: 22-30 (very competitive)
- ✅ Match rate: 85-95% of players match per wave
- ✅ Processing time: < 0.1ms (negligible)

---

## Comparison to Other Configurations

### vs Aggressive Fairness
| Metric | Balanced | Aggressive | Difference |
|--------|----------|------------|------------|
| Avg MMR Diff | 40.1 | 39.7 | -1% (negligible) |
| Matches/Wave | 11.24 | 11.16 | -1% (negligible) |
| Wave 10 Window (LOW) | 575 | **860** | +49% wider |

**Verdict**: Aggressive only helps in edge cases (< 10 players, 5+ wave waits)

### vs Strict Quality
| Metric | Balanced | Strict | Difference |
|--------|----------|--------|------------|
| Avg MMR Diff | 40.1 | **33.2** | **-17% tighter!** ✅ |
| Matches/Wave | 11.24 | 10.43 | -7% fewer |
| Wave 10 Window (LOW) | 575 | **400** | 30% tighter |

**Verdict**: Strict provides better quality but 7-10% fewer matches

---

## When to Switch Configurations

### Switch to Aggressive Fairness If:
- ⚠️ Queue regularly drops below 10 players
- ⚠️ Average wait time exceeds 5 waves (4 minutes)
- ⚠️ > 20% of players fail to match within 10 waves
- ⚠️ Community complains "can't find matches"

### Switch to Strict Quality If:
- ⚠️ Queue regularly has 30+ players
- ⚠️ Community complains "matches are unfair"
- ⚠️ Average MMR diff exceeds 60
- ⚠️ Community prioritizes competitive quality

---

## Monitoring Metrics

Track these to decide if configuration needs adjustment:

### Primary Metrics
1. **Average Wait Time**: Target < 3 waves (2.25 min at 45s/wave)
2. **Match Success Rate**: Target > 85% within 5 waves
3. **Average MMR Difference**: Target 40-60 (competitive but not too strict)
4. **Median MMR Difference**: Target 20-40 (half of matches very competitive)

### Secondary Metrics
5. **Queue Size Distribution**: What % of waves have < 10 players?
6. **Long-Waiter Count**: How many wait > 5 waves?
7. **Max MMR Difference**: Are there outlier stomps (> 200 MMR)?
8. **Pressure Mode Distribution**: What % of waves in each pressure mode?

### Decision Rules
- If **avg wait > 5 waves** → Consider Aggressive
- If **queue size < 10 in > 40% of waves** → Consider Aggressive
- If **avg MMR diff > 60** → Consider Strict
- If **queue size > 30 consistently** → Consider Strict

---

## Implementation Notes

### Algorithm Flow (7 Stages)
1. **Queue Partitioning**: BW-only, SC2-only, Both
2. **Flexible Assignment**: Assign "both" players based on skill bias
3. **Pressure Calculation**: Determine MMR window parameters
4. **Priority Ordering**: Sort by distance from mean + wait bonus
5. **Locally-Optimal Matching**: Minimize squared MMR differences
6. **Least-Squares Refinement**: 2 passes of adjacent swaps
7. **Match Creation**: Map/server selection, database writes

### Key Features
- ✅ **BW vs SC2 only** (cross-race matching enforced)
- ✅ **Smart "both" assignment** (skill-based balancing)
- ✅ **Locally-optimal** (not greedy first-come-first-served)
- ✅ **Wait time fairness** (exponential priority growth)
- ✅ **Match quality refinement** (post-match optimization)
- ✅ **Adaptive pressure** (adjusts to queue conditions)

### Performance Characteristics
- **Complexity**: O(n²) where n = queue size
- **Processing Time**: < 0.1ms for n < 50
- **Memory**: O(n²) for candidate pairs (negligible)
- **Deterministic**: Same input → same output

---

## Files Reference

### Configuration
- `src/backend/core/config.py` - All tunable parameters

### Implementation
- `src/backend/services/matchmaking_service.py` - Core algorithm

### Tests
- `tests/backend/services/test_matchmaking_optimization.py` - 15 comprehensive tests

### Analysis Scripts
- `scripts/matchmaking_comparison_analysis.py` - Old vs New comparison
- `scripts/matchmaking_fairness_comparison.py` - Aggressive vs Balanced comparison
- `scripts/matchmaking_three_way_comparison.py` - All three configs
- `scripts/matchmaking_long_wait_analysis.py` - Detailed parameter analysis

### Documentation
- `docs/architecture/matchmaking_algorithm.md` - Complete algorithm documentation
- `docs/architecture/matchmaking_fairness_analysis.md` - Configuration comparison
- `docs/architecture/MATCHMAKING_CONFIG.md` - This file

---

## Quick Reference: Configuration Values

**To change configuration**, edit `src/backend/core/config.py`:

### Balanced (Current) ✅
```python
MM_HIGH_PRESSURE_THRESHOLD = 0.20
MM_MODERATE_PRESSURE_THRESHOLD = 0.10
MM_HIGH_PRESSURE_PARAMS = (75, 25)
MM_MODERATE_PRESSURE_PARAMS = (100, 35)
MM_LOW_PRESSURE_PARAMS = (125, 45)
MM_WAIT_CYCLE_PRIORITY_COEFFICIENT = 20
MM_WAIT_CYCLE_PRIORITY_EXPONENT = 1.25
MM_BALANCE_THRESHOLD_MMR = 50
```

### Aggressive Fairness
```python
MM_HIGH_PRESSURE_THRESHOLD = 0.12
MM_MODERATE_PRESSURE_THRESHOLD = 0.05
MM_HIGH_PRESSURE_PARAMS = (75, 25)
MM_MODERATE_PRESSURE_PARAMS = (120, 50)
MM_LOW_PRESSURE_PARAMS = (160, 70)
MM_WAIT_CYCLE_PRIORITY_COEFFICIENT = 60
MM_WAIT_CYCLE_PRIORITY_EXPONENT = 1.5
MM_BALANCE_THRESHOLD_MMR = 75
```

### Strict Quality
```python
MM_HIGH_PRESSURE_THRESHOLD = 0.30
MM_MODERATE_PRESSURE_THRESHOLD = 0.15
MM_HIGH_PRESSURE_PARAMS = (50, 20)
MM_MODERATE_PRESSURE_PARAMS = (75, 25)
MM_LOW_PRESSURE_PARAMS = (100, 30)
MM_WAIT_CYCLE_PRIORITY_COEFFICIENT = 10
MM_WAIT_CYCLE_PRIORITY_EXPONENT = 1.1
MM_BALANCE_THRESHOLD_MMR = 30
```

---

## Version History

- **v2.0 (Current)**: Balanced configuration
  - Locally-optimal matching
  - Smart "both" player assignment
  - Least-squares refinement
  - Adaptive pressure thresholds

- **v1.0 (Legacy)**: Greedy configuration
  - First-come-first-served
  - Simple equalization
  - No refinement
  - Fixed pressure thresholds (30%/50%)

---

## Contact / Support

For questions about matchmaking configuration:
- See full algorithm documentation: `docs/architecture/matchmaking_algorithm.md`
- Run comparison scripts in `scripts/` directory
- Check test suite: `pytest tests/backend/services/test_matchmaking_optimization.py -v`

**Recommendation**: Monitor metrics for 2-4 weeks after launch before considering configuration changes.

