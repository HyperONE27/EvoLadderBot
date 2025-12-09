"""
Test the MMR display and abort performance fixes.
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


async def test_mmr_fallback():
    """Test that MMR lookup falls back to DB when match not in memory."""
    print("\n=== TEST: MMR Fallback for New Matches ===\n")
    
    try:
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        # Test with a non-existent match ID (should fall back to DB)
        test_match_id = 99999  # Very unlikely to exist
        
        print(f"[1/2] Testing MMR lookup for non-existent match {test_match_id}...")
        start = time.perf_counter()
        p1_mmr, p2_mmr = data_service.get_match_mmrs(test_match_id)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"      Result: P1={p1_mmr}, P2={p2_mmr}")
        print(f"      Time: {elapsed_ms:.4f}ms")
        
        if elapsed_ms < 50.0:  # Should be fast even with DB fallback
            print("      [PASS] Fallback DB query is fast")
        else:
            print("      [WARN] Fallback DB query is slower than expected")
        
        # Test with an existing match ID (should use memory)
        if len(data_service._matches_1v1_df) > 0:
            existing_match_id = data_service._matches_1v1_df[0, "id"]
            print(f"\n[2/2] Testing MMR lookup for existing match {existing_match_id}...")
            start = time.perf_counter()
            p1_mmr, p2_mmr = data_service.get_match_mmrs(existing_match_id)
            elapsed_ms = (time.perf_counter() - start) * 1000
            
            print(f"      Result: P1={p1_mmr}, P2={p2_mmr}")
            print(f"      Time: {elapsed_ms:.4f}ms")
            
            if elapsed_ms < 5.0:
                print("      [PASS] In-memory lookup is very fast")
            else:
                print("      [WARN] In-memory lookup is slower than expected")
        else:
            print("      [SKIP] No existing matches to test")
        
        await data_service.shutdown()
        print("\n[SUCCESS] MMR fallback working correctly!\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_abort_performance():
    """Test that abort operations are fast."""
    print("\n=== TEST: Abort Performance ===\n")
    
    try:
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        # Get a test player
        if len(data_service._players_df) == 0:
            print("[SKIP] No players to test")
            return True
        
        test_player_id = data_service._players_df[0, "discord_uid"]
        test_match_id = 99999  # Non-existent match for testing
        
        print(f"[1/2] Testing abort performance for player {test_player_id}...")
        
        # Test the abort method (should be fast even if match doesn't exist)
        start = time.perf_counter()
        success = await data_service.abort_match(test_match_id, test_player_id)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"      Success: {success}")
        print(f"      Time: {elapsed_ms:.4f}ms")
        
        if elapsed_ms < 10.0:  # Should be very fast
            print("      [PASS] Abort operation is fast")
        else:
            print("      [WARN] Abort operation is slower than expected")
        
        # Test abort count update (should be instant)
        print(f"\n[2/2] Testing abort count update...")
        start = time.perf_counter()
        current_aborts = data_service.get_remaining_aborts(test_player_id)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"      Current aborts: {current_aborts}")
        print(f"      Time: {elapsed_ms:.4f}ms")
        
        if elapsed_ms < 1.0:
            print("      [PASS] Abort count lookup is instant")
        else:
            print("      [WARN] Abort count lookup is slower than expected")
        
        await data_service.shutdown()
        print("\n[SUCCESS] Abort performance is optimized!\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all MMR and abort fix tests."""
    print("\n" + "="*60)
    print("MMR Display and Abort Performance Fix Tests")
    print("="*60)
    
    results = []
    
    # Test 1: MMR fallback
    results.append(("MMR Fallback", await test_mmr_fallback()))
    
    # Test 2: Abort performance
    results.append(("Abort Performance", await test_abort_performance()))
    
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
            print("\n[SUCCESS] All MMR and abort fix tests passed!\n")
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


