# Matchmaking Algorithm - 8-Stage Locally-Optimal System

**Version**: 2.1 (Priority-Filtered)  
**Target**: 20-30 player queues during early launch  
**Complexity**: O(n²) where n = queue size  
**Performance**: < 0.1ms for 30 players

---

## Overview

The matchmaking system operates in discrete waves (every 10-45 seconds) with a deterministic 8-stage pipeline that:
1. Balances BW and SC2 populations intelligently
2. Minimizes MMR variance across all matches
3. Respects wait time priorities via pre-filtering and scoring
4. Adapts to queue pressure dynamically
5. Always matches BW vs SC2 (cross-race only)

**Key Improvements over v1.0**:
- **4-32% better match quality** (lower MMR differences)
- **Locally-optimal** matching vs greedy first-come-first-served
- **Smart "both" player** assignment based on skill balance
- **Priority-based pre-filtering** to prevent queue jumping (v2.1)
- **Least-squares refinement** to smooth MMR variance
- **Lower pressure thresholds** (10%/20% vs 30%/50%) for small populations

---

## Stage 1: Queue Partitioning

At wave start, capture queue snapshot under lock to prevent race conditions.

### Player Categorization

Players are sorted into **three mutually exclusive sets**:

| Set | Condition | MMR Reference |
|-----|-----------|---------------|
| `bw_only` | Has BW race, no SC2 race | `player.bw_mmr` |
| `sc2_only` | Has SC2 race, no BW race | `player.sc2_mmr` |
| `both` | Has both BW and SC2 races | Both `player.bw_mmr` and `player.sc2_mmr` |

Each player tracks:
- `discord_user_id`, `user_id`
- `preferences.selected_races`, `preferences.vetoed_maps`
- `bw_mmr`, `sc2_mmr` (cached from DataAccessService)
- `wait_cycles` (number of waves waited)
- `queue_start_time`
- `residential_region`

---

## Stage 2: Flexible Player Assignment ("Both" Players)

**Goal**: Assign each "both" player to either BW or SC2 to:
1. Balance population counts (hard constraint)
2. Balance mean MMR levels (soft constraint, threshold = 50 MMR)
3. Respect skill bias (prefer assigning to stronger side)

### Algorithm

```python
def equalize_lists(bw_only, sc2_only, both_races):
    # Step 1: Calculate population delta
    delta_n = len(bw_only) - len(sc2_only)
    
    # Step 2: Sort "both" by skill bias (SC2-favoring → BW-favoring)
    # Skill bias = bw_mmr - sc2_mmr
    both_sorted = sorted(both_races, key=lambda p: calculate_skill_bias(p))
    
    # Step 3: Assign to balance counts
    if delta_n < 0:  # BW needs players
        # Take most BW-favoring players (from end)
        for _ in range(abs(delta_n)):
            bw_list.append(both_sorted.pop())
    elif delta_n > 0:  # SC2 needs players
        # Take most SC2-favoring players (from start)
        for _ in range(delta_n):
            sc2_list.append(both_sorted.pop(0))
    
    # Step 4: Distribute remaining evenly
    while both_sorted:
        if len(bw_list) < len(sc2_list):
            bw_list.append(both_sorted.pop())
        elif len(bw_list) > len(sc2_list):
            sc2_list.append(both_sorted.pop(0))
        else:  # Equal - alternate
            sc2_list.append(both_sorted.pop(0))
            if both_sorted:
                bw_list.append(both_sorted.pop())
    
    # Step 5: Check mean MMR balance
    bw_mean = mean([p.bw_mmr for p in bw_list])
    sc2_mean = mean([p.sc2_mmr for p in sc2_list])
    mmr_delta = bw_mean - sc2_mean
    
    # If imbalance > 50 MMR, shift one neutral player
    if abs(mmr_delta) > MM_BALANCE_THRESHOLD_MMR:
        # Find most neutral "both" player and move to weaker side
        both_in_bw = [p for p in bw_list if p.has_both_races]
        both_in_sc2 = [p for p in sc2_list if p.has_both_races]
        
        both_in_bw.sort(key=lambda p: abs(skill_bias(p)))  # Most neutral first
        both_in_sc2.sort(key=lambda p: abs(skill_bias(p)))
        
        if mmr_delta > 50 and both_in_bw:
            # BW stronger, move to SC2
            player = both_in_bw[0]
            bw_list.remove(player)
            sc2_list.append(player)
        elif mmr_delta < -50 and both_in_sc2:
            # SC2 stronger, move to BW
            player = both_in_sc2[0]
            sc2_list.remove(player)
            bw_list.append(player)
    
    return bw_list, sc2_list, []
```

