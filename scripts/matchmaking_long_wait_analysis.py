"""
Analysis of Aggressive Fairness Impact on Long-Waiting Players

Shows the difference between Balanced and Aggressive configurations
specifically for players who have been waiting multiple waves.
"""

import random
import statistics
from dataclasses import dataclass
from typing import List, Tuple
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))


@dataclass
class PlayerWaitAnalysis:
    """Analysis of a player's wait experience"""
    player_id: int
    wait_cycles: int
    matched_in_balanced: bool
    matched_in_aggressive: bool
    mmr_diff_balanced: int = 0
    mmr_diff_aggressive: int = 0


def analyze_mmr_windows():
    """Show how MMR windows expand differently"""
    print("=" * 80)
    print("MMR WINDOW EXPANSION COMPARISON")
    print("=" * 80)
    print()
    
    # Balanced params
    balanced_params = {
        'LOW': (125, 45),
        'MODERATE': (100, 35),
        'HIGH': (75, 25)
    }
    
    # Aggressive params
    aggressive_params = {
        'LOW': (160, 70),
        'MODERATE': (120, 50),
        'HIGH': (75, 25)
    }
    
    for pressure in ['LOW', 'MODERATE', 'HIGH']:
        print(f"\n{pressure} PRESSURE:")
        print(f"{'Wave':<8} {'Balanced Window':<20} {'Aggressive Window':<20} {'Difference':<15}")
        print("-" * 80)
        
        for wave in [0, 1, 2, 3, 5, 10, 15]:
            balanced_base, balanced_growth = balanced_params[pressure]
            aggressive_base, aggressive_growth = aggressive_params[pressure]
            
            balanced_window = balanced_base + (wave * balanced_growth)
            aggressive_window = aggressive_base + (wave * aggressive_growth)
            diff = aggressive_window - balanced_window
            
            print(f"{wave:<8} {balanced_window:<20} {aggressive_window:<20} {diff:+<15}")


def analyze_pressure_thresholds():
    """Show when different pressure modes trigger"""
    print("\n" + "=" * 80)
    print("PRESSURE THRESHOLD COMPARISON")
    print("=" * 80)
    print()
    
    # Balanced thresholds
    balanced_high = 0.20
    balanced_mod = 0.10
    
    # Aggressive thresholds
    aggressive_high = 0.12
    aggressive_mod = 0.05
    
    print(f"{'Queue Size':<12} {'Active Pop':<12} {'Pressure':<12} {'Balanced Mode':<20} {'Aggressive Mode':<20}")
    print("-" * 80)
    
    test_cases = [
        (1, 30), (2, 30), (3, 30), (5, 30), (10, 30), (15, 30),
        (5, 20), (10, 20), (15, 20),
        (10, 50), (20, 50), (30, 50)
    ]
    
    for queue_size, active_pop in test_cases:
        # Calculate pressure (using HIGH pop scale of 0.8)
        scale = 0.8 if active_pop > 25 else (1.2 if active_pop <= 10 else 1.0)
        pressure = min(1.0, (scale * queue_size) / active_pop)
        
        # Determine modes
        if pressure >= balanced_high:
            balanced_mode = "HIGH"
        elif pressure >= balanced_mod:
            balanced_mode = "MODERATE"
        else:
            balanced_mode = "LOW"
        
        if pressure >= aggressive_high:
            aggressive_mode = "HIGH"
        elif pressure >= aggressive_mod:
            aggressive_mode = "MODERATE"
        else:
            aggressive_mode = "LOW"
        
        mode_diff = " <-- Different!" if balanced_mode != aggressive_mode else ""
        
        print(f"{queue_size:<12} {active_pop:<12} {pressure:<12.3f} {balanced_mode:<20} {aggressive_mode:<20}{mode_diff}")


def analyze_wait_priority():
    """Show how wait time priority differs"""
    print("\n" + "=" * 80)
    print("WAIT TIME PRIORITY COMPARISON")
    print("=" * 80)
    print()
    
    # Balanced: coefficient=20, exponent=1.25
    # Aggressive: coefficient=60, exponent=1.5
    
    print(f"{'Wait Cycles':<15} {'Balanced Priority':<20} {'Aggressive Priority':<20} {'Ratio (Agg/Bal)':<20}")
    print("-" * 80)
    
    for cycles in [0, 1, 2, 3, 5, 7, 10, 15]:
        balanced_priority = 20 * (cycles ** 1.25)
        aggressive_priority = 60 * (cycles ** 1.5)
        
        ratio = aggressive_priority / balanced_priority if balanced_priority > 0 else 0
        
        print(f"{cycles:<15} {balanced_priority:<20.1f} {aggressive_priority:<20.1f} {ratio:<20.2f}x")


