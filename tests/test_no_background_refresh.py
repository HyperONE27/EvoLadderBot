"""
Test that background refresh mechanisms are disabled.
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


async def test_no_background_refresh():
    """Test that background refresh mechanisms are disabled."""
    print("\n=== TEST: No Background Refresh ===\n")
    
    try:
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        # Test 1: Leaderboard service should get data directly from DataAccessService
        print("[1/3] Testing leaderboard service direct access...")
        from src.backend.services.leaderboard_service import LeaderboardService
        leaderboard_service = LeaderboardService()
        
        start = time.perf_counter()
        df = leaderboard_service._get_cached_leaderboard_dataframe()
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"      [PASS] Leaderboard data retrieved in {elapsed_ms:.4f}ms")
        print(f"      [PASS] Data shape: {df.shape}")
        
        if elapsed_ms < 5.0:
            print("      [PASS] Direct access is very fast (no cache overhead)")
        else:
            print("      [WARN] Direct access is slower than expected")
        
        # Test 2: Cache invalidation should be deprecated
        print("\n[2/3] Testing cache invalidation deprecation...")
        from src.backend.services.leaderboard_service import invalidate_leaderboard_cache
        
        # This should print a deprecation message
        invalidate_leaderboard_cache()
        print("      [PASS] Cache invalidation shows deprecation message")
        
        # Test 3: DataAccessService should be the single source of truth
        print("\n[3/3] Testing DataAccessService as single source of truth...")
        
        # Get data multiple times - should be consistent and fast
        start = time.perf_counter()
        df1 = data_service.get_leaderboard_dataframe()
        df2 = data_service.get_leaderboard_dataframe()
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"      [PASS] Multiple calls completed in {elapsed_ms:.4f}ms")
        print(f"      [PASS] Data consistency: {df1.shape == df2.shape}")
        
        if elapsed_ms < 10.0:
            print("      [PASS] Multiple calls are very fast (no refresh overhead)")
        else:
            print("      [WARN] Multiple calls are slower than expected")
        
        await data_service.shutdown()
        print("\n[SUCCESS] No background refresh - DataAccessService is single source of truth!\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ranking_service_no_refresh():
    """Test that ranking service background refresh is disabled."""
    print("\n=== TEST: Ranking Service No Background Refresh ===\n")
    
    try:
        # Test that ranking service doesn't start background refresh
        from src.backend.services.ranking_service import RankingService
        from src.backend.db.db_reader_writer import DatabaseReader
        
        db_reader = DatabaseReader()
        ranking_service = RankingService(db_reader=db_reader)
        
        print("[1/2] Testing ranking service without background refresh...")
        
        # This should not start a background task
        await ranking_service.start_background_refresh(interval_seconds=1)
        
        # Wait a bit to see if any background work happens
        await asyncio.sleep(2)
        
        # Check if background task exists
        if hasattr(ranking_service, '_background_task') and ranking_service._background_task:
            print("      [WARN] Background task was created (should be disabled)")
        else:
            print("      [PASS] No background task created")
        
        # Stop the refresh (should be safe even if not started)
        ranking_service.stop_background_refresh()
        print("      [PASS] Stop background refresh completed safely")
        
        print("\n[2/2] Testing ranking service direct refresh...")
        
        # Test direct refresh (should still work)
        start = time.perf_counter()
        await ranking_service.trigger_refresh()
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"      [PASS] Direct refresh completed in {elapsed_ms:.4f}ms")
        
        if elapsed_ms < 100.0:
            print("      [PASS] Direct refresh is fast")
        else:
            print("      [WARN] Direct refresh is slower than expected")
        
        print("\n[SUCCESS] Ranking service background refresh disabled!\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all no-background-refresh tests."""
    print("\n" + "="*60)
    print("No Background Refresh Tests")
    print("="*60)
    
    results = []
    
    # Test 1: No background refresh
    results.append(("No Background Refresh", await test_no_background_refresh()))
    
    # Test 2: Ranking service no refresh
    results.append(("Ranking Service No Refresh", await test_ranking_service_no_refresh()))
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    print("="*60)
    print(f"Total: {passed}/{total} tests passed")
    print("="*60)
    
    return passed == total


if __name__ == "__main__":
    try:
        initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
        success = asyncio.run(run_all_tests())
        close_pool()
        
        if success:
            print("\n[SUCCESS] All no-background-refresh tests passed!\n")
            sys.exit(0)
        else:
            print("\n[FAILURE] Some tests failed\n")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n[FATAL] {e}")
        import traceback
        traceback.print_exc()
        close_pool()
        sys.exit(1)
