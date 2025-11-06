"""
Three-Way Matchmaking Configuration Comparison

Compares three configurations:
1. Aggressive Fairness: Everyone matches (wider windows, more stomps)
2. Balanced: Sweet spot (recommended for launch)
3. Strict Quality: Competitive matches only (tighter windows, some don't match)
"""

import random
import statistics
import time
from dataclasses import dataclass
from typing import List, Tuple, Dict
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))


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
                 low_params: Tuple[int, int], wait_coef: int, wait_exp: float,
                 balance_threshold: int):
        self.name = name
        self.HIGH_PRESSURE_THRESHOLD = high_threshold
        self.MODERATE_PRESSURE_THRESHOLD = mod_threshold
        self.HIGH_PRESSURE_PARAMS = high_params
        self.MODERATE_PRESSURE_PARAMS = mod_params
        self.LOW_PRESSURE_PARAMS = low_params
        self.WAIT_COEFFICIENT = wait_coef
        self.WAIT_EXPONENT = wait_exp
        self.BALANCE_THRESHOLD = balance_threshold
        self.DEFAULT_PARAMS = (75, 25)
        self.MMR_EXPANSION_STEP = 1
        self.POPULATION_THRESHOLD_LOW = 10
        self.POPULATION_THRESHOLD_MID = 25
        self.PRESSURE_SCALE_LOW_POP = 1.2
        self.PRESSURE_SCALE_MID_POP = 1.0
        self.PRESSURE_SCALE_HIGH_POP = 0.8


# Three configurations to compare
CONFIGS = {
    'aggressive': MatcherConfig(
        name="Aggressive Fairness",
        high_threshold=0.12,
        mod_threshold=0.05,
        high_params=(75, 25),
        mod_params=(120, 50),
        low_params=(160, 70),
        wait_coef=60,
        wait_exp=1.5,
        balance_threshold=75
    ),
    'balanced': MatcherConfig(
        name="Balanced",
        high_threshold=0.20,
        mod_threshold=0.10,
        high_params=(75, 25),
        mod_params=(100, 35),
        low_params=(125, 45),
        wait_coef=20,
        wait_exp=1.25,
        balance_threshold=50
    ),
    'strict': MatcherConfig(
        name="Strict Quality",
        high_threshold=0.30,  # Harder to trigger tight windows
        mod_threshold=0.15,
        high_params=(50, 20),  # Much tighter base, slower growth
        mod_params=(75, 25),
        low_params=(100, 30),  # Tight even in low pressure
        wait_coef=10,  # Lower priority for long-waiters
        wait_exp=1.1,  # Nearly linear
        balance_threshold=30  # Very strict skill balance
    )
}


class ConfigurableMatcher:
    """Matcher with configurable parameters"""
    
    def __init__(self, config: MatcherConfig):
        self.config = config
    
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
        """Find matches using locally-optimal algorithm"""
        if not lead_side or not follow_side:
            return []
        
        # Build candidates
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


def compare_configurations(queue_size: int, effective_pop: int, trials: int = 200) -> Dict:
    """Compare all three configurations"""
    matchers = {
        'aggressive': ConfigurableMatcher(CONFIGS['aggressive']),
        'balanced': ConfigurableMatcher(CONFIGS['balanced']),
        'strict': ConfigurableMatcher(CONFIGS['strict'])
    }
    
    results = {key: {'mmr_diffs': [], 'match_counts': [], 'times': [], 'max_diffs': []} 
               for key in matchers.keys()}
    
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
                match_diffs = []
                for p1, p2 in matches:
                    p1_mmr = p1.bw_mmr if is_bw_match else p1.sc2_mmr
                    p2_mmr = p2.sc2_mmr if is_bw_match else p2.bw_mmr
                    diff = abs(p1_mmr - p2_mmr)
                    match_diffs.append(diff)
                    results[key]['mmr_diffs'].append(diff)
                
                results[key]['match_counts'].append(len(matches))
                if match_diffs:
                    results[key]['max_diffs'].append(max(match_diffs))
    
    return {
        key: {
            'avg_mmr': statistics.mean(data['mmr_diffs']) if data['mmr_diffs'] else 0,
            'median_mmr': statistics.median(data['mmr_diffs']) if data['mmr_diffs'] else 0,
            'max_mmr': max(data['max_diffs']) if data['max_diffs'] else 0,
            'avg_max_mmr': statistics.mean(data['max_diffs']) if data['max_diffs'] else 0,
            'avg_matches': statistics.mean(data['match_counts']) if data['match_counts'] else 0,
            'avg_time_ms': statistics.mean(data['times']) * 1000 if data['times'] else 0,
        }
        for key, data in results.items()
    }


