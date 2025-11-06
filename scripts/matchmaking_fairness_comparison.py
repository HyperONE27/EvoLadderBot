"""
Matchmaking Fairness vs Performance Comparison

Compares three configurations:
1. Old Greedy (baseline)
2. Balanced Optimal (our implementation)
3. Aggressive Fairness (prioritize matches over quality)
"""

import random
import statistics
import time
from dataclasses import dataclass
from typing import List, Tuple, Dict
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
    wait_cycles: int = 0


class MatcherConfig:
    """Configuration for a matcher variant"""
    def __init__(self, name: str, high_threshold: float, mod_threshold: float,
                 high_params: Tuple[int, int], mod_params: Tuple[int, int],
                 low_params: Tuple[int, int], wait_coef: int, wait_exp: float):
        self.name = name
        self.HIGH_PRESSURE_THRESHOLD = high_threshold
        self.MODERATE_PRESSURE_THRESHOLD = mod_threshold
        self.HIGH_PRESSURE_PARAMS = high_params
        self.MODERATE_PRESSURE_PARAMS = mod_params
        self.LOW_PRESSURE_PARAMS = low_params
        self.WAIT_COEFFICIENT = wait_coef
        self.WAIT_EXPONENT = wait_exp
        self.DEFAULT_PARAMS = (75, 25)
        self.MMR_EXPANSION_STEP = 1
        self.POPULATION_THRESHOLD_LOW = 10
        self.POPULATION_THRESHOLD_MID = 25
        self.PRESSURE_SCALE_LOW_POP = 1.2
        self.PRESSURE_SCALE_MID_POP = 1.0
        self.PRESSURE_SCALE_HIGH_POP = 0.8


# Three configurations to compare
CONFIGS = {
    'old_greedy': MatcherConfig(
        name="Old Greedy",
        high_threshold=0.50,
        mod_threshold=0.30,
        high_params=(75, 25),
        mod_params=(100, 35),
        low_params=(125, 45),
        wait_coef=10,  # Old linear approach
        wait_exp=1.0
    ),
    'balanced': MatcherConfig(
        name="Balanced Optimal",
        high_threshold=0.20,
        mod_threshold=0.10,
        high_params=(75, 25),
        mod_params=(100, 35),
        low_params=(125, 45),
        wait_coef=20,
        wait_exp=1.25
    ),
    'aggressive': MatcherConfig(
        name="Aggressive Fairness",
        high_threshold=0.12,
        mod_threshold=0.05,
        high_params=(75, 25),
        mod_params=(120, 50),
        low_params=(160, 70),
        wait_coef=60,
        wait_exp=1.5
    )
}


