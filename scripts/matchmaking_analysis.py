"""
Matchmaking Algorithm Analysis Script

This script simulates the matchmaking algorithm with various player populations
to analyze match finding times and quality (MMR differences).
"""

import random
import statistics
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from collections import defaultdict

# Import config values
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
    preferred_race_type: str  # 'bw_only', 'sc2_only', 'both'
    join_time: float = 0.0
    wait_cycles: int = 0


@dataclass
class MatchResult:
    """Results from a matched pair"""
    player1_id: int
    player2_id: int
    player1_mmr: int
    player2_mmr: int
    mmr_difference: int
    wait_time_seconds: float
    wait_cycles: int


@dataclass
class SimulationMetrics:
    """Aggregated metrics from a simulation run"""
    total_players: int
    queue_size: int
    matches_found: int
    avg_wait_time: float = 0.0
    median_wait_time: float = 0.0
    max_wait_time: float = 0.0
    avg_mmr_diff: float = 0.0
    median_mmr_diff: float = 0.0
    max_mmr_diff: int = 0
    match_rate_per_wave: float = 0.0
    pressure_ratio: float = 0.0
    pressure_category: str = ""
    mmr_window_used: Tuple[int, int] = (0, 0)


class MatchmakingSimulator:
    """Simulates the matchmaking algorithm"""
    
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
    
    def _get_max_diff(self, wait_cycles: int, queue_size: int, effective_pop: int) -> int:
        """Calculate max MMR difference based on queue pressure and wait time"""
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
    
    def _categorize_players(self, players: List[SimulatedPlayer]) -> Tuple[List, List, List]:
        """Categorize players into BW-only, SC2-only, and both lists"""
        bw_only = []
        sc2_only = []
        both_races = []
        
        for player in players:
            if player.has_bw and not player.has_sc2:
                bw_only.append(player)
            elif player.has_sc2 and not player.has_bw:
                sc2_only.append(player)
            elif player.has_bw and player.has_sc2:
                both_races.append(player)
        
        # Sort by MMR (highest first)
        bw_only.sort(key=lambda p: p.bw_mmr, reverse=True)
        sc2_only.sort(key=lambda p: p.sc2_mmr, reverse=True)
        both_races.sort(key=lambda p: max(p.bw_mmr, p.sc2_mmr), reverse=True)
        
        return bw_only, sc2_only, both_races
    
    def _equalize_lists(self, list_x: List, list_y: List, list_z: List) -> Tuple[List, List, List]:
        """Equalize the sizes of list_x and list_y by moving players from list_z"""
        x_copy = list_x.copy()
        y_copy = list_y.copy()
        z_copy = list_z.copy()
        
        # Special case: if both X and Y are empty, distribute Z players evenly
        if not x_copy and not y_copy and z_copy:
            for i, player in enumerate(z_copy):
                if i % 2 == 0:
                    x_copy.append(player)
                else:
                    y_copy.append(player)
            z_copy = []
            return x_copy, y_copy, z_copy
        
        # Normal equalization logic
        while z_copy:
            if len(x_copy) < len(y_copy):
                player = z_copy.pop(0)
                x_copy.append(player)
            elif len(x_copy) > len(y_copy):
                player = z_copy.pop(0)
                y_copy.append(player)
            else:
                if len(z_copy) > 0:
                    player = z_copy.pop(0)
                    x_copy.append(player)
                if len(z_copy) > 0:
                    player = z_copy.pop(0)
                    y_copy.append(player)
        
        return x_copy, y_copy, z_copy
    
    def _find_matches(self, lead_side: List[SimulatedPlayer], follow_side: List[SimulatedPlayer],
                     is_bw_match: bool, queue_size: int, effective_pop: int) -> List[MatchResult]:
        """Find matches between lead_side and follow_side players"""
        matches = []
        used_lead = set()
        used_follow = set()
        
        if not lead_side:
            return matches
        
        # Sort lead side by wait cycles (highest first)
        sorted_lead = sorted(lead_side, key=lambda p: p.wait_cycles, reverse=True)
        
        for lead_player in sorted_lead:
            if lead_player.player_id in used_lead:
                continue
            
            lead_mmr = lead_player.bw_mmr if is_bw_match else lead_player.sc2_mmr
            max_diff = self._get_max_diff(lead_player.wait_cycles, queue_size, effective_pop)
            
            # Find best match in follow side
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
                
                matches.append(MatchResult(
                    player1_id=lead_player.player_id,
                    player2_id=best_match.player_id,
                    player1_mmr=p1_mmr,
                    player2_mmr=p2_mmr,
                    mmr_difference=abs(p1_mmr - p2_mmr),
                    wait_time_seconds=wait_time,
                    wait_cycles=max(lead_player.wait_cycles, best_match.wait_cycles)
                ))
                used_lead.add(lead_player.player_id)
                used_follow.add(best_match.player_id)
        
        return matches
    
    def simulate_match_wave(self, queue: List[SimulatedPlayer], 
                           effective_population: int) -> Tuple[List[MatchResult], List[SimulatedPlayer]]:
        """Simulate a single matchmaking wave"""
        # Increment wait cycles
        for player in queue:
            player.wait_cycles += 1
        
        # Categorize and equalize
        bw_list, sc2_list, both_races = self._categorize_players(queue)
        bw_list, sc2_list, remaining_z = self._equalize_lists(bw_list, sc2_list, both_races)
        
        # Find matches
        matches = []
        queue_size = len(queue)
        
        if len(bw_list) > 0 and len(sc2_list) > 0:
            if len(bw_list) <= len(sc2_list):
                lead_side, follow_side = bw_list, sc2_list
                is_bw_match = True
            else:
                lead_side, follow_side = sc2_list, bw_list
                is_bw_match = False
            
            matches = self._find_matches(lead_side, follow_side, is_bw_match, queue_size, effective_population)
        
        # Remove matched players from queue
        matched_ids = set()
        for match in matches:
            matched_ids.add(match.player1_id)
            matched_ids.add(match.player2_id)
        
        remaining_queue = [p for p in queue if p.player_id not in matched_ids]
        
        return matches, remaining_queue