def calculate_match_probability():
    """Estimate match probability at different wait times"""
    print("\n" + "=" * 80)
    print("ESTIMATED MATCH PROBABILITY")
    print("=" * 80)
    print()
    print("For a player with 1500 MMR in MODERATE pressure (10 players in queue):")
    print()
    
    # Assume 10 potential matches with MMR spread
    # Balanced: base=100, growth=35
    # Aggressive: base=120, growth=50
    
    potential_matches_mmr = [1400, 1420, 1450, 1480, 1520, 1550, 1580, 1600, 1650, 1700]
    player_mmr = 1500
    
    print(f"{'Wait Cycles':<15} {'Balanced Matches':<20} {'Aggressive Matches':<20} {'Improvement':<15}")
    print("-" * 80)
    
    for cycles in [0, 1, 2, 3, 5, 10]:
        balanced_window = 100 + (cycles * 35)
        aggressive_window = 120 + (cycles * 50)
        
        balanced_count = sum(1 for mmr in potential_matches_mmr if abs(player_mmr - mmr) <= balanced_window)
        aggressive_count = sum(1 for mmr in potential_matches_mmr if abs(player_mmr - mmr) <= aggressive_window)
        
        improvement = aggressive_count - balanced_count
        
        print(f"{cycles:<15} {balanced_count:<20} {aggressive_count:<20} {improvement:+<15}")


def main():
    print("\n")
    print("=" * 80)
    print("  AGGRESSIVE FAIRNESS: DETAILED IMPACT ANALYSIS")
    print("=" * 80)
    print()
    print("This analysis shows exactly when and how 'Aggressive Fairness' differs")
    print("from 'Balanced' configuration.")
    print()
    
    analyze_pressure_thresholds()
    analyze_mmr_windows()
    analyze_wait_priority()
    calculate_match_probability()
    
    print("\n" + "=" * 80)
    print("KEY INSIGHTS")
    print("=" * 80)
    print()
    print("1. PRESSURE TRIGGERING:")
    print("   - Aggressive triggers MODERATE at 5% queue (vs 10% balanced)")
    print("   - Aggressive triggers HIGH at 12% queue (vs 20% balanced)")
    print("   - Effect: Tighter MMR windows activate sooner in aggressive mode")
    print()
    print("2. MMR WINDOW EXPANSION:")
    print("   - At wave 10 in LOW pressure:")
    print("     * Balanced: 125 + 10×45 = 575 MMR window")
    print("     * Aggressive: 160 + 10×70 = 860 MMR window (+49% wider!)")
    print("   - Long-waiting players have MUCH wider windows in aggressive mode")
    print()
    print("3. WAIT TIME PRIORITY:")
    print("   - At 10 wait cycles:")
    print("     * Balanced: 20 × 10^1.25 = 356 priority bonus")
    print("     * Aggressive: 60 × 10^1.5 = 1,897 priority bonus (5.3x higher!)")
    print("   - Long-waiters are heavily prioritized in aggressive mode")
    print()
    print("4. WHEN AGGRESSIVE HELPS:")
    print("   - Small queues with high variance in MMR")
    print("   - Players waiting 5+ waves")
    print("   - When ensuring EVERYONE matches is more important than quality")
    print()
    print("5. WHEN BALANCED IS BETTER:")
    print("   - Larger queues (15+ players) where matches happen naturally")
    print("   - When match quality is important")
    print("   - Most players match within 1-3 waves anyway")
    print()
    print("RECOMMENDATION:")
    print("  Use BALANCED for launch (20-30 players expected)")
    print("  Consider AGGRESSIVE if:")
    print("    - Queue regularly drops below 10 players")
    print("    - Players consistently wait 5+ waves")
    print("    - Community prioritizes 'everyone plays' over 'fair matches'")
    print()


if __name__ == "__main__":
    main()

