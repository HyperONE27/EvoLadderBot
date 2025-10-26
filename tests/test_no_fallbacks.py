"""
Test that DataAccessService fails loud instead of using fallbacks.
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


async def test_fail_loud_behavior():
    """Test that DataAccessService fails loud instead of using fallbacks."""
    print("\n=== TEST: Fail Loud Behavior (No Fallbacks) ===\n")
    
    try:
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        # Test 1: MMR lookup for non-existent match should fail loud
        print("[1/3] Testing MMR lookup for non-existent match...")
        try:
            p1_mmr, p2_mmr = data_service.get_match_mmrs(99999)
            print(f"      [FAIL] Should have raised ValueError, got: P1={p1_mmr}, P2={p2_mmr}")
            return False
        except ValueError as e:
            print(f"      [PASS] Correctly raised ValueError: {e}")
        except Exception as e:
            print(f"      [FAIL] Raised wrong exception: {e}")
            return False
        
        # Test 2: Match lookup for non-existent match should return None (not fail)
        print("\n[2/3] Testing match lookup for non-existent match...")
        match = data_service.get_match(99999)
        if match is None:
            print("      [PASS] Correctly returned None for non-existent match")
        else:
            print(f"      [FAIL] Should have returned None, got: {match}")
            return False
        
        # Test 3: MMR lookup for existing match should work fast
        if len(data_service._matches_1v1_df) > 0:
            existing_match_id = data_service._matches_1v1_df[0, "id"]
            print(f"\n[3/3] Testing MMR lookup for existing match {existing_match_id}...")
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
            print("\n[3/3] [SKIP] No existing matches to test")
        
        await data_service.shutdown()
        print("\n[SUCCESS] Fail loud behavior working correctly!\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_match_creation_flow():
    """Test that matches are created in memory first."""
    print("\n=== TEST: Match Creation in Memory ===\n")
    
    try:
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        # Test creating a match
        print("[1/2] Testing match creation...")
        test_match_data = {
            'player_1_discord_uid': 123456789,
            'player_2_discord_uid': 987654321,
            'player_1_race': 'bw_terran',
            'player_2_race': 'sc2_zerg',
            'map_played': 'TestMap',
            'server_choice': 'TestServer',
            'player_1_mmr': 1500,
            'player_2_mmr': 1600,
            'mmr_change': 0
        }
        
        match_id = await data_service.create_match(test_match_data)
        print(f"      Created match ID: {match_id}")
        
        # Test that we can immediately read the match from memory
        print("\n[2/2] Testing immediate read from memory...")
        start = time.perf_counter()
        match = data_service.get_match(match_id)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        if match:
            print(f"      [PASS] Match found in memory: ID={match['id']}")
            print(f"      Time: {elapsed_ms:.4f}ms")
            
            if elapsed_ms < 1.0:
                print("      [PASS] Read from memory is instant")
            else:
                print("      [WARN] Read from memory is slower than expected")
        else:
            print("      [FAIL] Match not found in memory after creation")
            return False
        
        await data_service.shutdown()
        print("\n[SUCCESS] Match creation in memory working correctly!\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all no-fallback tests."""
    print("\n" + "="*60)
    print("No Fallbacks - Fail Loud Tests")
    print("="*60)
    
    results = []
    
    # Test 1: Fail loud behavior
    results.append(("Fail Loud Behavior", await test_fail_loud_behavior()))
    
    # Test 2: Match creation in memory
    results.append(("Match Creation in Memory", await test_match_creation_flow()))
    
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
            print("\n[SUCCESS] All no-fallback tests passed!\n")
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


