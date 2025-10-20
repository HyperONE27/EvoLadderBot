# Comprehensive Testing Strategy for Critical Modules

**Date**: October 20, 2025  
**Version**: 1.0  
**Purpose**: Define rigorous, mathematically-grounded test strategies for the 5 most critical services

---

## Table of Contents

1. [MMR Service (Rating Calculations)](#1-mmr-service)
2. [Matchmaking Service (Player Pairing)](#2-matchmaking-service)
3. [Command Guard Service (Authorization Flow)](#3-command-guard-service)
4. [Replay Service (File Processing)](#4-replay-service)
5. [Match Completion Service (State Machine)](#5-match-completion-service)

---

## 1. MMR Service

**File**: `src/backend/services/mmr_service.py`  
**Criticality**: HIGHEST - Incorrect MMR calculations affect competitive integrity  
**Algorithm**: Elo rating system with K-factor adaptation

### Mathematical Foundation

The service implements the Elo rating formula:

```
E_a = 1 / (1 + 10^((R_b - R_a) / D))
R'_a = R_a + K * (S_a - E_a)

Where:
- E_a = Expected score for player A (0.0 to 1.0)
- R_a, R_b = Current ratings for players A and B
- D = Divisor constant (500 in this implementation)
- K = K-factor constant (40 in this implementation)
- S_a = Actual score (1.0 = win, 0.5 = draw, 0.0 = loss)
- R'_a = New rating for player A
```

### Critical Invariants

1. **Conservation of Rating Points**: For non-draw outcomes, `|ΔR_a + ΔR_b| ≤ 1` (rounding error)
2. **Symmetry**: If A beats B, the MMR changes should be equal and opposite (within rounding)
3. **Monotonicity**: Higher MMR opponent → larger gain on win, smaller loss on defeat
4. **Draw Behavior**: In evenly matched games, draws should result in ~0 MMR change
5. **Default MMR**: All new players start at 1500
6. **Range Bounds**: MMR can theoretically go negative or exceed any upper bound

### Test Case Structure

```python
def test_calculate_new_mmr_symmetry(self, mmr_service):
    """Test that MMR changes are symmetric for equal-rated players"""
    
    test_cases = [
        # (p1_mmr, p2_mmr, result, expected_p1_change, expected_p2_change, tolerance)
        
        # Equal ratings - wins
        (1500, 1500, 1, +20, -20, 1),  # K=40, E=0.5, S=1.0 → 40*(1.0-0.5) = +20
        (1500, 1500, 2, -20, +20, 1),
        
        # Equal ratings - draw
        (1500, 1500, 0, 0, 0, 1),      # K=40, E=0.5, S=0.5 → 40*(0.5-0.5) = 0
        
        # Edge cases - perfect symmetry
        (1000, 1000, 1, +20, -20, 1),
        (2000, 2000, 1, +20, -20, 1),
        (3000, 3000, 1, +20, -20, 1),
        
        # Extreme ratings
        (0, 0, 1, +20, -20, 1),
        (5000, 5000, 1, +20, -20, 1),
    ]
    
    for p1_mmr, p2_mmr, result, expected_p1_delta, expected_p2_delta, tolerance in test_cases:
        outcome = mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, result)
        actual_p1_delta = outcome.player_one_mmr - p1_mmr
        actual_p2_delta = outcome.player_two_mmr - p2_mmr
        
        assert abs(actual_p1_delta - expected_p1_delta) <= tolerance, \
            f"P1 delta for ({p1_mmr},{p2_mmr},result={result}): expected {expected_p1_delta}, got {actual_p1_delta}"
        assert abs(actual_p2_delta - expected_p2_delta) <= tolerance, \
            f"P2 delta for ({p1_mmr},{p2_mmr},result={result}): expected {expected_p2_delta}, got {actual_p2_delta}"
        
        # Verify conservation (sum should be ~0 for wins/losses, exactly 0 for draws)
        if result != 0:
            assert abs(actual_p1_delta + actual_p2_delta) <= 1, \
                f"Conservation violated: {actual_p1_delta} + {actual_p2_delta} = {actual_p1_delta + actual_p2_delta}"
```

### Test Cases by Category

#### 1. Expected Score Calculation

```python
def test_calculate_expected_score(self, mmr_service):
    """Test the expected score formula against known values"""
    
    test_cases = [
        # (p1_mmr, p2_mmr, expected_e1, expected_e2, tolerance)
        # Formula: E_a = 1 / (1 + 10^((R_b - R_a) / 500))
        
        # Equal ratings → 50% each
        (1500, 1500, 0.5, 0.5, 0.001),
        
        # +100 rating advantage → ~64% vs 36%
        (1600, 1500, 0.640, 0.360, 0.001),  # 1/(1+10^(-100/500)) = 0.6400
        (1500, 1600, 0.360, 0.640, 0.001),
        
        # +200 rating advantage → ~76% vs 24%
        (1700, 1500, 0.760, 0.240, 0.001),  # 1/(1+10^(-200/500)) = 0.7599
        
        # +500 rating advantage → ~90.9% vs 9.1%
        (2000, 1500, 0.909, 0.091, 0.001),  # 1/(1+10^(-500/500)) = 0.9091
        
        # Large rating gaps
        (2500, 1500, 0.990, 0.010, 0.001),  # 1000 point gap
        (3000, 1500, 0.9990, 0.0010, 0.001),  # 1500 point gap
        
        # Verify E1 + E2 = 1.0 always
        (1234, 5678, None, None, 0.001),  # Will check sum = 1.0
        (9999, 1, None, None, 0.001),
    ]
    
    for p1_mmr, p2_mmr, expected_e1, expected_e2, tolerance in test_cases:
        e1, e2 = mmr_service._calculate_expected_mmr(p1_mmr, p2_mmr)
        
        if expected_e1 is not None:
            assert abs(e1 - expected_e1) <= tolerance, \
                f"E1 for ({p1_mmr},{p2_mmr}): expected {expected_e1}, got {e1}"
            assert abs(e2 - expected_e2) <= tolerance, \
                f"E2 for ({p1_mmr},{p2_mmr}): expected {expected_e2}, got {e2}"
        
        # Always verify E1 + E2 = 1.0
        assert abs((e1 + e2) - 1.0) <= tolerance, \
            f"Expected scores don't sum to 1.0: {e1} + {e2} = {e1 + e2}"
```

#### 2. Asymmetric MMR Scenarios (Upset Victories)

```python
def test_asymmetric_mmr_upset_mechanics(self, mmr_service):
    """Test that upsets award more points than expected wins"""
    
    test_cases = [
        # (lower_mmr, higher_mmr, mmr_diff, expected_upset_gain, expected_expected_loss, tolerance)
        # When lower beats higher, they should gain more than K/2
        # When higher beats lower, they should gain less than K/2
        
        # 100 point underdog wins (E ≈ 0.36, S = 1.0)
        (1500, 1600, 100, +26, -26, 1),  # 40 * (1.0 - 0.36) = +25.6
        
        # 200 point underdog wins (E ≈ 0.24, S = 1.0)
        (1500, 1700, 200, +30, -30, 1),  # 40 * (1.0 - 0.24) = +30.4
        
        # 500 point underdog wins (E ≈ 0.091, S = 1.0)
        (1500, 2000, 500, +36, -36, 1),  # 40 * (1.0 - 0.091) = +36.36
        
        # Extreme upset: 1000 point underdog
        (1500, 2500, 1000, +40, -40, 1),  # 40 * (1.0 - 0.01) ≈ +39.6
        
        # Expected win by favorite (should gain less)
        # 100 point favorite wins (E ≈ 0.64, S = 1.0)
        (1600, 1500, -100, +14, -14, 1),  # 40 * (1.0 - 0.64) = +14.4
        
        # 500 point favorite wins (E ≈ 0.909, S = 1.0)
        (2000, 1500, -500, +4, -4, 1),  # 40 * (1.0 - 0.909) = +3.64
        
        # Extreme favorite barely wins
        (2500, 1500, -1000, +0, -0, 1),  # 40 * (1.0 - 0.99) ≈ +0.4 → rounds to 0
    ]
    
    for lower_mmr, higher_mmr, mmr_diff, expected_gain, expected_loss, tolerance in test_cases:
        # Lower rated player wins
        outcome = mmr_service.calculate_new_mmr(lower_mmr, higher_mmr, 1)
        actual_gain = outcome.player_one_mmr - lower_mmr
        actual_loss = outcome.player_two_mmr - higher_mmr
        
        assert abs(actual_gain - expected_gain) <= tolerance, \
            f"Upset win ({lower_mmr} beats {higher_mmr}): expected +{expected_gain}, got +{actual_gain}"
        assert abs(actual_loss - expected_loss) <= tolerance, \
            f"Upset loss ({higher_mmr} loses to {lower_mmr}): expected {expected_loss}, got {actual_loss}"
```

#### 3. Draw Mechanics

```python
def test_draw_mmr_distribution(self, mmr_service):
    """Test MMR distribution in draws"""
    
    test_cases = [
        # (p1_mmr, p2_mmr, expected_p1_change, expected_p2_change, tolerance)
        # Draw: S = 0.5 for both, so change = K * (0.5 - E)
        
        # Equal players draw → no change
        (1500, 1500, 0, 0, 1),  # E = 0.5, 40 * (0.5 - 0.5) = 0
        
        # Higher rated draws against lower → loses points
        # P1=1600, P2=1500: E1=0.64, so change = 40 * (0.5 - 0.64) = -5.6
        (1600, 1500, -6, +6, 1),
        
        # Lower rated draws against higher → gains points
        (1500, 1600, +6, -6, 1),
        
        # Large gap draws heavily favor underdog
        # P1=1500, P2=2000: E1=0.091, so change = 40 * (0.5 - 0.091) = +16.36
        (1500, 2000, +16, -16, 1),
        
        # Massive gap
        (1500, 2500, +20, -20, 1),  # E ≈ 0.01, 40 * (0.5 - 0.01) ≈ +19.6
    ]
    
    for p1_mmr, p2_mmr, expected_p1_delta, expected_p2_delta, tolerance in test_cases:
        outcome = mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, 0)  # 0 = draw
        actual_p1_delta = outcome.player_one_mmr - p1_mmr
        actual_p2_delta = outcome.player_two_mmr - p2_mmr
        
        assert abs(actual_p1_delta - expected_p1_delta) <= tolerance, \
            f"Draw P1 change ({p1_mmr} vs {p2_mmr}): expected {expected_p1_delta}, got {actual_p1_delta}"
        assert abs(actual_p2_delta - expected_p2_delta) <= tolerance, \
            f"Draw P2 change ({p1_mmr} vs {p2_mmr}): expected {expected_p2_delta}, got {actual_p2_delta}"
```

#### 4. Edge Cases and Boundary Conditions

```python
def test_mmr_edge_cases(self, mmr_service):
    """Test extreme values and edge cases"""
    
    test_cases = [
        # (p1_mmr, p2_mmr, result, scenario_description)
        
        # Zero and negative MMR
        (0, 1500, 1, "Zero MMR wins"),
        (0, 1500, 2, "Zero MMR loses"),
        (-1000, 1500, 1, "Negative MMR wins"),
        (1500, 0, 1, "Wins against zero MMR"),
        
        # Very high MMR
        (10000, 10000, 1, "Very high equal MMR"),
        (10000, 1500, 1, "Extreme favorite wins"),
        (1500, 10000, 1, "Extreme underdog wins"),
        
        # Both at extremes
        (0, 10000, 1, "Min vs max MMR, min wins"),
        (10000, 0, 2, "Max vs min MMR, min wins"),
        
        # Identity cases
        (1500, 1500, 1, "Equal MMR, P1 wins"),
        (1500, 1500, 2, "Equal MMR, P2 wins"),
        (1500, 1500, 0, "Equal MMR, draw"),
    ]
    
    for p1_mmr, p2_mmr, result, description in test_cases:
        # Should not raise exception
        outcome = mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, result)
        
        # Verify output is valid
        assert isinstance(outcome.player_one_mmr, int), \
            f"{description}: P1 MMR is not int: {outcome.player_one_mmr}"
        assert isinstance(outcome.player_two_mmr, int), \
            f"{description}: P2 MMR is not int: {outcome.player_two_mmr}"
        
        # Verify conservation of points (for non-draws)
        if result != 0:
            p1_change = outcome.player_one_mmr - p1_mmr
            p2_change = outcome.player_two_mmr - p2_mmr
            assert abs(p1_change + p2_change) <= 1, \
                f"{description}: Conservation violated: {p1_change} + {p2_change}"
```

#### 5. Invalid Input Handling

```python
def test_invalid_inputs(self, mmr_service):
    """Test that invalid inputs raise appropriate exceptions"""
    
    test_cases = [
        # (p1_mmr, p2_mmr, result, expected_exception)
        (1500, 1500, 3, ValueError),  # Invalid result
        (1500, 1500, -1, ValueError),  # Invalid result
        (1500, 1500, 1.5, ValueError),  # Non-integer result (if validation exists)
        (1500, 1500, None, (ValueError, TypeError)),  # None result
    ]
    
    for p1_mmr, p2_mmr, result, expected_exception in test_cases:
        with pytest.raises(expected_exception):
            mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, result)
```

---

## 2. Matchmaking Service

**File**: `src/backend/services/matchmaking_service.py`  
**Criticality**: HIGHEST - Core gameplay experience  
**Algorithm**: Elastic MMR window with queue pressure adaptation

### Mathematical Foundation

The matchmaking service uses an elastic MMR window formula:

```
max_diff(cycles, pressure) = base + (growth * cycles)

Where:
- base, growth depend on queue pressure ratio
- cycles = number of matchmaking waves player has waited
- pressure = queue_size / active_population

Pressure Thresholds:
- High (>50%): base=75, growth=25
- Moderate (>30%): base=100, growth=35
- Low: base=125, growth=45

Population Scale Multipliers:
- ≤25 players: 1.2x pressure (amplify small queue impact)
- ≤100 players: 1.0x pressure (balanced)
- >100 players: 0.8x pressure (dampen large queue noise)
```

### Critical Invariants

1. **MMR Window Growth**: `max_diff(n+1) > max_diff(n)` - window always expands over time
2. **Race Compatibility**: BW players only match BW, SC2 only match SC2
3. **Both-Race Priority**: Players with both races selected match first
4. **Map Veto**: Matched players must share at least 1 non-vetoed map
5. **Server Selection**: Regional preference respected, fallback to nearest
6. **No Self-Matching**: Player cannot match themselves
7. **Atomic Queue Operations**: Add/remove must be thread-safe
8. **Activity Window**: Players active in last 15 minutes count toward population

### Test Case Structure

```python
def test_mmr_window_expansion(self, matchmaker):
    """Test that MMR window expands correctly over time"""
    
    test_cases = [
        # (cycles, queue_pressure, expected_base, expected_growth, expected_at_cycle_0, expected_at_cycle_5)
        
        # High pressure scenarios (>50%)
        (0, 0.6, 75, 25, 75, 200),   # base=75, after 5 cycles: 75 + 5*25 = 200
        (1, 0.6, 75, 25, 100, 225),  # After 1 cycle: 100, after 6 cycles: 225
        
        # Moderate pressure (30-50%)
        (0, 0.4, 100, 35, 100, 275),  # base=100, after 5 cycles: 100 + 5*35 = 275
        
        # Low pressure (<30%)
        (0, 0.2, 125, 45, 125, 350),  # base=125, after 5 cycles: 125 + 5*45 = 350
        
        # Edge cases
        (0, 0.0, 125, 45, 125, 350),  # Zero pressure = low pressure
        (0, 1.0, 75, 25, 75, 200),    # 100% pressure = high pressure
        (10, 0.5, 75, 25, 325, 575),  # Long wait time amplification
    ]
    
    for cycles, pressure, base, growth, expected_cycle_0, expected_cycle_5 in test_cases:
        # Calculate max_diff at cycle 0
        max_diff_0 = matchmaker._calculate_max_diff(cycles, pressure, base, growth)
        assert max_diff_0 == expected_cycle_0, \
            f"Cycle {cycles}, pressure {pressure}: expected {expected_cycle_0}, got {max_diff_0}"
        
        # Calculate max_diff at cycle 0 + 5
        max_diff_5 = matchmaker._calculate_max_diff(cycles + 5, pressure, base, growth)
        assert max_diff_5 == expected_cycle_5, \
            f"Cycle {cycles+5}, pressure {pressure}: expected {expected_cycle_5}, got {max_diff_5}"
        
        # Verify monotonic increase
        assert max_diff_5 > max_diff_0, \
            f"Window should expand: {max_diff_0} -> {max_diff_5}"
```

### Test Cases by Category

#### 1. Race Compatibility Matrix

```python
def test_race_matching_rules(self, matchmaker):
    """Test that race matching follows strict BW/SC2 separation"""
    
    test_cases = [
        # (p1_races, p2_races, should_match, expected_race_type)
        
        # Same race type - should match
        (["bw_terran"], ["bw_zerg"], True, "bw"),
        (["sc2_protoss"], ["sc2_terran"], True, "sc2"),
        
        # Both races - can match either
        (["bw_terran", "sc2_zerg"], ["bw_protoss"], True, "bw"),
        (["bw_terran", "sc2_zerg"], ["sc2_protoss"], True, "sc2"),
        (["bw_terran", "sc2_zerg"], ["bw_protoss", "sc2_terran"], True, "either"),
        
        # Cross-game - should NOT match
        (["bw_terran"], ["sc2_zerg"], False, None),
        (["sc2_protoss"], ["bw_terran"], False, None),
        
        # One has both, other has incompatible single
        (["bw_terran", "sc2_zerg"], ["sc2_protoss"], True, "sc2"),
        
        # Edge cases
        ([], ["bw_terran"], False, None),  # Empty races
        (["bw_terran"], [], False, None),
        ([], [], False, None),
    ]
    
    for p1_races, p2_races, should_match, expected_race_type in test_cases:
        result = matchmaker._are_races_compatible(p1_races, p2_races)
        
        assert result == should_match, \
            f"Race compatibility ({p1_races} vs {p2_races}): expected {should_match}, got {result}"
        
        if should_match:
            race_type = matchmaker._determine_match_race_type(p1_races, p2_races)
            if expected_race_type != "either":
                assert race_type == expected_race_type, \
                    f"Race type ({p1_races} vs {p2_races}): expected {expected_race_type}, got {race_type}"
```

#### 2. Map Veto System

```python
def test_map_veto_mechanics(self, matchmaker):
    """Test map selection with vetoes"""
    
    # Assume map pool: ["Arid", "Goldenaura", "Oceanborn", "Crimsonpath", "Ephemeron"]
    
    test_cases = [
        # (p1_vetoes, p2_vetoes, valid_maps_count, should_find_map)
        
        # No vetoes - all maps available
        ([], [], 5, True),
        
        # One player vetoes - 4 maps remain
        (["Arid"], [], 4, True),
        ([], ["Goldenaura"], 4, True),
        
        # Both veto different maps - 3 maps remain
        (["Arid"], ["Goldenaura"], 3, True),
        
        # Both veto same map - 4 maps remain
        (["Arid"], ["Arid"], 4, True),
        
        # Maximum vetoes (4 each) with overlap - at least 1 map remains
        (["Arid", "Goldenaura", "Oceanborn", "Crimsonpath"], 
         ["Goldenaura", "Oceanborn", "Crimsonpath", "Ephemeron"], 
         1, True),  # Only "Arid" and "Ephemeron" remain, but Arid vetoed by p1, so just Ephemeron
        
        # Impossible scenario - all maps vetoed by at least one player
        (["Arid", "Goldenaura", "Oceanborn", "Crimsonpath", "Ephemeron"],
         [], 
         0, False),
        
        # Overlapping vetoes
        (["Arid", "Goldenaura"], ["Goldenaura", "Oceanborn"], 2, True),  # Crimsonpath, Ephemeron
    ]
    
    map_pool = ["Arid", "Goldenaura", "Oceanborn", "Crimsonpath", "Ephemeron"]
    
    for p1_vetoes, p2_vetoes, expected_valid_count, should_find_map in test_cases:
        valid_maps = matchmaker._get_valid_maps(p1_vetoes, p2_vetoes, map_pool)
        
        assert len(valid_maps) == expected_valid_count, \
            f"Map count (P1={p1_vetoes}, P2={p2_vetoes}): expected {expected_valid_count}, got {len(valid_maps)}"
        
        if should_find_map:
            assert len(valid_maps) > 0, \
                f"Should find valid map but got none: P1={p1_vetoes}, P2={p2_vetoes}"
            selected = matchmaker._select_random_map(valid_maps)
            assert selected in valid_maps, \
                f"Selected map {selected} not in valid maps {valid_maps}"
```

#### 3. MMR-Based Pairing

```python
def test_mmr_pairing_logic(self, matchmaker):
    """Test that MMR-based pairing respects window constraints"""
    
    test_cases = [
        # (p1_mmr, p1_cycles, p2_mmr, p2_cycles, queue_pressure, should_match)
        
        # Equal MMR, fresh players - always match
        (1500, 0, 1500, 0, 0.3, True),
        
        # Small MMR difference within initial window
        (1500, 0, 1550, 0, 0.3, True),   # 50 diff, base=100
        (1500, 0, 1600, 0, 0.3, False),  # 100 diff, exceeds base=100
        
        # Window expansion allows match
        (1500, 0, 1600, 0, 0.3, False),  # 100 diff, cycle 0, base=100 -> NO
        (1500, 1, 1600, 0, 0.3, True),   # 100 diff, p1 cycle 1, window=135 -> YES
        
        # High pressure reduces window, prevents match
        (1500, 0, 1550, 0, 0.6, True),   # 50 diff, base=75 (high pressure) -> YES
        (1500, 0, 1600, 0, 0.6, False),  # 100 diff, exceeds base=75 -> NO
        
        # Long wait time expands window significantly
        (1500, 10, 2000, 0, 0.3, True),  # 500 diff, but cycle 10: 100 + 10*35 = 450 -> YES for one player
        
        # Extreme MMR differences
        (1500, 0, 3000, 0, 0.3, False),  # 1500 diff, base=100 -> NO
        (1500, 20, 3000, 0, 0.3, True),  # 1500 diff, cycle 20: 100 + 20*35 = 800 for p1, still may not match p2 cycle 0
    ]
    
    for p1_mmr, p1_cycles, p2_mmr, p2_cycles, pressure, should_match in test_cases:
        # Calculate windows for both players
        base, growth = matchmaker._get_pressure_params(pressure)
        p1_window = matchmaker._calculate_max_diff(p1_cycles, pressure, base, growth)
        p2_window = matchmaker._calculate_max_diff(p2_cycles, pressure, base, growth)
        
        mmr_diff = abs(p1_mmr - p2_mmr)
        
        # Match if EITHER player's window is large enough
        can_match = (mmr_diff <= p1_window) or (mmr_diff <= p2_window)
        
        assert can_match == should_match, \
            f"MMR pairing ({p1_mmr}@cycle{p1_cycles} vs {p2_mmr}@cycle{p2_cycles}, pressure={pressure}): " \
            f"diff={mmr_diff}, p1_window={p1_window}, p2_window={p2_window}, expected {should_match}, got {can_match}"
```

#### 4. Queue Pressure Calculation

```python
def test_queue_pressure_calculation(self, matchmaker):
    """Test queue pressure calculation with population scaling"""
    
    test_cases = [
        # (queue_size, active_population, expected_raw_pressure, expected_scaled_pressure, expected_category)
        
        # Small population amplification (≤25)
        (10, 20, 0.50, 0.60, "high"),      # 1.2x scale: 0.50 * 1.2 = 0.60 > 0.50 threshold
        (5, 20, 0.25, 0.30, "moderate"),   # 1.2x scale: 0.25 * 1.2 = 0.30
        (3, 20, 0.15, 0.18, "low"),        # 1.2x scale: 0.15 * 1.2 = 0.18
        
        # Medium population balanced (26-100)
        (30, 60, 0.50, 0.50, "high"),      # 1.0x scale
        (20, 60, 0.33, 0.33, "moderate"),  # 1.0x scale
        (10, 60, 0.17, 0.17, "low"),       # 1.0x scale
        
        # Large population dampening (>100)
        (60, 120, 0.50, 0.40, "moderate"), # 0.8x scale: 0.50 * 0.8 = 0.40 (drops from high to moderate)
        (40, 120, 0.33, 0.26, "low"),      # 0.8x scale: 0.33 * 0.8 = 0.26 (drops from moderate to low)
        
        # Edge cases
        (0, 100, 0.00, 0.00, "low"),       # No queue pressure
        (100, 100, 1.00, 0.80, "high"),    # 100% queueing in large pop, dampened to 0.80
        (10, 0, None, 0.00, "low"),        # Division by zero → 0 pressure
    ]
    
    for queue_size, active_pop, expected_raw, expected_scaled, expected_category in test_cases:
        pressure = matchmaker._calculate_queue_pressure(queue_size, active_pop)
        
        if expected_scaled is not None:
            assert abs(pressure - expected_scaled) < 0.01, \
                f"Pressure ({queue_size}/{active_pop}): expected {expected_scaled}, got {pressure}"
        
        # Determine category
        category = matchmaker._get_pressure_category(pressure)
        assert category == expected_category, \
            f"Pressure category ({pressure}): expected {expected_category}, got {category}"
```

#### 5. Concurrent Queue Operations

```python
async def test_concurrent_queue_operations(self, matchmaker):
    """Test thread-safety of add/remove operations"""
    
    test_cases = [
        # (operation_sequence, expected_final_queue_size)
        
        # Sequential adds
        ([("add", 1), ("add", 2), ("add", 3)], 3),
        
        # Add then remove same player
        ([("add", 1), ("remove", 1)], 0),
        
        # Add multiple, remove one
        ([("add", 1), ("add", 2), ("add", 3), ("remove", 2)], 2),
        
        # Remove non-existent player
        ([("add", 1), ("remove", 999)], 1),
        
        # Duplicate adds (should not duplicate in queue)
        ([("add", 1), ("add", 1), ("add", 1)], 1),  # Depends on implementation
        
        # Concurrent scenario: 100 adds, 50 removes, 50 expected
        ([(f"add", i) for i in range(100)] + [(f"remove", i) for i in range(50)], 50),
    ]
    
    for operations, expected_size in test_cases:
        matchmaker.players = []  # Reset
        
        # Execute operations
        for op, player_id in operations:
            if op == "add":
                player = create_mock_player(discord_id=player_id)
                await matchmaker.add_player(player)
            elif op == "remove":
                await matchmaker.remove_player(player_id)
        
        actual_size = len(matchmaker.players)
        assert actual_size == expected_size, \
            f"Queue size after {operations}: expected {expected_size}, got {actual_size}"
```

---

## 3. Command Guard Service

**File**: `src/backend/services/command_guard_service.py`  
**Criticality**: HIGH - Controls access to all commands  
**Pattern**: Guard clauses with cached state checks

### Authorization State Machine

```
New User → ensure_player_record() → Player Record Exists
   ↓
require_tos_accepted() → TOS Accepted
   ↓
require_setup_completed() → Setup Complete
   ↓
require_account_activated() → Activation Code Set
   ↓
FULL ACCESS (can queue, view profile, etc.)
```

### Critical Invariants

1. **State Progression**: Cannot skip states (e.g., activate without TOS)
2. **Cache Consistency**: Cache TTL = 5 minutes, invalidated on updates
3. **Error Hierarchy**: More specific errors propagate (AccountNotActivated > TermsNotAccepted)
4. **DM Enforcement**: All protected commands must be in DM channel
5. **Player Record Creation**: Always succeeds (creates if not exists)
6. **Cache Hit Rate**: Should be >85% during active sessions

### Test Case Structure

```python
def test_authorization_state_transitions(self, guard_service):
    """Test that authorization states progress correctly"""
    
    test_cases = [
        # (player_state, check_method, should_pass, expected_exception)
        
        # New player - no states set
        ({"accepted_tos": False, "completed_setup": False, "activation_code": None},
         "require_tos_accepted", False, TermsNotAcceptedError),
        
        # TOS accepted only
        ({"accepted_tos": True, "completed_setup": False, "activation_code": None},
         "require_tos_accepted", True, None),
        ({"accepted_tos": True, "completed_setup": False, "activation_code": None},
         "require_setup_completed", False, SetupIncompleteError),
        
        # TOS + Setup complete
        ({"accepted_tos": True, "completed_setup": True, "activation_code": None},
         "require_setup_completed", True, None),
        ({"accepted_tos": True, "completed_setup": True, "activation_code": None},
         "require_account_activated", False, AccountNotActivatedError),
        
        # Fully activated
        ({"accepted_tos": True, "completed_setup": True, "activation_code": "ABC123"},
         "require_queue_access", True, None),
        
        # Invalid state: activation without TOS (should still fail TOS check if tested)
        ({"accepted_tos": False, "completed_setup": True, "activation_code": "ABC123"},
         "require_account_activated", False, TermsNotAcceptedError),
        
        # Invalid state: activation without setup
        ({"accepted_tos": True, "completed_setup": False, "activation_code": "ABC123"},
         "require_account_activated", False, SetupIncompleteError),
    ]
    
    for player_state, check_method, should_pass, expected_exception in test_cases:
        mock_player = create_mock_player(**player_state)
        check_func = getattr(guard_service, check_method)
        
        if should_pass:
            # Should not raise
            try:
                check_func(mock_player)
            except Exception as e:
                pytest.fail(f"Expected pass for {check_method} with {player_state}, but got {e}")
        else:
            # Should raise specific exception
            with pytest.raises(expected_exception):
                check_func(mock_player)
```

### Test Cases by Category

#### 1. Cache Performance

```python
def test_cache_hit_rate_performance(self, guard_service):
    """Test that cache provides expected performance improvement"""
    
    test_cases = [
        # (cache_scenario, expected_hit_rate_pct, max_latency_ms)
        
        # Same player checked 10 times in a row
        ("repeated_single_player", 90, 10),  # First miss, then 9 hits = 90%
        
        # 5 players checked twice each
        ("repeated_multiple_players", 50, 10),  # 5 misses + 5 hits = 50%
        
        # Cache invalidation scenario
        ("invalidation_test", 0, 200),  # All cache misses after invalidation
        
        # TTL expiration (5 minute window)
        ("ttl_expiration", 0, 200),  # All misses after 5 minutes
    ]
    
    for scenario, expected_hit_rate, max_latency_ms in test_cases:
        player_cache.clear()  # Reset cache
        
        if scenario == "repeated_single_player":
            discord_uid = 123456
            username = "TestPlayer"
            
            # First call - cache miss
            start = time.time()
            guard_service.ensure_player_record(discord_uid, username)
            first_call_ms = (time.time() - start) * 1000
            
            # Subsequent calls - cache hits
            total_time = 0
            for _ in range(9):
                start = time.time()
                guard_service.ensure_player_record(discord_uid, username)
                total_time += (time.time() - start) * 1000
            
            avg_cached_latency = total_time / 9
            
            # Verify cache hit
            stats = player_cache.get_stats()
            hit_rate = stats["hit_rate_pct"]
            
            assert hit_rate >= expected_hit_rate, \
                f"{scenario}: Expected hit rate >={expected_hit_rate}%, got {hit_rate}%"
            assert avg_cached_latency < max_latency_ms, \
                f"{scenario}: Expected avg latency <{max_latency_ms}ms, got {avg_cached_latency:.2f}ms"
```

#### 2. DM Enforcement

```python
def test_dm_only_enforcement(self, guard_service):
    """Test that DM-only commands are properly enforced"""
    
    test_cases = [
        # (channel_type, should_pass, description)
        ("dm", True, "DM channel should pass"),
        ("text", False, "Text channel should fail"),
        ("voice", False, "Voice channel should fail"),
        ("group_dm", False, "Group DM should fail"),
        ("thread", False, "Thread should fail"),
    ]
    
    for channel_type, should_pass, description in test_cases:
        interaction = create_mock_interaction(channel_type=channel_type)
        
        if should_pass:
            try:
                guard_service.require_dm(interaction)
            except DMOnlyError:
                pytest.fail(f"{description}: Should not raise DMOnlyError")
        else:
            with pytest.raises(DMOnlyError):
                guard_service.require_dm(interaction)
```

#### 3. Cache Invalidation

```python
def test_cache_invalidation_on_updates(self, guard_service):
    """Test that cache is properly invalidated when player data changes"""
    
    test_cases = [
        # (update_method, player_before, update_args, should_invalidate)
        
        # Country update should invalidate
        ("update_country", {"discord_uid": 123, "country": "US"}, 
         {"new_country": "KR"}, True),
        
        # TOS acceptance should invalidate
        ("accept_terms_of_service", {"discord_uid": 123, "accepted_tos": False},
         {}, True),
        
        # Setup completion should invalidate
        ("complete_setup", {"discord_uid": 123, "completed_setup": False},
         {"player_name": "NewName", "country": "US", "battle_tag": "Test#1234", "alt_ids": []}, True),
        
        # Activation should invalidate
        ("submit_activation_code", {"discord_uid": 123, "activation_code": None},
         {"code": "ABC123"}, True),
    ]
    
    for update_method, player_before, update_args, should_invalidate in test_cases:
        # Prime cache with initial player state
        player_cache.set(player_before["discord_uid"], player_before)
        
        # Verify cache hit
        cached = player_cache.get(player_before["discord_uid"])
        assert cached is not None, "Cache should be primed"
        
        # Perform update
        update_func = getattr(user_info_service, update_method)
        update_func(player_before["discord_uid"], **update_args)
        
        # Check cache
        cached_after = player_cache.get(player_before["discord_uid"])
        
        if should_invalidate:
            assert cached_after is None, \
                f"{update_method} should invalidate cache, but it still exists"
        else:
            assert cached_after is not None, \
                f"{update_method} should not invalidate cache, but it was cleared"
```

---

## 4. Replay Service

**File**: `src/backend/services/replay_service.py`  
**Criticality**: HIGH - Validates match results, prevents cheating  
**Algorithm**: SC2Reader parsing + BLAKE2b hashing

### Parsing Requirements

```
Valid SC2Replay File Requirements:
1. Exactly 2 players (no observers counted as players)
2. Valid race for each player (BW or SC2 variant)
3. Parseable with sc2reader level 4
4. Duration > 0 seconds
5. Winner determinable (or draw)
6. Toon handles extractable
7. File size < 10MB (practical limit)
8. BLAKE2b hash collision rate < 2^-80
```

### Critical Invariants

1. **Hash Uniqueness**: BLAKE2b 80-bit digest provides ~2^-80 collision probability
2. **Idempotency**: Parsing same file always produces same hash
3. **Race Normalization**: "Terran" → "sc2_terran", "BW Terran" → "bw_terran"
4. **Winner Extraction**: Falls back to "was defeated!" message if winner field empty
5. **Duration Calculation**: Adjusted for game speed (Faster = 1.4x Normal)
6. **Multiprocessing Safety**: Parsing must be thread-safe in worker process
7. **Error Propagation**: Parse errors return dict with 'error' key, not exceptions

### Test Case Structure

```python
def test_replay_parsing_valid_files(self, replay_service):
    """Test parsing of valid replay files"""
    
    test_cases = [
        # (replay_filename, expected_player_count, expected_races, expected_winner, expected_duration_min, expected_duration_max)
        
        # Standard 1v1 matches
        ("1523.SC2Replay", 2, ["sc2_terran", "sc2_protoss"], 1, 300, 600),
        ("DarkReBellionIsles.SC2Replay", 2, ["bw_zerg", "bw_terran"], 2, 600, 1200),
        ("threepointPSIArcGoldenWall.SC2Replay", 2, ["sc2_zerg", "sc2_zerg"], 0, 120, 300),
        
        # Edge cases
        ("very_short_game.SC2Replay", 2, ["sc2_terran", "sc2_terran"], 1, 0, 120),  # Instant leave
        ("very_long_game.SC2Replay", 2, ["bw_protoss", "bw_protoss"], 0, 3600, 7200),  # 1-2 hour game
        
        # All race combinations
        ("tvz.SC2Replay", 2, ["sc2_terran", "sc2_zerg"], 1, 300, 900),
        ("pvt.SC2Replay", 2, ["sc2_protoss", "sc2_terran"], 2, 300, 900),
        ("zvp.SC2Replay", 2, ["sc2_zerg", "sc2_protoss"], 1, 300, 900),
        ("bw_tvt.SC2Replay", 2, ["bw_terran", "bw_terran"], 0, 300, 900),
    ]
    
    for filename, expected_players, expected_races, expected_winner, min_duration, max_duration in test_cases:
        replay_path = f"tests/test_data/test_replay_files/{filename}"
        
        with open(replay_path, 'rb') as f:
            replay_bytes = f.read()
        
        result = parse_replay_data_blocking(replay_bytes)
        
        # Should not have error
        assert result.get("error") is None, \
            f"{filename}: Parse failed with error: {result.get('error')}"
        
        # Verify player count
        assert result["player_count"] == expected_players, \
            f"{filename}: Expected {expected_players} players, got {result['player_count']}"
        
        # Verify races
        actual_races = [result["player_1_race"], result["player_2_race"]]
        assert actual_races == expected_races, \
            f"{filename}: Expected races {expected_races}, got {actual_races}"
        
        # Verify winner
        assert result["result"] == expected_winner, \
            f"{filename}: Expected winner {expected_winner}, got {result['result']}"
        
        # Verify duration in range
        duration = result["duration"]
        assert min_duration <= duration <= max_duration, \
            f"{filename}: Duration {duration}s outside range [{min_duration}, {max_duration}]"
        
        # Verify hash exists and is correct length
        replay_hash = result["replay_hash"]
        assert replay_hash is not None, f"{filename}: Hash is None"
        assert len(replay_hash) == 20, f"{filename}: Hash length should be 20 hex chars (80 bits), got {len(replay_hash)}"  # 10 bytes = 20 hex chars
```

### Test Cases by Category

#### 1. Invalid Replay Files

```python
def test_replay_parsing_invalid_files(self, replay_service):
    """Test that invalid replay files are rejected with appropriate errors"""
    
    test_cases = [
        # (replay_content, expected_error_substring)
        
        # Corrupted file
        (b"CORRUPTED_DATA_NOT_A_REPLAY", "parse"),
        
        # Empty file
        (b"", "empty"),
        
        # Wrong player count
        ("replay_with_3_players.SC2Replay", "2 players"),
        ("replay_with_1_player.SC2Replay", "2 players"),
        
        # Invalid race
        ("replay_with_invalid_race.SC2Replay", "race"),
        
        # No duration extractable
        ("replay_no_duration.SC2Replay", "duration"),
    ]
    
    for replay_input, expected_error in test_cases:
        if isinstance(replay_input, bytes):
            replay_bytes = replay_input
        else:
            replay_path = f"tests/test_data/test_replay_files/{replay_input}"
            with open(replay_path, 'rb') as f:
                replay_bytes = f.read()
        
        result = parse_replay_data_blocking(replay_bytes)
        
        # Should have error
        assert result.get("error") is not None, \
            f"{replay_input}: Expected error, but parse succeeded"
        assert expected_error.lower() in result["error"].lower(), \
            f"{replay_input}: Expected error containing '{expected_error}', got '{result['error']}'"
```

#### 2. Hash Consistency

```python
def test_replay_hash_consistency(self, replay_service):
    """Test that replay hashes are consistent and unique"""
    
    test_cases = [
        # (replay_filename, should_be_unique_from_previous)
        ("1523.SC2Replay", True),
        ("DarkReBellionIsles.SC2Replay", True),
        ("threepointPSIArcGoldenWall.SC2Replay", True),
        
        # Same file parsed twice - should have identical hash
        ("1523.SC2Replay", False),  # Second time, should match first
    ]
    
    hashes = {}
    previous_hash = None
    
    for filename, should_be_unique in test_cases:
        replay_path = f"tests/test_data/test_replay_files/{filename}"
        
        with open(replay_path, 'rb') as f:
            replay_bytes = f.read()
        
        result = parse_replay_data_blocking(replay_bytes)
        current_hash = result["replay_hash"]
        
        if should_be_unique:
            # Should not match any previous hash
            assert current_hash not in hashes.values(), \
                f"{filename}: Hash {current_hash} collides with previous file"
            hashes[filename] = current_hash
            previous_hash = current_hash
        else:
            # Should match previous hash (same file)
            assert current_hash == previous_hash, \
                f"{filename}: Hash inconsistent on re-parse: {current_hash} vs {previous_hash}"
```

#### 3. Race Normalization

```python
def test_race_normalization(self, replay_service):
    """Test that races are correctly normalized to database format"""
    
    test_cases = [
        # (sc2reader_race_string, expected_normalized_race)
        ("Terran", "sc2_terran"),
        ("Protoss", "sc2_protoss"),
        ("Zerg", "sc2_zerg"),
        ("BW Terran", "bw_terran"),
        ("BW Protoss", "bw_protoss"),
        ("BW Zerg", "bw_zerg"),
        
        # Edge cases
        ("terran", "sc2_terran"),  # Lowercase (if handled)
        ("TERRAN", "sc2_terran"),  # Uppercase (if handled)
        ("Random", "Random"),  # Should pass through if not in map
    ]
    
    for raw_race, expected_normalized in test_cases:
        normalized = replay_service._normalize_race(raw_race)
        assert normalized == expected_normalized, \
            f"Race normalization '{raw_race}': expected '{expected_normalized}', got '{normalized}'"
```

#### 4. Multiprocessing Safety

```python
def test_multiprocessing_parsing(self, bot_with_process_pool):
    """Test that replay parsing works correctly in multiprocessing environment"""
    
    test_cases = [
        # (replay_filename, concurrent_parses_count)
        ("1523.SC2Replay", 1),
        ("DarkReBellionIsles.SC2Replay", 5),
        ("threepointPSIArcGoldenWall.SC2Replay", 10),
    ]
    
    for filename, concurrent_count in test_cases:
        replay_path = f"tests/test_data/test_replay_files/{filename}"
        
        with open(replay_path, 'rb') as f:
            replay_bytes = f.read()
        
        # Submit multiple parse tasks to process pool
        loop = asyncio.get_event_loop()
        tasks = []
        
        for _ in range(concurrent_count):
            task = loop.run_in_executor(
                bot_with_process_pool.process_pool,
                parse_replay_data_blocking,
                replay_bytes
            )
            tasks.append(task)
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks)
        
        # All should succeed with same hash
        first_hash = results[0]["replay_hash"]
        for i, result in enumerate(results):
            assert result.get("error") is None, \
                f"{filename} parse {i+1}/{concurrent_count}: Failed with {result.get('error')}"
            assert result["replay_hash"] == first_hash, \
                f"{filename} parse {i+1}/{concurrent_count}: Hash mismatch {result['replay_hash']} vs {first_hash}"
```

---

## 5. Match Completion Service

**File**: `src/backend/services/match_completion_service.py`  
**Criticality**: HIGH - Ensures match results are finalized correctly  
**Pattern**: Async state machine with monitoring tasks

### Match State Transitions

```
Match Created (match_result = NULL, p1_report = NULL, p2_report = NULL)
   ↓
Replay Uploaded (replay_uploaded = "Yes")
   ↓
P1 Reports (p1_report = 0/1/2/-3)
   ↓
P2 Reports (p2_report = 0/1/2/-3)
   ↓
State Resolution:
   - Both Agree (p1_report == p2_report) → match_result = p1_report, MMR updated
   - Conflict (p1_report != p2_report) → match_result = -2 (conflict)
   - Abort (either report = -3) → match_result = -1 (aborted)
```

### Critical Invariants

1. **Idempotency**: Processing same match twice has no effect
2. **Atomicity**: MMR updates are transactional (both players or neither)
3. **Notification Guarantee**: Callbacks fired exactly once per match
4. **Monitor Cleanup**: Monitoring tasks stopped after completion
5. **Lock Per Match**: Concurrent processing of same match is serialized
6. **Processed Set**: Match IDs marked as processed prevent re-processing
7. **Waiter Notification**: All waiting tasks notified on completion

### Test Case Structure

```python
async def test_match_state_transitions(self, match_completion_service):
    """Test that match states transition correctly"""
    
    test_cases = [
        # (initial_state, p1_report, p2_report, expected_final_state, expected_mmr_updated)
        
        # Agreement scenarios
        ({"match_result": None, "p1_report": None, "p2_report": None},
         1, 1, {"match_result": 1}, True),  # Both report P1 wins
        
        ({"match_result": None, "p1_report": None, "p2_report": None},
         2, 2, {"match_result": 2}, True),  # Both report P2 wins
        
        ({"match_result": None, "p1_report": None, "p2_report": None},
         0, 0, {"match_result": 0}, True),  # Both report draw
        
        # Conflict scenarios
        ({"match_result": None, "p1_report": None, "p2_report": None},
         1, 2, {"match_result": -2}, False),  # P1 says P1 wins, P2 says P2 wins
        
        ({"match_result": None, "p1_report": None, "p2_report": None},
         0, 1, {"match_result": -2}, False),  # P1 says draw, P2 says P1 wins
        
        # Abort scenarios
        ({"match_result": None, "p1_report": None, "p2_report": None},
         -3, None, {"match_result": -1}, False),  # P1 aborts, P2 hasn't reported yet
        
        ({"match_result": None, "p1_report": None, "p2_report": None},
         None, -3, {"match_result": -1}, False),  # P2 aborts
        
        ({"match_result": None, "p1_report": None, "p2_report": None},
         -3, -3, {"match_result": -1}, False),  # Both abort
        
        # Sequential reporting (P1 first)
        ({"match_result": None, "p1_report": 1, "p2_report": None},
         None, 1, {"match_result": 1}, True),  # P1 already reported, P2 agrees
        
        # Sequential reporting (P2 first)
        ({"match_result": None, "p1_report": None, "p2_report": 2},
         2, None, {"match_result": 2}, True),  # P2 already reported, P1 agrees
    ]
    
    for initial_state, p1_report, p2_report, expected_final, mmr_should_update in test_cases:
        # Create match in database
        match_id = create_test_match(**initial_state)
        
        # Submit reports
        if p1_report is not None and initial_state["p1_report"] is None:
            matchmaker.record_match_result(match_id, player_1_discord_id, p1_report)
        
        if p2_report is not None and initial_state["p2_report"] is None:
            matchmaker.record_match_result(match_id, player_2_discord_id, p2_report)
        
        # Wait for completion
        await match_completion_service.check_match_completion(match_id)
        
        # Verify final state
        match_data = db_reader.get_match_1v1(match_id)
        assert match_data["match_result"] == expected_final["match_result"], \
            f"Match {match_id} state: expected {expected_final['match_result']}, got {match_data['match_result']}"
        
        # Verify MMR updated
        if mmr_should_update:
            p1_mmr_after = db_reader.get_player_mmr_1v1(player_1_discord_id, race)
            p2_mmr_after = db_reader.get_player_mmr_1v1(player_2_discord_id, race)
            
            # MMR should have changed from initial values
            assert p1_mmr_after["mmr"] != initial_p1_mmr or p2_mmr_after["mmr"] != initial_p2_mmr, \
                f"Match {match_id}: MMR should have updated but did not"
```

### Test Cases by Category

#### 1. Idempotency

```python
async def test_match_completion_idempotency(self, match_completion_service):
    """Test that processing the same match multiple times is safe"""
    
    test_cases = [
        # (match_id, process_count, expected_callback_count)
        (1, 1, 1),   # Single processing
        (2, 2, 1),   # Double processing
        (3, 5, 1),   # Multiple processing
        (4, 10, 1),  # Concurrent processing
    ]
    
    for match_id, process_count, expected_callbacks in test_cases:
        # Create completed match
        setup_completed_match(match_id, p1_report=1, p2_report=1)
        
        # Track callback invocations
        callback_count = 0
        def callback(status, data):
            nonlocal callback_count
            callback_count += 1
        
        # Start monitoring
        match_completion_service.start_monitoring_match(match_id, callback)
        
        # Process multiple times
        tasks = []
        for _ in range(process_count):
            task = match_completion_service.check_match_completion(match_id)
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # Wait a bit for callbacks
        await asyncio.sleep(0.5)
        
        # Verify callback count
        assert callback_count == expected_callbacks, \
            f"Match {match_id} processed {process_count} times: expected {expected_callbacks} callbacks, got {callback_count}"
```

#### 2. Concurrent Match Processing

```python
async def test_concurrent_match_processing(self, match_completion_service):
    """Test that multiple matches can be processed concurrently"""
    
    test_cases = [
        # (match_count, expected_all_complete)
        (1, True),
        (5, True),
        (10, True),
        (50, True),
    ]
    
    for match_count, expected_complete in test_cases:
        # Create multiple matches
        match_ids = []
        for i in range(match_count):
            match_id = create_test_match(
                p1_report=random.choice([0, 1, 2]),
                p2_report=random.choice([0, 1, 2])
            )
            match_ids.append(match_id)
        
        # Process all concurrently
        tasks = [
            match_completion_service.check_match_completion(match_id)
            for match_id in match_ids
        ]
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start_time
        
        # Verify all completed
        completed_count = sum(1 for r in results if r)
        
        if expected_complete:
            assert completed_count == match_count, \
                f"Expected {match_count} matches to complete, got {completed_count}"
        
        # Verify processing time is reasonable (should be concurrent, not sequential)
        # If sequential: ~50ms per match × N matches
        # If concurrent: ~50ms total (with some overhead)
        max_expected_time = 0.5 + (match_count * 0.01)  # 500ms + 10ms per match overhead
        assert elapsed < max_expected_time, \
            f"Processing {match_count} matches took {elapsed:.2f}s, expected <{max_expected_time:.2f}s (indicates sequential processing)"
```

#### 3. Lock Contention

```python
async def test_match_lock_contention(self, match_completion_service):
    """Test that per-match locks prevent race conditions"""
    
    test_cases = [
        # (match_id, concurrent_checks, expected_callback_count)
        (1, 10, 1),  # 10 concurrent checks on same match
        (2, 50, 1),  # 50 concurrent checks on same match
        (3, 100, 1), # 100 concurrent checks on same match
    ]
    
    for match_id, concurrent_count, expected_callbacks in test_cases:
        # Create match ready for completion
        setup_match_ready_for_completion(match_id, p1_report=1, p2_report=1)
        
        # Track callbacks
        callback_count = 0
        callback_lock = asyncio.Lock()
        
        async def callback(status, data):
            nonlocal callback_count
            async with callback_lock:
                callback_count += 1
        
        # Start monitoring
        match_completion_service.start_monitoring_match(match_id, callback)
        
        # Launch many concurrent checks
        tasks = [
            match_completion_service.check_match_completion(match_id)
            for _ in range(concurrent_count)
        ]
        
        await asyncio.gather(*tasks)
        await asyncio.sleep(0.5)  # Wait for callbacks
        
        # Verify only one callback fired (due to locking)
        assert callback_count == expected_callbacks, \
            f"Match {match_id} with {concurrent_count} concurrent checks: expected {expected_callbacks} callback, got {callback_count}"
```

---

## Implementation Guidelines

### Running the Tests

```bash
# Run all critical service tests
pytest tests/backend/services/test_mmr_service.py -v
pytest tests/backend/services/test_matchmaking_service.py -v
pytest tests/backend/services/test_command_guard_service.py -v
pytest tests/backend/services/test_replay_service.py -v
pytest tests/backend/services/test_match_completion_service.py -v

# Run with coverage
pytest tests/backend/services/ --cov=src.backend.services --cov-report=html

# Run specific test category
pytest tests/backend/services/test_mmr_service.py::TestMMRService::test_calculate_expected_score -v
```

### Test Data Requirements

```
tests/test_data/
├── test_replay_files/
│   ├── 1523.SC2Replay (valid SC2 TvP)
│   ├── DarkReBellionIsles.SC2Replay (valid BW ZvT)
│   ├── threepointPSIArcGoldenWall.SC2Replay (valid SC2 ZvZ draw)
│   ├── invalid_player_count.SC2Replay (3 players)
│   ├── corrupted.SC2Replay (malformed data)
│   └── ... (additional edge cases)
└── mock_database.db (SQLite for testing)
```

### Performance Benchmarks

Expected test execution times (on CI/CD):

```
MMR Service:              <5 seconds   (100+ test cases, pure math)
Matchmaking Service:      <30 seconds  (includes async operations)
Command Guard Service:    <10 seconds  (includes cache tests)
Replay Service:           <60 seconds  (includes file I/O)
Match Completion Service: <45 seconds  (includes async monitoring)

Total:                    <150 seconds (2.5 minutes for full suite)
```

---

## Coverage Goals

- **Line Coverage**: >90% for all critical services
- **Branch Coverage**: >85% (test all if/else paths)
- **Integration Coverage**: >75% (test service interactions)
- **Edge Case Coverage**: 100% (test all boundary conditions)

---

**Document Version**: 1.0  
**Last Updated**: October 20, 2025  
**Next Review**: After test implementation complete

