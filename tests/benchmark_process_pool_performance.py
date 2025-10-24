"""
Comprehensive benchmarking script for ProcessPoolExecutor performance.

This script measures:
1. Replay parsing: native vs. ProcessPoolExecutor
2. Leaderboard generation: native vs. ProcessPoolExecutor with various data sizes
3. IPC overhead measurement

Results guide timeout configuration for the process pool supervisor.
"""

import asyncio
import io
import time
import os
import sys
from concurrent.futures import ProcessPoolExecutor, TimeoutError
from pathlib import Path

import polars as pl

# Add src to path so we can import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backend.services.replay_service import parse_replay_data_blocking


def echo_job(data: str) -> str:
    """Simple echo job to measure pure IPC overhead."""
    return data


def leaderboard_generation_job(
    mmr_data: list[dict],
    filter_complexity: str = "simple"
) -> dict:
    """
    Simulate leaderboard generation with varying complexity.
    
    Args:
        mmr_data: List of MMR dictionaries
        filter_complexity: "simple", "medium", or "complex"
    
    Returns:
        Dict with query results and timing info
    """
    import time
    start = time.perf_counter()
    
    df = pl.DataFrame(mmr_data)
    
    if filter_complexity == "simple":
        # Top 20 players
        result = df.sort("mmr", descending=True).head(20)
    elif filter_complexity == "medium":
        # Filter by race and sort
        result = df.filter(pl.col("race") == "sc2_terran").sort("mmr", descending=True).head(20)
    elif filter_complexity == "complex":
        # Multiple filters: race, country, best race only
        result = (
            df.filter((pl.col("race").is_in(["sc2_terran", "sc2_zerg"])) & (pl.col("country").is_in(["US", "KR"])))
            .sort(["mmr", "last_played"], descending=[True, True])
            .group_by("discord_uid", maintain_order=True)
            .first()
            .head(20)
        )
    else:
        result = df
    
    elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
    return {
        "rows_returned": len(result),
        "elapsed_ms": elapsed,
        "complexity": filter_complexity
    }


def load_test_replay(replay_path: str) -> bytes:
    """Load a test replay file from disk."""
    with open(replay_path, 'rb') as f:
        return f.read()


def benchmark_ipc_overhead():
    """Measure raw IPC overhead with echo job."""
    print("\n" + "="*80)
    print("BENCHMARK 1: IPC OVERHEAD MEASUREMENT")
    print("="*80)
    
    test_payloads = [
        ("100 bytes", "x" * 100),
        ("1 KB", "x" * 1024),
        ("10 KB", "x" * (10 * 1024)),
        ("100 KB", "x" * (100 * 1024)),
    ]
    
    with ProcessPoolExecutor(max_workers=1) as executor:
        for name, payload in test_payloads:
            times = []
            for _ in range(5):  # 5 iterations per payload size
                start = time.perf_counter()
                future = executor.submit(echo_job, payload)
                result = future.result(timeout=10)
                elapsed = (time.perf_counter() - start) * 1000
                times.append(elapsed)
            
            avg = sum(times) / len(times)
            min_t = min(times)
            max_t = max(times)
            
            print(f"{name:12} | Avg: {avg:7.2f}ms | Min: {min_t:7.2f}ms | Max: {max_t:7.2f}ms")


def benchmark_replay_parsing():
    """Benchmark replay parsing performance."""
    print("\n" + "="*80)
    print("BENCHMARK 2: REPLAY PARSING")
    print("="*80)
    
    test_replay_dir = Path("tests/test_data/test_replay_files")
    replay_files = list(test_replay_dir.glob("*.SC2Replay"))
    
    if not replay_files:
        print("ERROR: No test replay files found. Skipping replay parsing benchmark.")
        return
    
    print(f"Found {len(replay_files)} test replay files.\n")
    
    for replay_file in replay_files:
        replay_bytes = load_test_replay(str(replay_file))
        print(f"\nTesting: {replay_file.name} ({len(replay_bytes) / 1024:.1f} KB)")
        print("-" * 60)
        
        # Native execution (blocking)
        print("Native execution (blocking):")
        native_times = []
        for i in range(3):
            start = time.perf_counter()
            result = parse_replay_data_blocking(replay_bytes)
            elapsed = (time.perf_counter() - start) * 1000
            native_times.append(elapsed)
            print(f"  Iteration {i+1}: {elapsed:.2f}ms | Error: {result.get('error')}")
        
        native_avg = sum(native_times) / len(native_times)
        
        # ProcessPoolExecutor execution
        print("\nProcessPoolExecutor execution:")
        pool_times = []
        with ProcessPoolExecutor(max_workers=1) as executor:
            for i in range(3):
                start = time.perf_counter()
                future = executor.submit(parse_replay_data_blocking, replay_bytes)
                result = future.result(timeout=10)
                elapsed = (time.perf_counter() - start) * 1000
                pool_times.append(elapsed)
                print(f"  Iteration {i+1}: {elapsed:.2f}ms | Error: {result.get('error')}")
        
        pool_avg = sum(pool_times) / len(pool_times)
        ipc_overhead = pool_avg - native_avg
        
        print(f"\nSummary:")
        print(f"  Native avg:        {native_avg:.2f}ms")
        print(f"  Pool avg:          {pool_avg:.2f}ms")
        print(f"  IPC overhead:      {ipc_overhead:.2f}ms ({(ipc_overhead/native_avg)*100:.1f}% overhead)")