def generate_player_population(total_players: int, mmr_distribution: str = 'normal') -> List[SimulatedPlayer]:
    """
    Generate a realistic player population with MMR distribution
    
    mmr_distribution options:
    - 'normal': Normal distribution centered at 1500
    - 'bimodal': Two peaks (casual and competitive)
    - 'uniform': Evenly distributed
    """
    players = []
    
    for i in range(total_players):
        # Determine race preference (40% BW only, 30% SC2 only, 30% both)
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
        
        # Generate MMR based on distribution type
        if mmr_distribution == 'normal':
            bw_mmr = int(random.gauss(1500, 300))
            sc2_mmr = int(random.gauss(1500, 300))
        elif mmr_distribution == 'bimodal':
            # 60% casual (1200-1600), 40% competitive (1600-2000)
            if random.random() < 0.6:
                bw_mmr = int(random.gauss(1400, 150))
                sc2_mmr = int(random.gauss(1400, 150))
            else:
                bw_mmr = int(random.gauss(1800, 150))
                sc2_mmr = int(random.gauss(1800, 150))
        else:  # uniform
            bw_mmr = random.randint(1000, 2000)
            sc2_mmr = random.randint(1000, 2000)
        
        # Clamp MMR to reasonable bounds
        bw_mmr = max(800, min(2500, bw_mmr))
        sc2_mmr = max(800, min(2500, sc2_mmr))
        
        players.append(SimulatedPlayer(
            player_id=i,
            bw_mmr=bw_mmr,
            sc2_mmr=sc2_mmr,
            has_bw=has_bw,
            has_sc2=has_sc2,
            preferred_race_type=preferred
        ))
    
    return players


