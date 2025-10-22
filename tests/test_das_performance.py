"""
Test performance of DataAccessService.
"""

import asyncio
import os
import sys
import time

os.system("chcp 65001 > nul")

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.backend.services.data_access_service import DataAccessService
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS


async def test_performance():
    """Test read performance."""
    print("\n=== Performance Test ===\n")
    
    try:
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        # Get a test UID
        if len(data_service._players_df) == 0:
            print("[SKIP] No players to test")
            return True
        
        test_uid = data_service._players_df[0, "discord_uid"]
        iterations = 1000
        
        # Benchmark 1: Player info
        print(f"[1/3] Benchmarking player_info ({iterations} iterations)...")
        start = time.perf_counter()
        for _ in range(iterations):
            data_service.get_player_info(test_uid)
        elapsed = (time.perf_counter() - start) * 1000 / iterations
        print(f"      [PASS] {elapsed:.4f}ms avg")
        
        # Benchmark 2: player_exists
        print(f"[2/3] Benchmarking player_exists ({iterations} iterations)...")
        start = time.perf_counter()
        for _ in range(iterations):
            data_service.player_exists(test_uid)
        elapsed = (time.perf_counter() - start) * 1000 / iterations
        print(f"      [PASS] {elapsed:.4f}ms avg")
        
        # Benchmark 3: MMR lookup
        if len(data_service._mmrs_df) > 0:
            test_uid = data_service._mmrs_df[0, "discord_uid"]
            test_race = data_service._mmrs_df[0, "race"]
            
            print(f"[3/3] Benchmarking MMR lookup ({iterations} iterations)...")
            start = time.perf_counter()
            for _ in range(iterations):
                data_service.get_player_mmr(test_uid, test_race)
            elapsed = (time.perf_counter() - start) * 1000 / iterations
            print(f"      [PASS] {elapsed:.4f}ms avg")
        else:
            print("[3/3] No MMRs to benchmark")
        
        await data_service.shutdown()
        print("\n[SUCCESS] Performance tests complete! [PASS]\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
        success = asyncio.run(test_performance())
        close_pool()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[FATAL] {e}")
        close_pool()
        sys.exit(1)