def print_mmr_windows():
    """Show MMR window comparison"""
    print("\n" + "=" * 80)
    print("MMR WINDOW COMPARISON (Wave 0, 5, 10)")
    print("=" * 80)
    
    for pressure, label in [('LOW', 'LOW PRESSURE'), ('MODERATE', 'MODERATE'), ('HIGH', 'HIGH')]:
        print(f"\n{label}:")
        print(f"{'Wave':<8} {'Aggressive':<15} {'Balanced':<15} {'Strict':<15}")
        print("-" * 60)
        
        for wave in [0, 5, 10]:
            windows = {}
            for key, config in CONFIGS.items():
                if pressure == 'HIGH':
                    base, growth = config.HIGH_PRESSURE_PARAMS
                elif pressure == 'MODERATE':
                    base, growth = config.MODERATE_PRESSURE_PARAMS
                else:
                    base, growth = config.LOW_PRESSURE_PARAMS
                windows[key] = base + (wave * growth)
            
            print(f"{wave:<8} {windows['aggressive']:<15} {windows['balanced']:<15} {windows['strict']:<15}")


def main():
    print("=" * 80)
    print("THREE-WAY MATCHMAKING COMPARISON")
    print("=" * 80)
    print()
    print("Configurations:")
    print("  1. Aggressive Fairness: Everyone matches (wider windows)")
    print("  2. Balanced: Sweet spot (recommended)")
    print("  3. Strict Quality: Competitive only (tighter windows)")
    print()
    
    print_mmr_windows()
    
    scenarios = [
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
        
        print(f"\n{'Config':<20} {'Avg MMR':<12} {'Median':<12} {'Max':<12} {'Matches':<12} {'Time (ms)':<12}")
        print("-" * 80)
        
        for key in ['aggressive', 'balanced', 'strict']:
            config_name = CONFIGS[key].name
            avg_mmr = result[key]['avg_mmr']
            median_mmr = result[key]['median_mmr']
            max_mmr = result[key]['avg_max_mmr']
            avg_matches = result[key]['avg_matches']
            avg_time = result[key]['avg_time_ms']
            
            print(f"{config_name:<20} {avg_mmr:<12.1f} {median_mmr:<12.1f} {max_mmr:<12.1f} {avg_matches:<12.2f} {avg_time:<12.3f}")
        
        # Show trade-offs
        print("\nKey Trade-offs:")
        balanced_quality = result['balanced']['avg_mmr']
        strict_quality = result['strict']['avg_mmr']
        aggressive_quality = result['aggressive']['avg_mmr']
        
        balanced_matches = result['balanced']['avg_matches']
        strict_matches = result['strict']['avg_matches']
        aggressive_matches = result['aggressive']['avg_matches']
        
        if balanced_quality > 0:
            print(f"  Strict vs Balanced:")
            print(f"    Quality improvement: {(balanced_quality - strict_quality) / balanced_quality * 100:+.1f}%")
            print(f"    Match count change: {(strict_matches - balanced_matches) / balanced_matches * 100:+.1f}%")
            
            print(f"  Aggressive vs Balanced:")
            print(f"    Quality change: {(balanced_quality - aggressive_quality) / balanced_quality * 100:+.1f}%")
            print(f"    Match count change: {(aggressive_matches - balanced_matches) / balanced_matches * 100:+.1f}%")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print("Aggressive Fairness:")
    print("  + Everyone gets matched")
    print("  + Very wide windows for long-waiters")
    print("  - Large MMR gaps possible (stomps)")
    print("  - Lower competitive quality")
    print()
    print("Balanced (RECOMMENDED):")
    print("  + Good match quality")
    print("  + Most players match within 3-5 waves")
    print("  + Reasonable wait times")
    print("  = Sweet spot for 20-30 player queues")
    print()
    print("Strict Quality:")
    print("  + Highly competitive matches")
    print("  + Small MMR deltas")
    print("  - Fewer matches overall")
    print("  - Long-waiters may never match")
    print("  - Only works with large populations")
    print()


if __name__ == "__main__":
    main()