**Example**:
- Input: BW=2, SC2=5, Both=[p1(BW+200), p2(SC2+150), p3(Neutral)]
- Output: BW=4 (2+p1+p3), SC2=5 (5+p2)

---

## Stage 3: Pressure-Aware MMR Window Calculation

### Queue Pressure

```
pressure = min(1.0, (scale * queue_size) / active_population)
```

**Population-based scaling**:
- Pop ≤ 10: `scale = 1.2` (amplify pressure)
- Pop ≤ 25: `scale = 1.0` (balanced)
- Pop > 25: `scale = 0.8` (dampen pressure)

### Pressure Categories

| Pressure | Threshold | Base MMR | Growth/Wave |
|----------|-----------|----------|-------------|
| **HIGH** | ≥ 20% | 75 | 25 |
| **MODERATE** | ≥ 10% | 100 | 35 |
| **LOW** | < 10% | 125 | 45 |

### MMR Window Formula

```
max_diff(player) = base + (wait_cycles ÷ 1) × growth
```

**Example** (MODERATE pressure, 5 wait cycles):
```
max_diff = 100 + 5 × 35 = 275 MMR
```

---

## Stage 4: Priority-Based Pre-Filtering

**Goal**: Prevent fresh players from "stealing" matches from long-waiting players by filtering excess players based on priority.

### Problem This Solves

The matching algorithm only uses the **lead player's** wait cycles to determine MMR acceptance windows. This creates unfair bias:
- Follow players with long wait times get zero benefit from expanded MMR windows
- Fresh players on the larger side can match before veterans

**Example**: Lead has 1 player (1500 MMR, 0 cycles). Follow has 2 players: (1700 MMR, 10 cycles) and (1550 MMR, 0 cycles). Without filtering, the fresh 1550 MMR player matches while the veteran waits.

### Algorithm

Before matching begins, if one side has more players than the other:

```python
def _filter_by_priority(lead_side, follow_side):
    lead_count = len(lead_side)
    follow_count = len(follow_side)
    
    if lead_count == follow_count:
        return lead_side, follow_side  # No filtering needed
    
    if lead_count > follow_count:
        # Lead side has excess - keep only highest priority players
        sorted_lead = sorted(lead_side, key=lambda p: p.wait_cycles, reverse=True)
        filtered_lead = sorted_lead[:follow_count]
        return filtered_lead, follow_side
    else:
        # Follow side has excess - keep only highest priority players
        sorted_follow = sorted(follow_side, key=lambda p: p.wait_cycles, reverse=True)
        filtered_follow = sorted_follow[:lead_count]
        return lead_side, filtered_follow
```

### Execution Order

1. After `equalize_lists` assigns "both" players to BW or SC2
2. After determining which side is lead and which is follow
3. **Filter excess players by priority** ← This stage
4. Proceed to candidate building and matching

### Example

**Before filtering:**
- Lead: 1 player (1500 MMR, 0 cycles)
- Follow: 2 players (1700 MMR, 10 cycles) and (1550 MMR, 0 cycles)

**After filtering:**
- Lead: 1 player (1500 MMR, 0 cycles)
- Follow: 1 player (1700 MMR, 10 cycles) ← kept by priority
- Filtered out: (1550 MMR, 0 cycles) ← removed from this wave

**Outcome**: The veteran player (10 cycles) gets first consideration. If no match occurs this wave, both players remain in queue for the next wave with incremented wait_cycles.

### Benefits

1. **Eliminates queue jumping** - fresh players cannot steal matches from veterans
2. **Fair priority enforcement** - wait_cycles determines candidacy, not just scoring
3. **Maintains algorithm integrity** - existing matching logic remains unchanged
4. **Deterministic** - clear priority ordering based on wait time

---

## Stage 5: Locally-Optimal Matching

**Old approach (greedy)**: Process players by wait time, each picks their best match.  
**New approach (locally-optimal)**: Consider all valid pairs, select globally.

### Algorithm

```python
def find_matches(lead_side, follow_side, is_bw_match):
    # 1. Build all valid candidate pairs within MMR windows
    candidates = []
    for lead_player in lead_side:
        lead_mmr = lead_player.bw_mmr if is_bw_match else lead_player.sc2_mmr
        max_diff = max_diff(lead_player.wait_cycles)
        
        for follow_player in follow_side:
            follow_mmr = follow_player.sc2_mmr if is_bw_match else follow_player.bw_mmr
            mmr_diff = abs(lead_mmr - follow_mmr)
            
            if mmr_diff <= max_diff:
                # Score: lower is better
                wait_priority = lead_player.wait_cycles + follow_player.wait_cycles
                score = (mmr_diff ** 2) - (wait_priority × 20)
                
                candidates.append((score, lead_player, follow_player, mmr_diff))
    
    # 2. Sort by score (ascending)
    candidates.sort(key=lambda x: x[0])
    
    # 3. Greedily select matches (no player reuse)
    matches = []
    used_lead = set()
    used_follow = set()
    
    for score, lead, follow, mmr_diff in candidates:
        if lead.id not in used_lead and follow.id not in used_follow:
            matches.append((lead, follow))
            used_lead.add(lead.id)
            used_follow.add(follow.id)
    
    return matches
```