def run_simulation(total_population: int, queue_percentage: float, 
                   num_waves: int = 20, mmr_distribution: str = 'normal') -> Dict:
    """
    Run a complete simulation
    
    Args:
        total_population: Total number of online players
        queue_percentage: Percentage of population in queue (0.05 to 0.20)
        num_waves: Number of matchmaking waves to simulate
        mmr_distribution: Type of MMR distribution
    """
    simulator = MatchmakingSimulator()
    
    # Generate population
    all_players = generate_player_population(total_population, mmr_distribution)
    
    # Select players for initial queue
    queue_size = int(total_population * queue_percentage)
    queue = random.sample(all_players, queue_size)
    
    # Reset wait cycles and set join time
    for player in queue:
        player.wait_cycles = 0
        player.join_time = 0.0
    
    # Run simulation waves
    all_matches = []
    wave_metrics = []
    
    effective_population = total_population
    
    for wave in range(num_waves):
        matches, queue = simulator.simulate_match_wave(queue, effective_population)
        all_matches.extend(matches)
        
        # Calculate wave metrics
        queue_pressure = simulator._calculate_queue_pressure(len(queue), effective_population)
        
        if queue_pressure >= simulator.HIGH_PRESSURE_THRESHOLD:
            pressure_category = "HIGH"
            mmr_params = simulator.HIGH_PRESSURE_PARAMS
        elif queue_pressure >= simulator.MODERATE_PRESSURE_THRESHOLD:
            pressure_category = "MODERATE"
            mmr_params = simulator.MODERATE_PRESSURE_PARAMS
        else:
            pressure_category = "LOW"
            mmr_params = simulator.LOW_PRESSURE_PARAMS
        
        wave_metrics.append({
            'wave': wave,
            'matches': len(matches),
            'queue_size': len(queue),
            'pressure': queue_pressure,
            'pressure_category': pressure_category,
            'mmr_params': mmr_params
        })
    
    # Aggregate metrics
    if all_matches:
        wait_times = [m.wait_time_seconds for m in all_matches]
        mmr_diffs = [m.mmr_difference for m in all_matches]
        
        metrics = SimulationMetrics(
            total_players=total_population,
            queue_size=queue_size,
            matches_found=len(all_matches),
            avg_wait_time=statistics.mean(wait_times),
            median_wait_time=statistics.median(wait_times),
            max_wait_time=max(wait_times),
            avg_mmr_diff=statistics.mean(mmr_diffs),
            median_mmr_diff=statistics.median(mmr_diffs),
            max_mmr_diff=max(mmr_diffs),
            match_rate_per_wave=len(all_matches) / num_waves
        )
    else:
        metrics = SimulationMetrics(
            total_players=total_population,
            queue_size=queue_size,
            matches_found=0
        )
    
    return {
        'metrics': metrics,
        'matches': all_matches,
        'wave_metrics': wave_metrics,
        'final_queue_size': len(queue)
    }