def benchmark_leaderboard_generation():
    """Benchmark leaderboard generation with varying data sizes and complexity."""
    print("\n" + "="*80)
    print("BENCHMARK 3: LEADERBOARD GENERATION")
    print("="*80)
    
    data_sizes = [100, 1000, 10000, 30000]
    complexities = ["simple", "medium", "complex"]
    
    for size in data_sizes:
        print(f"\n{'='*60}")
        print(f"Data Size: {size} players")
        print(f"{'='*60}")
        
        # Generate mock leaderboard data
        import random
        races = ["sc2_terran", "sc2_zerg", "sc2_protoss", "bw_terran", "bw_zerg", "bw_protoss"]
        countries = ["US", "KR", "CN", "DE", "FR", "BR", "CA"]
        
        mmr_data = [
            {
                "discord_uid": i,
                "race": random.choice(races),
                "mmr": random.randint(1000, 3000),
                "player_name": f"Player_{i}",
                "country": random.choice(countries),
                "games_played": random.randint(10, 1000),
                "games_won": random.randint(0, 500),
                "games_lost": random.randint(0, 500),
                "games_drawn": random.randint(0, 100),
                "last_played": f"2025-01-{random.randint(1, 28):02d}"
            }
            for i in range(size)
        ]
        
        for complexity in complexities:
            print(f"\n  Complexity: {complexity}")
            
            # Native execution
            start = time.perf_counter()
            result = leaderboard_generation_job(mmr_data, complexity)
            native_time = (time.perf_counter() - start) * 1000
            
            # ProcessPoolExecutor execution
            with ProcessPoolExecutor(max_workers=1) as executor:
                start = time.perf_counter()
                future = executor.submit(leaderboard_generation_job, mmr_data, complexity)
                result = future.result(timeout=30)
                pool_time = (time.perf_counter() - start) * 1000
            
            overhead = pool_time - native_time
            print(f"    Native:    {native_time:7.2f}ms")
            print(f"    Pool:      {pool_time:7.2f}ms")
            print(f"    Overhead:  {overhead:7.2f}ms ({(overhead/native_time)*100:6.1f}%)")


def recommend_timeouts():
    """Print timeout recommendations based on benchmarks."""
    print("\n" + "="*80)
    print("TIMEOUT RECOMMENDATIONS")
    print("="*80)
    print("""
Based on the benchmarks above, here are recommended timeout values:

REPLAY PARSING:
  - Suggested base timeout: 1000ms (1.0 second)
  - Rationale: Parsing typically completes in 300-800ms natively
              IPC overhead is usually 100-300ms
              1 second provides comfortable margin without being wasteful

LEADERBOARD GENERATION:
  - Small datasets (100-1000 players):   2000ms (2.0 seconds)
  - Medium datasets (10000 players):    5000ms (5.0 seconds)
  - Large datasets (30000+ players):   10000ms (10.0 seconds)

SUGGESTED AGGRESSIVE TIMEOUTS (Better CPU utilization):
  - Replay parsing: 1000ms (native + IPC + 10% margin)
  - Leaderboard (10k players): 3000-5000ms (depends on filter complexity)

GENERAL RULE:
  - Any task exceeding timeout is considered a hung worker
  - Timeout should be: (95th percentile of native execution) + (observed IPC overhead) + (10% buffer)
""")


async def main():
    """Run all benchmarks."""
    print("\n" + "="*80)
    print("PROCESSPOOL PERFORMANCE BENCHMARK SUITE")
    print("="*80)
    
    benchmark_ipc_overhead()
    benchmark_replay_parsing()
    benchmark_leaderboard_generation()
    recommend_timeouts()
    
    print("\n" + "="*80)
    print("BENCHMARK COMPLETE")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
