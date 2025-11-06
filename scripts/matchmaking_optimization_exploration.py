"""
Matchmaking Optimization Exploration Script

This script explores the current matchmaking algorithm's behavior
and compares greedy vs locally-optimal matching strategies.

Key Analysis Areas:
1. Greedy vs Optimal: How much better could matches be?
2. Parameter Sensitivity: Are current pressure params calibrated correctly?
3. Queue Behavior: Typical patterns with 20-30 players
"""

import random
import statistics
from dataclasses import dataclass
from typing import List, Tuple, Dict, Set
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
    wait_cycles: int = 0


@dataclass
class MatchPair:
    """A potential match between two players"""
    lead_player_id: int
    follow_player_id: int
    lead_mmr: int
    follow_mmr: int
    mmr_diff: int
    lead_wait_cycles: int
    follow_wait_cycles: int
    
    @property
    def total_wait_cycles(self) -> int:
        return self.lead_wait_cycles + self.follow_wait_cycles
    
    @property
    def max_wait_cycles(self) -> int:
        return max(self.lead_wait_cycles, self.follow_wait_cycles)


class MatchmakingComparison:
    """Compares greedy vs locally-optimal matching"""
    
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
        """Calculate queue pressure ratio"""
        if effective_pop <= 0:
            return 0.0
        
        if effective_pop <= self.POPULATION_THRESHOLD_LOW:
            scale = self.PRESSURE_SCALE_LOW_POP
        elif effective_pop <= self.POPULATION_THRESHOLD_MID:
            scale = self.PRESSURE_SCALE_MID_POP
        else:
            scale = self.PRESSURE_SCALE_HIGH_POP
        
        return min(1.0, (scale * queue_size) / effective_pop)
    
    def _get_max_diff(self, wait_cycles: int, queue_size: int, effective_pop: int) -> int:
        """Calculate max MMR difference"""
        if effective_pop == 0:
            base, growth = self.DEFAULT_PARAMS
        else:
            pressure_ratio = self._calculate_queue_pressure(queue_size, effective_pop)
            
            if pressure_ratio >= self.HIGH_PRESSURE_THRESHOLD:
                base, growth = self.HIGH_PRESSURE_PARAMS
            elif pressure_ratio >= self.MODERATE_PRESSURE_THRESHOLD:
                base, growth = self.MODERATE_PRESSURE_PARAMS
            else:
                base, growth = self.LOW_PRESSURE_PARAMS
        
        return base + (wait_cycles // self.MMR_EXPANSION_STEP) * growth
    
    def _categorize_and_equalize(self, players: List[SimulatedPlayer]) -> Tuple[List, List]:
        """Categorize players and equalize lists"""
        bw_only = [p for p in players if p.has_bw and not p.has_sc2]
        sc2_only = [p for p in players if p.has_sc2 and not p.has_bw]
        both_races = [p for p in players if p.has_bw and p.has_sc2]
        
        bw_list = bw_only.copy()
        sc2_list = sc2_only.copy()
        z_copy = both_races.copy()
        
        # Equalize using both_races
        if not bw_list and not sc2_list and z_copy:
            for i, player in enumerate(z_copy):
                if i % 2 == 0:
                    bw_list.append(player)
                else:
                    sc2_list.append(player)
            z_copy = []
        else:
            while z_copy:
                if len(bw_list) < len(sc2_list):
                    bw_list.append(z_copy.pop(0))
                elif len(bw_list) > len(sc2_list):
                    sc2_list.append(z_copy.pop(0))
                else:
                    if z_copy:
                        bw_list.append(z_copy.pop(0))
                    if z_copy:
                        sc2_list.append(z_copy.pop(0))
        
        return bw_list, sc2_list
    
    def greedy_match(self, lead_side: List[SimulatedPlayer], 
                    follow_side: List[SimulatedPlayer],
                    is_bw_match: bool, queue_size: int, 
                    effective_pop: int) -> List[MatchPair]:
        """Current greedy matching algorithm"""
        matches = []
        used_lead = set()
        used_follow = set()
        
        if not lead_side:
            return matches
        
        # Sort by wait cycles (highest first)
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
                follow_mmr = best_match.sc2_mmr if is_bw_match else best_match.bw_mmr
                matches.append(MatchPair(
                    lead_player_id=lead_player.player_id,
                    follow_player_id=best_match.player_id,
                    lead_mmr=lead_mmr,
                    follow_mmr=follow_mmr,
                    mmr_diff=abs(lead_mmr - follow_mmr),
                    lead_wait_cycles=lead_player.wait_cycles,
                    follow_wait_cycles=best_match.wait_cycles
                ))
                used_lead.add(lead_player.player_id)
                used_follow.add(best_match.player_id)
        
        return matches
    
    def locally_optimal_match(self, lead_side: List[SimulatedPlayer],
                             follow_side: List[SimulatedPlayer],
                             is_bw_match: bool, queue_size: int,
                             effective_pop: int) -> List[MatchPair]:
        """
        Locally-optimal matching using weighted bipartite matching.
        
        Strategy: Build all valid edges, then greedily select best matches
        that maximize overall quality (minimize total MMR differences).
        """
        if not lead_side or not follow_side:
            return []
        
        # Build all valid match candidates
        valid_pairs = []
        
        for lead_player in lead_side:
            lead_mmr = lead_player.bw_mmr if is_bw_match else lead_player.sc2_mmr
            max_diff = self._get_max_diff(lead_player.wait_cycles, queue_size, effective_pop)
            
            for follow_player in follow_side:
                follow_mmr = follow_player.sc2_mmr if is_bw_match else follow_player.bw_mmr
                mmr_diff = abs(lead_mmr - follow_mmr)
                
                if mmr_diff <= max_diff:
                    # Score: prioritize high wait times and low MMR differences
                    # Wait time bonus: longer wait = higher priority
                    wait_priority = lead_player.wait_cycles + follow_player.wait_cycles
                    
                    # Combined score: lower is better
                    # Weight wait time heavily (multiply by 20 to convert cycles to MMR-equivalent)
                    score = mmr_diff - (wait_priority * 20)
                    
                    valid_pairs.append((
                        score,
                        mmr_diff,
                        lead_player,
                        follow_player,
                        lead_mmr,
                        follow_mmr
                    ))
        
        # Sort by score (lower is better)
        valid_pairs.sort(key=lambda x: x[0])
        
        # Greedily select matches
        matches = []
        used_lead = set()
        used_follow = set()
        
        for score, mmr_diff, lead_player, follow_player, lead_mmr, follow_mmr in valid_pairs:
            if lead_player.player_id not in used_lead and follow_player.player_id not in used_follow:
                matches.append(MatchPair(
                    lead_player_id=lead_player.player_id,
                    follow_player_id=follow_player.player_id,
                    lead_mmr=lead_mmr,
                    follow_mmr=follow_mmr,
                    mmr_diff=mmr_diff,
                    lead_wait_cycles=lead_player.wait_cycles,
                    follow_wait_cycles=follow_player.wait_cycles
                ))
                used_lead.add(lead_player.player_id)
                used_follow.add(follow_player.player_id)
        
        return matches


def generate_realistic_queue(queue_size: int, mmr_distribution: str = 'normal') -> List[SimulatedPlayer]:
    """Generate a realistic queue snapshot"""
    players = []
    
    for i in range(queue_size):
        # Race distribution: 40% BW, 30% SC2, 30% both
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
        
        # Generate MMR
        if mmr_distribution == 'normal':
            bw_mmr = int(random.gauss(1500, 300))
            sc2_mmr = int(random.gauss(1500, 300))
        else:
            bw_mmr = random.randint(1000, 2000)
            sc2_mmr = random.randint(1000, 2000)
        
        bw_mmr = max(800, min(2500, bw_mmr))
        sc2_mmr = max(800, min(2500, sc2_mmr))
        
        # Wait cycles: weighted towards lower values (most players just joined)
        # 50% have wait_cycles 0-2, 30% have 3-5, 20% have 6+
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


def compare_algorithms_single_wave(queue_size: int, effective_pop: int, trials: int = 100) -> Dict:
    """Compare greedy vs locally-optimal for a given queue size"""
    comparator = MatchmakingComparison()
    
    greedy_mmr_diffs = []
    optimal_mmr_diffs = []
    greedy_match_counts = []
    optimal_match_counts = []
    improvement_cases = 0
    
    for trial in range(trials):
        queue = generate_realistic_queue(queue_size)
        bw_list, sc2_list = comparator._categorize_and_equalize(queue)
        
        if not bw_list or not sc2_list:
            continue
        
        # Choose lead/follow
        if len(bw_list) <= len(sc2_list):
            lead_side, follow_side = bw_list, sc2_list
            is_bw_match = True
        else:
            lead_side, follow_side = sc2_list, bw_list
            is_bw_match = False
        
        # Run both algorithms
        greedy_matches = comparator.greedy_match(
            lead_side, follow_side, is_bw_match, queue_size, effective_pop
        )
        optimal_matches = comparator.locally_optimal_match(
            lead_side, follow_side, is_bw_match, queue_size, effective_pop
        )
        
        if greedy_matches:
            greedy_mmr_diffs.extend([m.mmr_diff for m in greedy_matches])
            greedy_match_counts.append(len(greedy_matches))
        
        if optimal_matches:
            optimal_mmr_diffs.extend([m.mmr_diff for m in optimal_matches])
            optimal_match_counts.append(len(optimal_matches))
        
        # Check if optimal is better
        if greedy_matches and optimal_matches:
            greedy_avg = statistics.mean([m.mmr_diff for m in greedy_matches])
            optimal_avg = statistics.mean([m.mmr_diff for m in optimal_matches])
            if optimal_avg < greedy_avg or len(optimal_matches) > len(greedy_matches):
                improvement_cases += 1
    
    return {
        'greedy_avg_mmr': statistics.mean(greedy_mmr_diffs) if greedy_mmr_diffs else 0,
        'optimal_avg_mmr': statistics.mean(optimal_mmr_diffs) if optimal_mmr_diffs else 0,
        'greedy_median_mmr': statistics.median(greedy_mmr_diffs) if greedy_mmr_diffs else 0,
        'optimal_median_mmr': statistics.median(optimal_mmr_diffs) if optimal_mmr_diffs else 0,
        'greedy_avg_matches': statistics.mean(greedy_match_counts) if greedy_match_counts else 0,
        'optimal_avg_matches': statistics.mean(optimal_match_counts) if optimal_match_counts else 0,
        'improvement_percentage': (improvement_cases / trials) * 100,
        'trials_run': trials
    }


def analyze_pressure_params():
    """Analyze if current pressure parameters are well-calibrated"""
    print("=" * 80)
    print("PRESSURE PARAMETER CALIBRATION ANALYSIS")
    print("=" * 80)
    print()
    
    comparator = MatchmakingComparison()
    
    # Test various queue sizes at different population levels
    test_cases = [
        # (queue_size, effective_pop, description)
        (5, 20, "25% queue at 20 pop (target scenario)"),
        (10, 30, "33% queue at 30 pop (target scenario)"),
        (15, 30, "50% queue at 30 pop (peak hours)"),
        (20, 40, "50% queue at 40 pop"),
        (8, 50, "16% queue at 50 pop"),
        (15, 100, "15% queue at 100 pop"),
    ]
    
    for queue_size, effective_pop, description in test_cases:
        pressure = comparator._calculate_queue_pressure(queue_size, effective_pop)
        
        # Determine pressure category
        if pressure >= comparator.HIGH_PRESSURE_THRESHOLD:
            pressure_cat = "HIGH"
            params = comparator.HIGH_PRESSURE_PARAMS
        elif pressure >= comparator.MODERATE_PRESSURE_THRESHOLD:
            pressure_cat = "MODERATE"
            params = comparator.MODERATE_PRESSURE_PARAMS
        else:
            pressure_cat = "LOW"
            params = comparator.LOW_PRESSURE_PARAMS
        
        # Determine population scale
        if effective_pop <= comparator.POPULATION_THRESHOLD_LOW:
            pop_scale = comparator.PRESSURE_SCALE_LOW_POP
            pop_cat = "LOW"
        elif effective_pop <= comparator.POPULATION_THRESHOLD_MID:
            pop_scale = comparator.PRESSURE_SCALE_MID_POP
            pop_cat = "MID"
        else:
            pop_scale = comparator.PRESSURE_SCALE_HIGH_POP
            pop_cat = "HIGH"
        
        print(f"{description}")
        print(f"  Queue: {queue_size}, Pop: {effective_pop} ({pop_cat} pop)")
        print(f"  Raw ratio: {queue_size/effective_pop:.3f}")
        print(f"  Scale factor: {pop_scale}")
        print(f"  Scaled pressure: {pressure:.3f}")
        print(f"  Pressure category: {pressure_cat}")
        print(f"  MMR params: base={params[0]}, growth={params[1]}")
        print(f"  MMR window at wave 1: {params[0] + params[1]}")
        print(f"  MMR window at wave 5: {params[0] + 5*params[1]}")
        print(f"  MMR window at wave 10: {params[0] + 10*params[1]}")
        print()


def analyze_queue_behavior():
    """Analyze typical queue behavior for 20-30 player scenarios"""
    print("=" * 80)
    print("QUEUE BEHAVIOR ANALYSIS (20-30 PLAYERS)")
    print("=" * 80)
    print()
    
    target_scenarios = [
        (20, 20, "20 in queue, 20 active (100% - unrealistic but boundary)"),
        (10, 20, "10 in queue, 20 active (50% - high pressure)"),
        (5, 20, "5 in queue, 20 active (25% - moderate)"),
        (3, 20, "3 in queue, 20 active (15% - low)"),
        (15, 30, "15 in queue, 30 active (50% - high pressure)"),
        (10, 30, "10 in queue, 30 active (33% - moderate)"),
        (6, 30, "6 in queue, 30 active (20% - low-moderate)"),
        (3, 30, "3 in queue, 30 active (10% - low)"),
    ]
    
    for queue_size, effective_pop, description in target_scenarios:
        print(f"Scenario: {description}")
        result = compare_algorithms_single_wave(queue_size, effective_pop, trials=200)
        
        print(f"  Greedy Algorithm:")
        print(f"    Avg matches: {result['greedy_avg_matches']:.2f}")
        print(f"    Avg MMR diff: {result['greedy_avg_mmr']:.1f}")
        print(f"    Median MMR diff: {result['greedy_median_mmr']:.1f}")
        
        print(f"  Locally-Optimal Algorithm:")
        print(f"    Avg matches: {result['optimal_avg_matches']:.2f}")
        print(f"    Avg MMR diff: {result['optimal_avg_mmr']:.1f}")
        print(f"    Median MMR diff: {result['optimal_median_mmr']:.1f}")
        
        # Calculate improvement
        if result['greedy_avg_mmr'] > 0:
            mmr_improvement = ((result['greedy_avg_mmr'] - result['optimal_avg_mmr']) 
                             / result['greedy_avg_mmr'] * 100)
            match_improvement = ((result['optimal_avg_matches'] - result['greedy_avg_matches'])
                               / result['greedy_avg_matches'] * 100) if result['greedy_avg_matches'] > 0 else 0
            
            print(f"  Improvement:")
            print(f"    MMR quality: {mmr_improvement:+.1f}%")
            print(f"    Match count: {match_improvement:+.1f}%")
            print(f"    Better in {result['improvement_percentage']:.1f}% of trials")
        print()


def main():
    """Run comprehensive optimization exploration"""
    print("\n" + "=" * 80)
    print("MATCHMAKING OPTIMIZATION EXPLORATION")
    print("=" * 80)
    print()
    
    # 1. Analyze pressure parameter calibration
    analyze_pressure_params()
    
    # 2. Analyze queue behavior for target scenarios
    analyze_queue_behavior()
    
    print("=" * 80)
    print("EXPLORATION COMPLETE")
    print("=" * 80)
    print()
    print("Key Questions for Optimization:")
    print("1. Does the locally-optimal algorithm provide meaningful improvements?")
    print("2. Are the pressure thresholds triggering correctly for 20-30 player queues?")
    print("3. Are the MMR window growth rates appropriate?")
    print("4. Should we adjust the wait_cycle priority bonus?")
    print()


if __name__ == "__main__":
    main()

