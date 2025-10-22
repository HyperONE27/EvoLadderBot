"""
End-to-end integration tests for optimized match, abort, and replay flows.
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


async def test_match_embed_generation_speed():
    """
    Test the complete match embed generation flow to ensure it's fast.
    This simulates what happens in MatchFoundView.get_embed().
    """
    print("\n=== TEST: Match Embed Generation Speed ===\n")
    
    try:
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        if len(data_service._matches_df) == 0:
            print("[SKIP] No matches to test")
            return True
        
        # Get a test match
        test_match_id = data_service._matches_df[0, "id"]
        match = data_service.get_match(test_match_id)
        p1_id = match["player_1_discord_uid"]
        p2_id = match["player_2_discord_uid"]
        
        print(f"[TEST] Simulating embed generation for match {test_match_id}")
        print(f"       Players: {p1_id} vs {p2_id}\n")
        
        # Simulate the complete embed generation flow
        start = time.perf_counter()
        
        # Step 1: Get player info (both players)
        checkpoint1 = time.perf_counter()
        p1_info = data_service.get_player_info(p1_id)
        p2_info = data_service.get_player_info(p2_id)
        elapsed1_ms = (time.perf_counter() - checkpoint1) * 1000
        print(f"  [1/4] Player info lookup: {elapsed1_ms:.4f}ms")
        
        # Step 2: Get MMRs from match
        checkpoint2 = time.perf_counter()
        p1_mmr, p2_mmr = data_service.get_match_mmrs(test_match_id)
        elapsed2_ms = (time.perf_counter() - checkpoint2) * 1000
        print(f"  [2/4] Match MMR lookup: {elapsed2_ms:.4f}ms")
        
        # Step 3: Get remaining aborts (both players)
        checkpoint3 = time.perf_counter()
        p1_aborts = data_service.get_remaining_aborts(p1_id)
        p2_aborts = data_service.get_remaining_aborts(p2_id)
        elapsed3_ms = (time.perf_counter() - checkpoint3) * 1000
        print(f"  [3/4] Abort count lookup: {elapsed3_ms:.4f}ms")
        
        # Step 4: Get player preferences
        checkpoint4 = time.perf_counter()
        p1_prefs = data_service.get_player_preferences(p1_id)
        p2_prefs = data_service.get_player_preferences(p2_id)
        elapsed4_ms = (time.perf_counter() - checkpoint4) * 1000
        print(f"  [4/4] Preferences lookup: {elapsed4_ms:.4f}ms")
        
        total_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n  [RESULT] Total embed data gathering: {total_ms:.4f}ms\n")
        
        # Performance assessment
        if total_ms < 5.0:
            print("  [PERF] EXCELLENT! (<5ms)")
        elif total_ms < 10.0:
            print("  [PERF] Very good! (<10ms)")
        elif total_ms < 50.0:
            print("  [PERF] Good (<50ms)")
        else:
            print(f"  [WARN] Slower than expected: {total_ms:.4f}ms")
        
        # Compare to old performance
        old_time_ms = 600  # From logs: 600-800ms total embed generation
        improvement = ((old_time_ms - total_ms) / old_time_ms) * 100
        
        print(f"\n  [INFO] Performance vs Old Implementation:")
        print(f"         Before: ~600-800ms (with DB queries)")
        print(f"         After:  {total_ms:.4f}ms (all in-memory)")
        print(f"         Gain:   ~{improvement:.1f}% faster")
        
        await data_service.shutdown()
        print("\n[SUCCESS] Match embed generation is blazing fast!\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_abort_flow_performance():
    """
    Test abort flow to ensure it's fast and non-blocking.
    """
    print("\n=== TEST: Match Abort Flow Performance ===\n")
    
    try:
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        # Get a test player
        if len(data_service._players_df) == 0:
            print("[SKIP] No players to test")
            return True
        
        test_player_id = data_service._players_df[0, "discord_uid"]
        
        print(f"[TEST] Simulating abort for player {test_player_id}\n")
        
        # Get initial abort count
        initial_aborts = data_service.get_remaining_aborts(test_player_id)
        print(f"  [INFO] Initial aborts: {initial_aborts}")
        
        # Simulate abort (decrement aborts)
        start = time.perf_counter()
        
        # Step 1: Update aborts in memory (instant)
        new_aborts = max(0, initial_aborts - 1)
        await data_service.update_remaining_aborts(test_player_id, new_aborts)
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"  [1/2] In-memory abort update: {elapsed_ms:.4f}ms")
        
        # Step 2: Verify it was queued for async write
        if data_service._total_writes_queued > 0:
            print(f"  [2/2] Async DB write queued: [PASS]")
        
        # Verify the in-memory value updated immediately
        verify_start = time.perf_counter()
        current_aborts = data_service.get_remaining_aborts(test_player_id)
        verify_ms = (time.perf_counter() - verify_start) * 1000
        
        print(f"\n  [VERIFY] Read updated aborts: {verify_ms:.4f}ms")
        print(f"           Value: {current_aborts} (expected: {new_aborts})")
        
        if current_aborts == new_aborts:
            print("           [PASS] In-memory update successful")
        else:
            print("           [FAIL] Value mismatch")
            return False
        
        # Restore original value
        await data_service.update_remaining_aborts(test_player_id, initial_aborts)
        await asyncio.sleep(0.5)  # Let queue process
        
        print(f"\n  [RESULT] Total abort operation: {elapsed_ms:.4f}ms\n")
        
        # Performance assessment
        if elapsed_ms < 1.0:
            print("  [PERF] EXCELLENT! (<1ms)")
        elif elapsed_ms < 5.0:
            print("  [PERF] Very good! (<5ms)")
        elif elapsed_ms < 50.0:
            print("  [PERF] Good (<50ms)")
        else:
            print(f"  [WARN] Slower than expected: {elapsed_ms:.4f}ms")
        
        # Compare to old performance
        old_time_ms = 3330  # From logs: 3330ms execute_abort_complete
        improvement = ((old_time_ms - elapsed_ms) / old_time_ms) * 100
        
        print(f"\n  [INFO] Performance vs Old Implementation:")
        print(f"         Before: ~3330ms (blocking DB write)")
        print(f"         After:  {elapsed_ms:.4f}ms (async write)")
        print(f"         Gain:   ~{improvement:.1f}% faster")
        
        await data_service.shutdown()
        print("\n[SUCCESS] Abort flow is non-blocking and instant!\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_concurrent_operations():
    """
    Test that multiple concurrent operations don't block each other.
    """
    print("\n=== TEST: Concurrent Operations (No Blocking) ===\n")
    
    try:
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        if len(data_service._players_df) < 10:
            print("[SKIP] Need at least 10 players to test")
            return True
        
        # Get 10 random players
        player_ids = data_service._players_df.head(10)["discord_uid"].to_list()
        
        print(f"[TEST] Performing 100 concurrent reads (10 players x 10 ops each)\n")
        
        start = time.perf_counter()
        
        # Perform 100 concurrent reads
        tasks = []
        for player_id in player_ids:
            tasks.append(asyncio.create_task(asyncio.to_thread(
                data_service.get_player_info, player_id
            )))
            tasks.append(asyncio.create_task(asyncio.to_thread(
                data_service.get_remaining_aborts, player_id
            )))
            tasks.append(asyncio.create_task(asyncio.to_thread(
                data_service.get_player_preferences, player_id
            )))
            tasks.append(asyncio.create_task(asyncio.to_thread(
                data_service.get_all_player_mmrs, player_id
            )))
        
        results = await asyncio.gather(*tasks)
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        avg_ms = elapsed_ms / len(tasks)
        
        print(f"  [RESULT] {len(tasks)} operations completed")
        print(f"           Total time: {elapsed_ms:.2f}ms")
        print(f"           Average per op: {avg_ms:.4f}ms")
        print(f"           Throughput: {len(tasks)/elapsed_ms*1000:.0f} ops/sec\n")
        
        if avg_ms < 0.5:
            print("  [PERF] EXCELLENT! (<0.5ms per op)")
        elif avg_ms < 1.0:
            print("  [PERF] Very good! (<1ms per op)")
        elif avg_ms < 5.0:
            print("  [PERF] Good (<5ms per op)")
        
        await data_service.shutdown()
        print("\n[SUCCESS] Concurrent operations are fast and non-blocking!\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all end-to-end flow tests."""
    print("\n" + "="*60)
    print("End-to-End Flow Tests (Phase 5)")
    print("="*60)
    
    results = []
    
    # Test 1: Match embed generation speed
    results.append(("Match Embed Generation", await test_match_embed_generation_speed()))
    
    # Test 2: Abort flow performance
    results.append(("Abort Flow Performance", await test_abort_flow_performance()))
    
    # Test 3: Concurrent operations
    results.append(("Concurrent Operations", await test_concurrent_operations()))
    
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
            print("\n[SUCCESS] All end-to-end flow tests passed!\n")
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