**Why squared MMR difference?**  
Heavily penalizes large gaps:
- Two matches at 50 MMR diff: `50² + 50² = 5,000`
- One at 100, one at 0: `100² + 0² = 10,000` (much worse!)

**Wait time priority**:  
Subtracting `wait_cycles × 20` from score gives long-waiters preference even with slightly worse MMR fits.

---

## Stage 6: Least-Squares Refinement

After initial matching, perform **2 passes** of adjacent swaps to minimize total squared error.

### Algorithm

```python
def refine_matches_least_squares(matches, is_bw_match):
    for pass_num in range(2):  # 2 passes
        swaps_made = False
        
        for i in range(len(matches) - 1):
            (p1_lead, p1_follow) = matches[i]
            (p2_lead, p2_follow) = matches[i+1]
            
            # Calculate squared error before
            error_before = (p1_lead.mmr - p1_follow.mmr)² + 
                          (p2_lead.mmr - p2_follow.mmr)²
            
            # Calculate squared error after swapping follow players
            error_after = (p1_lead.mmr - p2_follow.mmr)² + 
                         (p2_lead.mmr - p1_follow.mmr)²
            
            if error_after < error_before:
                # Check swap respects MMR windows
                new_diff_1 = abs(p1_lead.mmr - p2_follow.mmr)
                new_diff_2 = abs(p2_lead.mmr - p1_follow.mmr)
                
                if (new_diff_1 <= max_diff(p1_lead.wait_cycles) and
                    new_diff_2 <= max_diff(p2_lead.wait_cycles)):
                    # Perform swap
                    matches[i] = (p1_lead, p2_follow)
                    matches[i+1] = (p2_lead, p1_follow)
                    swaps_made = True
        
        if not swaps_made:
            break  # No more improvements
    
    return matches
```

**Example**:
```
Before: [(1500 BW, 1610 SC2), (1600 BW, 1490 SC2)]
Error:  110² + 110² = 24,200

After:  [(1500 BW, 1490 SC2), (1600 BW, 1610 SC2)]
Error:  10² + 10² = 200

Improvement: 99.2% reduction in error!
```

---

## Stage 7: Match Creation

For each finalized match pair:

1. **Map Selection**: Random from non-vetoed maps
   ```python
   available_maps = all_maps - (p1.vetoed_maps ∪ p2.vetoed_maps)
   map_choice = random.choice(available_maps)
   ```

2. **Server Selection**: Optimal for player regions
   ```python
   if both_regions_valid:
       server = regions_service.get_match_server(p1.region, p2.region)
   else:
       server = regions_service.get_random_game_server()
   ```

3. **Channel Assignment**: Rotates through `scevo01` to `scevo10`
   ```python
   channel_num = (match_id % 10) or 10
   in_game_channel = f"scevo{channel_num:02d}"
   ```

4. **Database Record**: Created via `DataAccessService`
   - Player IDs, races, MMRs
   - Map, server, channel
   - Match state: `"pending"`
   - Player states: `"in_match:{match_id}"`

---

## Stage 8: Queue Cleanup

1. Update `recent_activity` timestamps for matched players
2. Remove matched players from `matchmaker.players` list
3. Sync removal with `QueueService` for admin visibility
4. Log final statistics:
   - Total matches found
   - Remaining queue size
   - Match quality metrics (avg/min/max MMR diff)

---

## Performance Characteristics

### Complexity Analysis

| Stage | Operation | Complexity |
|-------|-----------|------------|
| 1 | Categorize | O(n) |
| 2 | Equalize | O(n log n) (sorting) |
| 3 | Pressure calc | O(1) |
| 4 | Priority filter | O(n log n) (sorting) |
| 5 | Build candidates | O(n²) |
| 5 | Sort + select | O(n² log n) |
| 6 | Refinement | O(n) per pass, 2 passes |
| 7-8 | Match creation | O(n) |

**Total**: O(n² log n) ≈ O(n²) for practical n < 100

### Benchmark Results

| Queue Size | Old (Greedy) | New (Optimal) | MMR Improvement |
|------------|--------------|---------------|-----------------|
| 5 players | 0.003 ms | 0.003 ms | +29.4% |
| 10 players | 0.006 ms | 0.007 ms | +10.2% |
| 20 players | 0.017 ms | 0.024 ms | +7.4% |
| 30 players | 0.036 ms | 0.054 ms | +23.0% |

