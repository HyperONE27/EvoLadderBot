"""
Deep Matchmaking Algorithm Analysis

This script provides a more detailed analysis including:
- Pressure threshold behavior
- Race imbalance effects
- MMR distribution impacts
- Time-to-match distributions
"""

import random
import statistics
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple
from collections import defaultdict

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from src.backend.core import config


@dataclass
class SimulatedPlayer:
    """Represents a player in the simulation"""
    player_id: int
    bw_mmr: int
    sc2_mmr: int
    has_bw: bool
    has_sc2: bool
    preferred_race_type: str
    join_time: float = 0.0
    wait_cycles: int = 0


@dataclass
class DetailedMatchResult:
    """Extended match result with more metrics"""
    player1_id: int
    player2_id: int
    player1_mmr: int
    player2_mmr: int
    mmr_difference: int
    wait_time_seconds: float
    wait_cycles: int
    wave_found: int
    queue_pressure_at_match: float
    pressure_category: str
    mmr_window_base: int
    mmr_window_growth: int


class DetailedMatchmakingSimulator:
    """Enhanced simulator with detailed tracking"""
    
    def __init__(self):
        self.MATCH_INTERVAL_SECONDS = config.MM_MATCH_INTERVAL_SECONDS
        self.HIGH_PRESSURE_THRESHOLD = config.MM_HIGH_PRESSURE_THRESHOLD
        self.MODERATE_PRESSURE_THRESHOLD = config.MM_MODERATE_PRESSURE_THRESHOLD
        self.HIGH_PRESSURE_PARAMS = config.MM_HIGH_PRESSURE_PARAMS
        self.MODERATE_PRESSURE_PARAMS = config.MM_MODERATE_PRESSURE_PARAMS
        self.LOW_PRESSURE_PARAMS = config.MM_LOW_PRESSURE_PARAMS
        self.DEFAULT_PARAMS = config.MM_DEFAULT_PARAMS
        self.MMR_EXPANSION_STEP = config.MM_MMR_EXPANSION_STEP
        self.POPULATION_THRESHOLD_LOW = config.MM_POPULATION_THRESHOLD_LOW
        self.POPULATION_THRESHOLD_MID = config.MM_POPULATION_THRESHOLD_MID
        self.PRESSURE_SCALE_LOW_POP = config.MM_PRESSURE_SCALE_LOW_POP
        self.PRESSURE_SCALE_MID_POP = config.MM_PRESSURE_SCALE_MID_POP
        self.PRESSURE_SCALE_HIGH_POP = config.MM_PRESSURE_SCALE_HIGH_POP
        
    def _calculate_queue_pressure(self, queue_size: int, effective_pop: int) -> float:
        """Calculate the scale-adjusted queue pressure ratio"""
        if effective_pop <= 0:
            return 0.0
        
        if effective_pop <= self.POPULATION_THRESHOLD_LOW:
            scale = self.PRESSURE_SCALE_LOW_POP
        elif effective_pop <= self.POPULATION_THRESHOLD_MID:
            scale = self.PRESSURE_SCALE_MID_POP
        else:
            scale = self.PRESSURE_SCALE_HIGH_POP
        
        return min(1.0, (scale * queue_size) / effective_pop)
    
    def _get_pressure_params(self, queue_size: int, effective_pop: int) -> Tuple[Tuple[int, int], str]:
        """Get pressure parameters and category"""
        if effective_pop == 0:
            return self.DEFAULT_PARAMS, "DEFAULT"
        
        pressure_ratio = self._calculate_queue_pressure(queue_size, effective_pop)
        
        if pressure_ratio >= self.HIGH_PRESSURE_THRESHOLD:
            return self.HIGH_PRESSURE_PARAMS, "HIGH"
        elif pressure_ratio >= self.MODERATE_PRESSURE_THRESHOLD:
            return self.MODERATE_PRESSURE_PARAMS, "MODERATE"
        else:
            return self.LOW_PRESSURE_PARAMS, "LOW"
    
    def _get_max_diff(self, wait_cycles: int, queue_size: int, effective_pop: int) -> int:
        """Calculate max MMR difference"""
        params, _ = self._get_pressure_params(queue_size, effective_pop)
        base, growth = params
        return base + (wait_cycles // self.MMR_EXPANSION_STEP) * growth
    
    def _categorize_players(self, players: List[SimulatedPlayer]) -> Tuple[List, List, List]:
        """Categorize players into BW-only, SC2-only, and both lists"""
        bw_only = [p for p in players if p.has_bw and not p.has_sc2]
        sc2_only = [p for p in players if p.has_sc2 and not p.has_bw]
        both_races = [p for p in players if p.has_bw and p.has_sc2]
        
        bw_only.sort(key=lambda p: p.bw_mmr, reverse=True)
        sc2_only.sort(key=lambda p: p.sc2_mmr, reverse=True)
        both_races.sort(key=lambda p: max(p.bw_mmr, p.sc2_mmr), reverse=True)
        
        return bw_only, sc2_only, both_races
    
    def _equalize_lists(self, list_x: List, list_y: List, list_z: List) -> Tuple[List, List, List]:
        """Equalize the sizes of list_x and list_y"""
        x_copy = list_x.copy()
        y_copy = list_y.copy()
        z_copy = list_z.copy()
        
        if not x_copy and not y_copy and z_copy:
            for i, player in enumerate(z_copy):
                if i % 2 == 0:
                    x_copy.append(player)
                else:
                    y_copy.append(player)
            z_copy = []
            return x_copy, y_copy, z_copy
        
        while z_copy:
            if len(x_copy) < len(y_copy):
                x_copy.append(z_copy.pop(0))
            elif len(x_copy) > len(y_copy):
                y_copy.append(z_copy.pop(0))
            else:
                if z_copy:
                    x_copy.append(z_copy.pop(0))
                if z_copy:
                    y_copy.append(z_copy.pop(0))
        
        return x_copy, y_copy, z_copy
    
    def simulate_wave_detailed(self, queue: List[SimulatedPlayer], effective_population: int, 
                              wave_number: int) -> Tuple[List[DetailedMatchResult], List[SimulatedPlayer]]:
        """Simulate a wave with detailed tracking"""
        for player in queue:
            player.wait_cycles += 1
        
        queue_size = len(queue)
        pressure = self._calculate_queue_pressure(queue_size, effective_population)
        params, pressure_cat = self._get_pressure_params(queue_size, effective_population)
        
        bw_list, sc2_list, both_races = self._categorize_players(queue)
        bw_list, sc2_list, _ = self._equalize_lists(bw_list, sc2_list, both_races)
        
        matches = []
        
        if len(bw_list) > 0 and len(sc2_list) > 0:
            if len(bw_list) <= len(sc2_list):
                lead_side, follow_side = bw_list, sc2_list
                is_bw_match = True
            else:
                lead_side, follow_side = sc2_list, bw_list
                is_bw_match = False
            
            matches = self._find_matches_detailed(
                lead_side, follow_side, is_bw_match, 
                queue_size, effective_population, wave_number, pressure, pressure_cat, params
            )
        
        matched_ids = {m.player1_id for m in matches} | {m.player2_id for m in matches}
        remaining_queue = [p for p in queue if p.player_id not in matched_ids]
        
        return matches, remaining_queue
    
    def _find_matches_detailed(self, lead_side: List, follow_side: List, is_bw_match: bool,
                              queue_size: int, effective_pop: int, wave_number: int,
                              pressure: float, pressure_cat: str, 
                              params: Tuple[int, int]) -> List[DetailedMatchResult]:
        """Find matches with detailed tracking"""
        matches = []
        used_lead = set()
        used_follow = set()
        
        if not lead_side:
            return matches
        
        sorted_lead = sorted(lead_side, key=lambda p: p.wait_cycles, reverse=True)
        
        for lead_player in sorted_lead:
            if lead_player.player_id in used_lead:
                continue
            
            lead_mmr = lead_player.bw_mmr if is_bw_match else lead_player.sc2_mmr
            max_diff = self._get_max_diff(lead_player.wait_cycles, queue_size, effective_pop)
            
            best_match = None
            best_diff = float('inf')
            
            for follow_player in follow_side:
                if follow_player.player_id in used_follow:
                    continue
                
                follow_mmr = follow_player.sc2_mmr if is_bw_match else follow_player.bw_mmr
                mmr_diff = abs(lead_mmr - follow_mmr)
                
                if mmr_diff <= max_diff and mmr_diff < best_diff:
                    best_match = follow_player
                    best_diff = mmr_diff
            
            if best_match:
                p1_mmr = lead_mmr
                p2_mmr = best_match.sc2_mmr if is_bw_match else best_match.bw_mmr
                wait_time = (lead_player.wait_cycles + best_match.wait_cycles) / 2 * self.MATCH_INTERVAL_SECONDS
                
                matches.append(DetailedMatchResult(
                    player1_id=lead_player.player_id,
                    player2_id=best_match.player_id,
                    player1_mmr=p1_mmr,
                    player2_mmr=p2_mmr,
                    mmr_difference=abs(p1_mmr - p2_mmr),
                    wait_time_seconds=wait_time,
                    wait_cycles=max(lead_player.wait_cycles, best_match.wait_cycles),
                    wave_found=wave_number,
                    queue_pressure_at_match=pressure,
                    pressure_category=pressure_cat,
                    mmr_window_base=params[0],
                    mmr_window_growth=params[1]
                ))
                used_lead.add(lead_player.player_id)
                used_follow.add(best_match.player_id)
        
        return matches


def generate_players(total: int, race_distribution: Dict[str, float], 
                    mmr_distribution: str = 'normal') -> List[SimulatedPlayer]:
    """Generate players with specified race distribution"""
    players = []
    
    for i in range(total):
        race_roll = random.random()
        cumulative = 0.0
        
        for race_type, probability in race_distribution.items():
            cumulative += probability
            if race_roll < cumulative:
                if race_type == 'bw_only':
                    has_bw, has_sc2 = True, False
                elif race_type == 'sc2_only':
                    has_bw, has_sc2 = False, True
                else:
                    has_bw, has_sc2 = True, True
                break
        
        if mmr_distribution == 'normal':
            bw_mmr = int(random.gauss(1500, 300))
            sc2_mmr = int(random.gauss(1500, 300))
        elif mmr_distribution == 'bimodal':
            if random.random() < 0.6:
                bw_mmr = int(random.gauss(1400, 150))
                sc2_mmr = int(random.gauss(1400, 150))
            else:
                bw_mmr = int(random.gauss(1800, 150))
                sc2_mmr = int(random.gauss(1800, 150))
        else:
            bw_mmr = random.randint(1000, 2000)
            sc2_mmr = random.randint(1000, 2000)
        
        bw_mmr = max(800, min(2500, bw_mmr))
        sc2_mmr = max(800, min(2500, sc2_mmr))
        
        players.append(SimulatedPlayer(
            player_id=i,
            bw_mmr=bw_mmr,
            sc2_mmr=sc2_mmr,
            has_bw=has_bw,
            has_sc2=has_sc2,
            preferred_race_type=race_type
        ))
    
    return players


def run_detailed_simulation(population: int, queue_pct: float, race_dist: Dict[str, float],
                           mmr_dist: str, num_waves: int = 30) -> Dict:
    """Run detailed simulation"""
    simulator = DetailedMatchmakingSimulator()
    all_players = generate_players(population, race_dist, mmr_dist)
    
    queue_size = int(population * queue_pct)
    queue = random.sample(all_players, queue_size)
    
    for player in queue:
        player.wait_cycles = 0
        player.join_time = 0.0
    
    all_matches = []
    wave_data = []
    
    for wave in range(num_waves):
        matches, queue = simulator.simulate_wave_detailed(queue, population, wave)
        all_matches.extend(matches)
        
        queue_pressure = simulator._calculate_queue_pressure(len(queue), population)
        _, pressure_cat = simulator._get_pressure_params(len(queue), population)
        
        bw_only, sc2_only, both = simulator._categorize_players(queue)
        
        wave_data.append({
            'wave': wave,
            'matches_found': len(matches),
            'queue_size': len(queue),
            'pressure': queue_pressure,
            'pressure_category': pressure_cat,
            'bw_only': len(bw_only),
            'sc2_only': len(sc2_only),
            'both_races': len(both)
        })
    
    return {
        'all_matches': all_matches,
        'wave_data': wave_data,
        'final_queue_size': len(queue),
        'initial_queue_size': queue_size
    }


def analyze_pressure_sensitivity():
    """Analyze how pressure thresholds affect matchmaking"""
    print("=" * 80)
    print("PRESSURE SENSITIVITY ANALYSIS")
    print("=" * 80)
    
    # Test different population:queue ratios to trigger different pressure levels
    test_cases = [
        # Format: (population, queue_size, expected_pressure)
        (10, 2, "Testing small pop, 20% queue"),
        (10, 5, "Testing small pop, 50% queue"),
        (10, 8, "Testing small pop, 80% queue"),
        (30, 3, "Testing mid pop, 10% queue"),
        (30, 10, "Testing mid pop, 33% queue"),
        (30, 20, "Testing mid pop, 67% queue"),
        (100, 5, "Testing large pop, 5% queue"),
        (100, 40, "Testing large pop, 40% queue"),
        (100, 80, "Testing large pop, 80% queue"),
    ]
    
    simulator = DetailedMatchmakingSimulator()
    
    for pop, queue_size, description in test_cases:
        queue_pct = queue_size / pop
        pressure = simulator._calculate_queue_pressure(queue_size, pop)
        params, pressure_cat = simulator._get_pressure_params(queue_size, pop)
        
        # Determine scale factor
        if pop <= simulator.POPULATION_THRESHOLD_LOW:
            scale = simulator.PRESSURE_SCALE_LOW_POP
            pop_cat = "LOW"
        elif pop <= simulator.POPULATION_THRESHOLD_MID:
            scale = simulator.PRESSURE_SCALE_MID_POP
            pop_cat = "MID"
        else:
            scale = simulator.PRESSURE_SCALE_HIGH_POP
            pop_cat = "HIGH"
        
        print(f"\n{description}")
        print(f"  Population: {pop} ({pop_cat} pop, scale={scale})")
        print(f"  Queue Size: {queue_size} ({queue_pct*100:.0f}%)")
        print(f"  Raw Pressure: {queue_size/pop:.3f}")
        print(f"  Scaled Pressure: {pressure:.3f}")
        print(f"  Pressure Category: {pressure_cat}")
        print(f"  MMR Window: base={params[0]}, growth={params[1]}")
        print(f"  MMR at wave 0: {params[0]}")
        print(f"  MMR at wave 5: {params[0] + 5*params[1]}")
        print(f"  MMR at wave 10: {params[0] + 10*params[1]}")


def main():
    """Run comprehensive deep analysis"""
    print("=" * 80)
    print("DETAILED MATCHMAKING ANALYSIS")
    print("=" * 80)
    print()
    
    # First, analyze pressure sensitivity
    analyze_pressure_sensitivity()
    
    print("\n" + "=" * 80)
    print("RACE IMBALANCE IMPACT ANALYSIS")
    print("=" * 80)
    
    race_distributions = [
        {'bw_only': 0.40, 'sc2_only': 0.40, 'both': 0.20},  # Balanced
        {'bw_only': 0.60, 'sc2_only': 0.20, 'both': 0.20},  # BW heavy
        {'bw_only': 0.20, 'sc2_only': 0.60, 'both': 0.20},  # SC2 heavy
        {'bw_only': 0.45, 'sc2_only': 0.45, 'both': 0.10},  # Few flex players
    ]
    
    for dist in race_distributions:
        print(f"\n--- Race Distribution: BW={dist['bw_only']:.0%}, SC2={dist['sc2_only']:.0%}, Both={dist['both']:.0%} ---")
        
        result = run_detailed_simulation(
            population=50,
            queue_pct=0.20,
            race_dist=dist,
            mmr_dist='normal',
            num_waves=30
        )
        
        matches = result['all_matches']
        
        if matches:
            print(f"  Matches Found: {len(matches)}")
            print(f"  Average Wait: {statistics.mean([m.wait_time_seconds for m in matches]):.1f}s")
            print(f"  Average MMR Diff: {statistics.mean([m.mmr_difference for m in matches]):.1f}")
            print(f"  Players Remaining: {result['final_queue_size']} / {result['initial_queue_size']}")
            
            # Analyze pressure distribution
            pressure_cats = [m.pressure_category for m in matches]
            print(f"  Pressure at matches: {dict((cat, pressure_cats.count(cat)) for cat in set(pressure_cats))}")
        else:
            print(f"  No matches found!")
            print(f"  Players Remaining: {result['final_queue_size']} / {result['initial_queue_size']}")
    
    print("\n" + "=" * 80)
    print("MMR DISTRIBUTION IMPACT ANALYSIS")
    print("=" * 80)
    
    mmr_distributions = ['normal', 'bimodal', 'uniform']
    
    for mmr_dist in mmr_distributions:
        print(f"\n--- MMR Distribution: {mmr_dist.upper()} ---")
        
        result = run_detailed_simulation(
            population=50,
            queue_pct=0.20,
            race_dist={'bw_only': 0.40, 'sc2_only': 0.40, 'both': 0.20},
            mmr_dist=mmr_dist,
            num_waves=30
        )
        
        matches = result['all_matches']
        
        if matches:
            print(f"  Matches Found: {len(matches)}")
            print(f"  Average Wait: {statistics.mean([m.wait_time_seconds for m in matches]):.1f}s")
            print(f"  Average MMR Diff: {statistics.mean([m.mmr_difference for m in matches]):.1f}")
            print(f"  Median MMR Diff: {statistics.median([m.mmr_difference for m in matches]):.1f}")
            print(f"  Max MMR Diff: {max([m.mmr_difference for m in matches])}")
    
    print("\n" + "=" * 80)
    print("TIME-TO-MATCH DISTRIBUTION")
    print("=" * 80)
    
    result = run_detailed_simulation(
        population=100,
        queue_pct=0.15,
        race_dist={'bw_only': 0.40, 'sc2_only': 0.40, 'both': 0.20},
        mmr_dist='normal',
        num_waves=30
    )
    
    matches = result['all_matches']
    
    if matches:
        # Group by wait cycles
        wait_cycle_distribution = defaultdict(int)
        for match in matches:
            wait_cycle_distribution[match.wait_cycles] += 1
        
        print(f"\nMatches by Wait Cycles:")
        for cycles in sorted(wait_cycle_distribution.keys()):
            count = wait_cycle_distribution[cycles]
            pct = count / len(matches) * 100
            print(f"  {cycles} waves ({cycles*45}s): {count} matches ({pct:.1f}%)")
        
        # MMR difference by wait time
        print(f"\nMMR Difference by Wait Cycles:")
        for cycles in sorted(wait_cycle_distribution.keys()):
            cycle_matches = [m for m in matches if m.wait_cycles == cycles]
            if cycle_matches:
                avg_mmr = statistics.mean([m.mmr_difference for m in cycle_matches])
                print(f"  {cycles} waves: {avg_mmr:.1f} MMR avg diff")
    
    print("\n" + "=" * 80)
    print("Analysis Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()