def main():
    """Run comprehensive matchmaking analysis"""
    print("=" * 80)
    print("MATCHMAKING ALGORITHM ANALYSIS")
    print("=" * 80)
    print()
    
    # Test scenarios
    scenarios = [
        # Small population
        {'population': 20, 'queue_pct': 0.10, 'name': 'Small Pop, Low Queue'},
        {'population': 20, 'queue_pct': 0.20, 'name': 'Small Pop, High Queue'},
        
        # Medium population
        {'population': 50, 'queue_pct': 0.05, 'name': 'Medium Pop, Very Low Queue'},
        {'population': 50, 'queue_pct': 0.10, 'name': 'Medium Pop, Low Queue'},
        {'population': 50, 'queue_pct': 0.15, 'name': 'Medium Pop, Moderate Queue'},
        {'population': 50, 'queue_pct': 0.20, 'name': 'Medium Pop, High Queue'},
        
        # Large population
        {'population': 100, 'queue_pct': 0.05, 'name': 'Large Pop, Very Low Queue'},
        {'population': 100, 'queue_pct': 0.10, 'name': 'Large Pop, Low Queue'},
        {'population': 100, 'queue_pct': 0.15, 'name': 'Large Pop, Moderate Queue'},
        {'population': 100, 'queue_pct': 0.20, 'name': 'Large Pop, High Queue'},
    ]
    
    results = []
    
    for scenario in scenarios:
        print(f"\n{'=' * 80}")
        print(f"Scenario: {scenario['name']}")
        print(f"Population: {scenario['population']}, Queue: {scenario['queue_pct']*100:.0f}%")
        print(f"{'=' * 80}")
        
        result = run_simulation(
            scenario['population'],
            scenario['queue_pct'],
            num_waves=20,
            mmr_distribution='normal'
        )
        
        metrics = result['metrics']
        
        print(f"\nRESULTS:")
        print(f"  Total Matches Found: {metrics.matches_found}")
        print(f"  Match Rate: {metrics.match_rate_per_wave:.2f} matches/wave")
        print(f"  Final Queue Size: {result['final_queue_size']}")
        print(f"\nWAIT TIMES:")
        print(f"  Average: {metrics.avg_wait_time:.1f}s ({metrics.avg_wait_time/45:.1f} waves)")
        print(f"  Median: {metrics.median_wait_time:.1f}s ({metrics.median_wait_time/45:.1f} waves)")
        print(f"  Maximum: {metrics.max_wait_time:.1f}s ({metrics.max_wait_time/45:.1f} waves)")
        print(f"\nMATCH QUALITY (MMR Difference):")
        print(f"  Average: {metrics.avg_mmr_diff:.1f}")
        print(f"  Median: {metrics.median_mmr_diff:.1f}")
        print(f"  Maximum: {metrics.max_mmr_diff}")
        
        # Analyze pressure trends
        pressure_categories = [w['pressure_category'] for w in result['wave_metrics']]
        pressure_counts = {cat: pressure_categories.count(cat) for cat in set(pressure_categories)}
        print(f"\nPRESSURE DISTRIBUTION:")
        for cat, count in sorted(pressure_counts.items()):
            print(f"  {cat}: {count} waves ({count/len(result['wave_metrics'])*100:.0f}%)")
        
        results.append({
            'scenario': scenario,
            'result': result,
            'metrics': metrics
        })
    
    # Generate summary report
    print("\n" + "=" * 80)
    print("SUMMARY ANALYSIS")
    print("=" * 80)
    
    print("\nMatch Success Rate by Population Size:")
    for pop_size in [20, 50, 100]:
        pop_results = [r for r in results if r['scenario']['population'] == pop_size]
        avg_matches = statistics.mean([r['metrics'].matches_found for r in pop_results])
        avg_rate = statistics.mean([r['metrics'].match_rate_per_wave for r in pop_results])
        print(f"  Population {pop_size}: {avg_matches:.1f} matches (avg), {avg_rate:.2f} matches/wave")
    
    print("\nAverage Wait Times by Queue Percentage:")
    for queue_pct in [0.05, 0.10, 0.15, 0.20]:
        pct_results = [r for r in results if r['scenario']['queue_pct'] == queue_pct]
        if pct_results:
            avg_wait = statistics.mean([r['metrics'].avg_wait_time for r in pct_results if r['metrics'].avg_wait_time > 0])
            print(f"  {queue_pct*100:.0f}% in queue: {avg_wait:.1f}s ({avg_wait/45:.1f} waves)")
    
    print("\nMatch Quality by Population Size:")
    for pop_size in [20, 50, 100]:
        pop_results = [r for r in results if r['scenario']['population'] == pop_size]
        valid_results = [r for r in pop_results if r['metrics'].avg_mmr_diff > 0]
        if valid_results:
            avg_diff = statistics.mean([r['metrics'].avg_mmr_diff for r in valid_results])
            print(f"  Population {pop_size}: {avg_diff:.1f} MMR avg difference")
    
    print("\nAnalysis complete!")
    print("\nKey Insights:")
    print("  1. Check if match rates are acceptable across scenarios")
    print("  2. Verify wait times don't exceed player patience thresholds")
    print("  3. Ensure MMR differences maintain competitive balance")
    print("  4. Consider pressure scaling effectiveness")
    print()


if __name__ == "__main__":
    main()