**Conclusion**: Processing time remains negligible (< 0.1ms) while match quality improves dramatically.

---

## Configuration Parameters

### Pressure Thresholds
```python
MM_HIGH_PRESSURE_THRESHOLD = 0.20  # 20% queue/active ratio
MM_MODERATE_PRESSURE_THRESHOLD = 0.10  # 10% queue/active ratio
```

### MMR Windows
```python
MM_HIGH_PRESSURE_PARAMS = (75, 25)      # (base, growth)
MM_MODERATE_PRESSURE_PARAMS = (100, 35)
MM_LOW_PRESSURE_PARAMS = (125, 45)
```

### Population Scaling
```python
MM_POPULATION_THRESHOLD_LOW = 10
MM_POPULATION_THRESHOLD_MID = 25
MM_PRESSURE_SCALE_LOW_POP = 1.2  # Amplify for small pops
MM_PRESSURE_SCALE_MID_POP = 1.0
MM_PRESSURE_SCALE_HIGH_POP = 0.8  # Dampen for large pops
```

### Matching Priorities
```python
MM_WAIT_CYCLE_PRIORITY_COEFFICIENT = 20  # Wait time bonus
MM_BALANCE_THRESHOLD_MMR = 50  # Skill balance threshold
MM_REFINEMENT_PASSES = 2  # Swap optimization passes
```

---

## Example Walkthrough

### Input Queue (15 players)
```
BW-only: 3 players (avg MMR: 1450)
SC2-only: 5 players (avg MMR: 1550)
Both: 7 players (biases: -200, -100, -50, 0, +50, +100, +200)
```

### Stage 2: Equalization
```
Delta = 3 - 5 = -2 (BW needs 2 more)
Assign: +100 and +200 bias players to BW
Result: BW=5, SC2=5, remaining_both=5

Distribute remaining evenly:
BW=7 (3+2+2), SC2=8 (5+3)

Check mean balance:
BW avg: 1480, SC2 avg: 1530, delta=50 (at threshold, acceptable)
```

### Stage 4: Matching (assuming 30 active players)
```
Pressure = 0.8 × 15 / 30 = 0.40 → HIGH (≥0.20)
MMR window: base=75, growth=25

Lead side: BW (7 players)
Follow side: SC2 (8 players)

Candidates built: 7 × 8 = 56 pairs (before filtering)
After MMR filtering: ~35 valid pairs

Top 5 candidates by score:
1. (1520 BW, 1515 SC2): score = 25 - 0×20 = 25
2. (1480 BW, 1485 SC2): score = 25 - 4×20 = -55
3. (1600 BW, 1590 SC2): score = 100 - 2×20 = 60
...

Matches selected: 7 pairs (all BW matched)
```

### Stage 5: Refinement
```
Initial:
  Match 1: (1520, 1515), diff=5
  Match 2: (1480, 1530), diff=50
  Error = 5² + 50² = 2,525

Swap follow players:
  Match 1: (1520, 1530), diff=10
  Match 2: (1480, 1515), diff=35
  Error = 10² + 35² = 1,325

Improved by 47%! Swap accepted.
```

### Output
```
7 matches created
1 SC2 player remains in queue
Avg MMR diff: 18.4
Match quality: Excellent
Processing time: 0.02 ms
```

---

## Logging Output

```
⏰ Checking for matches with 15 players in queue...
🎯 Attempting to match players with advanced algorithm...
   📊 Queue composition: BW-only=3, SC2-only=5, Both=7
   📊 After equalization: BW=7, SC2=8, Remaining Z=0
   ⚖️  Skill balance: BW avg=1480, SC2 avg=1530, delta=50
   ✅ Found 7 BW vs SC2 matches (lead: 7, follow: 8)
   🔄 Least-squares refinement: 3 swaps made across 2 passes
   📈 Match quality: avg MMR diff=18.4, min=5, max=45
   📊 Final state: 14 players matched
```

---

## Future Optimizations

1. **Global Optimal Matching**: Use Hungarian algorithm for true O(n³) global optimization (when n > 50)
2. **Machine Learning**: Predict match quality and player satisfaction
3. **Dynamic Thresholds**: Adjust pressure thresholds based on historical queue patterns
4. **Multi-Wave Lookahead**: Consider future waves when making current assignments
5. **Skill Variance Minimization**: Optimize not just mean balance but variance within sides

---

## References

- Original greedy algorithm: `src/backend/services/matchmaking_service.py` (v1.0)
- Optimization exploration: `scripts/matchmaking_optimization_exploration.py`
- Comparison analysis: `scripts/matchmaking_comparison_analysis.py`
- Tests: `tests/backend/services/test_matchmaking_optimization.py`

