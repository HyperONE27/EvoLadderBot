"""
Matchmaking Algorithm Comparison: Old (Greedy) vs New (Locally-Optimal)

This script compares the old greedy algorithm against the new optimized algorithm
with the same test data to demonstrate improvements in match quality.
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


class OldGreedyMatcher:
    """Old greedy matching algorithm for comparison"""
    
    def __init__(self):
        self.HIGH_PRESSURE_THRESHOLD = 0.50  # Old value
        self.MODERATE_PRESSURE_THRESHOLD = 0.30  # Old value
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
    
    def find_matches(self, lead_side: List[SimulatedPlayer], follow_side: List[SimulatedPlayer],
                    is_bw_match: bool, queue_size: int, effective_pop: int) -> List[Tuple[SimulatedPlayer, SimulatedPlayer]]:
        """Old greedy matching algorithm"""
        matches = []
        used_lead = set()
        used_follow = set()
        
        if not lead_side:
            return matches
        
        # Sort by wait cycles (highest first) - old approach
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


class NewOptimalMatcher:
    """New locally-optimal matching algorithm"""
    
    def __init__(self):
        self.HIGH_PRESSURE_THRESHOLD = config.MM_HIGH_PRESSURE_THRESHOLD  # New: 0.20
        self.MODERATE_PRESSURE_THRESHOLD = config.MM_MODERATE_PRESSURE_THRESHOLD  # New: 0.10
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
    
    def find_matches(self, lead_side: List[SimulatedPlayer], follow_side: List[SimulatedPlayer],
                    is_bw_match: bool, queue_size: int, effective_pop: int) -> List[Tuple[SimulatedPlayer, SimulatedPlayer]]:
        """New locally-optimal matching algorithm"""
        if not lead_side or not follow_side:
            return []
        
        # Build all valid candidate pairs
        candidates = []
        for lead_player in lead_side:
            lead_mmr = lead_player.bw_mmr if is_bw_match else lead_player.sc2_mmr
            max_diff = self._get_max_diff(lead_player.wait_cycles, queue_size, effective_pop)
            
            for follow_player in follow_side:
                follow_mmr = follow_player.sc2_mmr if is_bw_match else follow_player.bw_mmr
                mmr_diff = abs(lead_mmr - follow_mmr)
                
                if mmr_diff <= max_diff:
                    wait_priority = (lead_player.wait_cycles + follow_player.wait_cycles)
                    score = (mmr_diff ** 2) - (wait_priority * config.MM_WAIT_CYCLE_PRIORITY_COEFFICIENT)
                    candidates.append((score, lead_player, follow_player, mmr_diff))
        
        # Sort by score and greedily select
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


def generate_test_queue(queue_size: int, mmr_distribution: str = 'normal') -> List[SimulatedPlayer]:
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
        
        if mmr_distribution == 'normal':
            bw_mmr = int(random.gauss(1500, 300))
            sc2_mmr = int(random.gauss(1500, 300))
        else:
            bw_mmr = random.randint(1000, 2000)
            sc2_mmr = random.randint(1000, 2000)
        
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
        z_copy = []
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


def compare_algorithms(queue_size: int, effective_pop: int, trials: int = 100) -> Dict:
    """Compare old vs new algorithm"""
    old_matcher = OldGreedyMatcher()
    new_matcher = NewOptimalMatcher()
    
    old_mmr_diffs = []
    new_mmr_diffs = []
    old_match_counts = []
    new_match_counts = []
    old_times = []
    new_times = []
    
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
        
        # Test old algorithm
        start = time.perf_counter()
        old_matches = old_matcher.find_matches(lead_side, follow_side, is_bw_match, queue_size, effective_pop)
        old_times.append(time.perf_counter() - start)
        
        # Test new algorithm
        start = time.perf_counter()
        new_matches = new_matcher.find_matches(lead_side, follow_side, is_bw_match, queue_size, effective_pop)
        new_times.append(time.perf_counter() - start)
        
        if old_matches:
            for p1, p2 in old_matches:
                p1_mmr = p1.bw_mmr if is_bw_match else p1.sc2_mmr
                p2_mmr = p2.sc2_mmr if is_bw_match else p2.bw_mmr
                old_mmr_diffs.append(abs(p1_mmr - p2_mmr))
            old_match_counts.append(len(old_matches))
        
        if new_matches:
            for p1, p2 in new_matches:
                p1_mmr = p1.bw_mmr if is_bw_match else p1.sc2_mmr
                p2_mmr = p2.sc2_mmr if is_bw_match else p2.bw_mmr
                new_mmr_diffs.append(abs(p1_mmr - p2_mmr))
            new_match_counts.append(len(new_matches))
    
    return {
        'old_avg_mmr': statistics.mean(old_mmr_diffs) if old_mmr_diffs else 0,
        'new_avg_mmr': statistics.mean(new_mmr_diffs) if new_mmr_diffs else 0,
        'old_median_mmr': statistics.median(old_mmr_diffs) if old_mmr_diffs else 0,
        'new_median_mmr': statistics.median(new_mmr_diffs) if new_mmr_diffs else 0,
        'old_avg_matches': statistics.mean(old_match_counts) if old_match_counts else 0,
        'new_avg_matches': statistics.mean(new_match_counts) if new_match_counts else 0,
        'old_avg_time_ms': statistics.mean(old_times) * 1000 if old_times else 0,
        'new_avg_time_ms': statistics.mean(new_times) * 1000 if new_times else 0,
    }


def main():
    print("=" * 80)
    print("MATCHMAKING ALGORITHM COMPARISON")
    print("Old (Greedy) vs New (Locally-Optimal)")
    print("=" * 80)
    print()
    
    scenarios = [
        (5, 20, "5 in queue, 20 active (25%)"),
        (10, 20, "10 in queue, 20 active (50%)"),
        (10, 30, "10 in queue, 30 active (33%)"),
        (15, 30, "15 in queue, 30 active (50%)"),
        (20, 30, "20 in queue, 30 active (67%)"),
        (25, 40, "25 in queue, 40 active (62%)"),
        (30, 50, "30 in queue, 50 active (60%)"),
    ]
    
    for queue_size, effective_pop, description in scenarios:
        print(f"Scenario: {description}")
        result = compare_algorithms(queue_size, effective_pop, trials=200)
        
        mmr_improvement = 0
        if result['old_avg_mmr'] > 0:
            mmr_improvement = ((result['old_avg_mmr'] - result['new_avg_mmr']) 
                             / result['old_avg_mmr'] * 100)
        
        match_improvement = 0
        if result['old_avg_matches'] > 0:
            match_improvement = ((result['new_avg_matches'] - result['old_avg_matches'])
                               / result['old_avg_matches'] * 100)
        
        print(f"  OLD Algorithm:")
        print(f"    Avg matches: {result['old_avg_matches']:.2f}")
        print(f"    Avg MMR diff: {result['old_avg_mmr']:.1f}")
        print(f"    Median MMR diff: {result['old_median_mmr']:.1f}")
        print(f"    Avg time: {result['old_avg_time_ms']:.3f} ms")
        
        print(f"  NEW Algorithm:")
        print(f"    Avg matches: {result['new_avg_matches']:.2f}")
        print(f"    Avg MMR diff: {result['new_avg_mmr']:.1f}")
        print(f"    Median MMR diff: {result['new_median_mmr']:.1f}")
        print(f"    Avg time: {result['new_avg_time_ms']:.3f} ms")
        
        print(f"  IMPROVEMENT:")
        print(f"    MMR quality: {mmr_improvement:+.1f}%")
        print(f"    Match count: {match_improvement:+.1f}%")
        print(f"    Processing time: {result['new_avg_time_ms'] - result['old_avg_time_ms']:+.3f} ms")
        print()
    
    print("=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()