class ConfigurableMatcher:
    """Matcher with configurable parameters"""
    
    def __init__(self, config: MatcherConfig, use_optimal: bool = True):
        self.config = config
        self.use_optimal = use_optimal
    
    def _calculate_queue_pressure(self, queue_size: int, effective_pop: int) -> float:
        if effective_pop <= 0:
            return 0.0
        
        if effective_pop <= self.config.POPULATION_THRESHOLD_LOW:
            scale = self.config.PRESSURE_SCALE_LOW_POP
        elif effective_pop <= self.config.POPULATION_THRESHOLD_MID:
            scale = self.config.PRESSURE_SCALE_MID_POP
        else:
            scale = self.config.PRESSURE_SCALE_HIGH_POP
        
        return min(1.0, (scale * queue_size) / effective_pop)
    
    def _get_max_diff(self, wait_cycles: int, queue_size: int, effective_pop: int) -> int:
        if effective_pop == 0:
            base, growth = self.config.DEFAULT_PARAMS
        else:
            pressure_ratio = self._calculate_queue_pressure(queue_size, effective_pop)
            
            if pressure_ratio >= self.config.HIGH_PRESSURE_THRESHOLD:
                base, growth = self.config.HIGH_PRESSURE_PARAMS
            elif pressure_ratio >= self.config.MODERATE_PRESSURE_THRESHOLD:
                base, growth = self.config.MODERATE_PRESSURE_PARAMS
            else:
                base, growth = self.config.LOW_PRESSURE_PARAMS
        
        return base + (wait_cycles // self.config.MMR_EXPANSION_STEP) * growth
    
    def find_matches(self, lead_side: List[SimulatedPlayer], follow_side: List[SimulatedPlayer],
                    is_bw_match: bool, queue_size: int, effective_pop: int) -> List[Tuple[SimulatedPlayer, SimulatedPlayer]]:
        """Find matches using configured algorithm"""
        if not lead_side or not follow_side:
            return []
        
        if self.use_optimal:
            # Optimal matching with candidates
            candidates = []
            for lead_player in lead_side:
                lead_mmr = lead_player.bw_mmr if is_bw_match else lead_player.sc2_mmr
                max_diff = self._get_max_diff(lead_player.wait_cycles, queue_size, effective_pop)
                
                for follow_player in follow_side:
                    follow_mmr = follow_player.sc2_mmr if is_bw_match else follow_player.bw_mmr
                    mmr_diff = abs(lead_mmr - follow_mmr)
                    
                    if mmr_diff <= max_diff:
                        wait_priority = (lead_player.wait_cycles + follow_player.wait_cycles)
                        score = (mmr_diff ** 2) - (wait_priority * self.config.WAIT_COEFFICIENT)
                        candidates.append((score, lead_player, follow_player, mmr_diff))
            
            candidates.sort(key=lambda x: x[0])
            
            matches = []
            used_lead = set()
            used_follow = set()
            
            for score, lead_player, follow_player, mmr_diff in candidates:
                if (lead_player.player_id not in used_lead and 
                    follow_player.player_id not in used_follow):
                    matches.append((lead_player, follow_player))
                    used_lead.add(lead_player.player_id)
                    used_follow.add(follow_player.player_id)
            
            return matches
        else:
            # Old greedy matching
            matches = []
            used_lead = set()
            used_follow = set()
            
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
                    matches.append((lead_player, best_match))
                    used_lead.add(lead_player.player_id)
                    used_follow.add(best_match.player_id)
            
            return matches


def generate_test_queue(queue_size: int) -> List[SimulatedPlayer]:
    """Generate a realistic queue snapshot"""
    players = []
    
    for i in range(queue_size):
        race_roll = random.random()
        if race_roll < 0.40:
            has_bw, has_sc2 = True, False
            preferred = 'bw_only'
        elif race_roll < 0.70:
            has_bw, has_sc2 = False, True
            preferred = 'sc2_only'
        else:
            has_bw, has_sc2 = True, True
            preferred = 'both'
        
        bw_mmr = int(random.gauss(1500, 300))
        sc2_mmr = int(random.gauss(1500, 300))
        
        bw_mmr = max(800, min(2500, bw_mmr))
        sc2_mmr = max(800, min(2500, sc2_mmr))
        
        wait_roll = random.random()
        if wait_roll < 0.50:
            wait_cycles = random.randint(0, 2)
        elif wait_roll < 0.80:
            wait_cycles = random.randint(3, 5)
        else:
            wait_cycles = random.randint(6, 12)
        
        players.append(SimulatedPlayer(
            player_id=i,
            bw_mmr=bw_mmr,
            sc2_mmr=sc2_mmr,
            has_bw=has_bw,
            has_sc2=has_sc2,
            preferred_race_type=preferred,
            wait_cycles=wait_cycles
        ))
    
    return players


def categorize_and_equalize(players: List[SimulatedPlayer]) -> Tuple[List, List]:
    """Simple categorization and equalization"""
    bw_only = [p for p in players if p.has_bw and not p.has_sc2]
    sc2_only = [p for p in players if p.has_sc2 and not p.has_bw]
    both_races = [p for p in players if p.has_bw and p.has_sc2]
    
    bw_list = bw_only.copy()
    sc2_list = sc2_only.copy()
    z_copy = both_races.copy()
    
    if not bw_list and not sc2_list and z_copy:
        for i, player in enumerate(z_copy):
            if i % 2 == 0:
                bw_list.append(player)
            else:
                sc2_list.append(player)
    else:
        while z_copy:
            if len(bw_list) < len(sc2_list):
                bw_list.append(z_copy.pop())
            elif len(bw_list) > len(sc2_list):
                sc2_list.append(z_copy.pop(0))
            else:
                if z_copy:
                    sc2_list.append(z_copy.pop(0))
                if z_copy:
                    bw_list.append(z_copy.pop())
    
    return bw_list, sc2_list


def compare_configurations(queue_size: int, effective_pop: int, trials: int = 100) -> Dict:
    """Compare all three configurations"""
    matchers = {
        'old_greedy': ConfigurableMatcher(CONFIGS['old_greedy'], use_optimal=False),
        'balanced': ConfigurableMatcher(CONFIGS['balanced'], use_optimal=True),
        'aggressive': ConfigurableMatcher(CONFIGS['aggressive'], use_optimal=True)
    }
    
    results = {key: {'mmr_diffs': [], 'match_counts': [], 'times': []} for key in matchers.keys()}
    
    for trial in range(trials):
        queue = generate_test_queue(queue_size)
        bw_list, sc2_list = categorize_and_equalize(queue)
        
        if not bw_list or not sc2_list:
            continue
        
        if len(bw_list) <= len(sc2_list):
            lead_side, follow_side = bw_list, sc2_list
            is_bw_match = True
        else:
            lead_side, follow_side = sc2_list, bw_list
            is_bw_match = False
        
        for key, matcher in matchers.items():
            start = time.perf_counter()
            matches = matcher.find_matches(lead_side, follow_side, is_bw_match, queue_size, effective_pop)
            results[key]['times'].append(time.perf_counter() - start)
            
            if matches:
                for p1, p2 in matches:
                    p1_mmr = p1.bw_mmr if is_bw_match else p1.sc2_mmr
                    p2_mmr = p2.sc2_mmr if is_bw_match else p2.bw_mmr
                    results[key]['mmr_diffs'].append(abs(p1_mmr - p2_mmr))
                results[key]['match_counts'].append(len(matches))
    
    return {
        key: {
            'avg_mmr': statistics.mean(data['mmr_diffs']) if data['mmr_diffs'] else 0,
            'median_mmr': statistics.median(data['mmr_diffs']) if data['mmr_diffs'] else 0,
            'avg_matches': statistics.mean(data['match_counts']) if data['match_counts'] else 0,
            'avg_time_ms': statistics.mean(data['times']) * 1000 if data['times'] else 0,
        }
        for key, data in results.items()
    }


def main():
    print("=" * 80)
    print("MATCHMAKING FAIRNESS vs PERFORMANCE COMPARISON")
    print("=" * 80)
    print()
    print("Configurations:")
    print("  1. Old Greedy: Original algorithm (baseline)")
    print("  2. Balanced Optimal: Our optimized implementation")
    print("  3. Aggressive Fairness: Prioritizes matching over quality")
    print()
    
    scenarios = [
        (5, 20, "5 in queue, 20 active (25%)"),
        (10, 20, "10 in queue, 20 active (50%)"),
        (10, 30, "10 in queue, 30 active (33%)"),
        (15, 30, "15 in queue, 30 active (50%)"),
        (20, 30, "20 in queue, 30 active (67%)"),
        (30, 50, "30 in queue, 50 active (60%)"),
    ]
    
    for queue_size, effective_pop, description in scenarios:
        print(f"\n{'=' * 80}")
        print(f"Scenario: {description}")
        print('=' * 80)
        
        result = compare_configurations(queue_size, effective_pop, trials=200)
        
        # Print results in table format
        print(f"\n{'Config':<20} {'Avg MMR Diff':<15} {'Matches/Wave':<15} {'Time (ms)':<12}")
        print("-" * 80)
        
        for key in ['old_greedy', 'balanced', 'aggressive']:
            config_name = CONFIGS[key].name
            avg_mmr = result[key]['avg_mmr']
            avg_matches = result[key]['avg_matches']
            avg_time = result[key]['avg_time_ms']
            
            print(f"{config_name:<20} {avg_mmr:<15.1f} {avg_matches:<15.2f} {avg_time:<12.3f}")
        
        # Calculate improvements relative to old greedy
        print("\n" + "Improvements vs Old Greedy:")
        for key in ['balanced', 'aggressive']:
            config_name = CONFIGS[key].name
            
            mmr_improvement = 0
            if result['old_greedy']['avg_mmr'] > 0:
                mmr_improvement = ((result['old_greedy']['avg_mmr'] - result[key]['avg_mmr']) 
                                 / result['old_greedy']['avg_mmr'] * 100)
            
            match_improvement = 0
            if result['old_greedy']['avg_matches'] > 0:
                match_improvement = ((result[key]['avg_matches'] - result['old_greedy']['avg_matches'])
                                   / result['old_greedy']['avg_matches'] * 100)
            
            time_overhead = result[key]['avg_time_ms'] - result['old_greedy']['avg_time_ms']
            
            print(f"  {config_name}:")
            print(f"    MMR quality: {mmr_improvement:+.1f}%")
            print(f"    Match count: {match_improvement:+.1f}%")
            print(f"    Time overhead: {time_overhead:+.3f}ms")
        
        # Compare balanced vs aggressive
        print("\n" + "Aggressive vs Balanced:")
        balanced_mmr = result['balanced']['avg_mmr']
        aggressive_mmr = result['aggressive']['avg_mmr']
        
        if balanced_mmr > 0:
            quality_change = ((balanced_mmr - aggressive_mmr) / balanced_mmr * 100)
            print(f"  Quality change: {quality_change:+.1f}% (negative = worse quality)")
        
        balanced_matches = result['balanced']['avg_matches']
        aggressive_matches = result['aggressive']['avg_matches']
        
        if balanced_matches > 0:
            match_change = ((aggressive_matches - balanced_matches) / balanced_matches * 100)
            print(f"  Match count change: {match_change:+.1f}%")
    
    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    print()
    print("Key Findings:")
    print("  - Aggressive Fairness increases match counts but may reduce quality")
    print("  - Processing time remains negligible for all configurations")
    print("  - Best configuration depends on: player base size, queue pressure, priorities")
    print()


if __name__ == "__main__":
    main()

