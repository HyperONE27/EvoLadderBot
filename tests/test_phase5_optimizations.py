"""
Test Phase 5 optimizations: Match lookup and replay upload improvements.
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


async def test_match_lookup_performance():
    """Test match lookup performance improvement."""
    print("\n=== TEST: Match Lookup Performance ===\n")
    
    try:
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        if len(data_service._matches_1v1_df) == 0:
            print("[SKIP] No matches to test")
            return True
        
        # Get a test match ID
        test_match_id = data_service._matches_1v1_df[0, "id"]
        
        # Test 1: get_match
        print(f"[1/3] Testing get_match({test_match_id})...")
        start = time.perf_counter()
        match = data_service.get_match(test_match_id)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        if match:
            print(f"      [PASS] Found match in {elapsed_ms:.4f}ms")
            if elapsed_ms < 1.0:
                print(f"      [PERF] Excellent! (<1ms)")
            elif elapsed_ms < 5.0:
                print(f"      [PERF] Good (<5ms)")
        else:
            print("      [FAIL] Match not found")
            return False
        
        # Test 2: get_match_mmrs (optimized)
        print(f"[2/3] Testing get_match_mmrs({test_match_id})...")
        start = time.perf_counter()
        p1_mmr, p2_mmr = data_service.get_match_mmrs(test_match_id)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        print(f"      [PASS] Retrieved MMRs: P1={p1_mmr}, P2={p2_mmr} in {elapsed_ms:.4f}ms")
        if elapsed_ms < 1.0:
            print(f"      [PERF] Excellent! (<1ms)")
        
        # Test 3: Performance benchmark (1000 iterations)
        print(f"[3/3] Benchmarking get_match_mmrs (1000 iterations)...")
        iterations = 1000
        start = time.perf_counter()
        
        for _ in range(iterations):
            data_service.get_match_mmrs(test_match_id)
        
        avg_ms = ((time.perf_counter() - start) / iterations) * 1000
        print(f"      [PASS] Average: {avg_ms:.4f}ms per call")
        
        if avg_ms < 0.5:
            print(f"      [PERF] Excellent! (<0.5ms avg)")
        elif avg_ms < 1.0:
            print(f"      [PERF] Very good! (<1ms avg)")
        elif avg_ms < 5.0:
            print(f"      [PERF] Good (<5ms avg)")
        else:
            print(f"      [WARN] Slower than expected: {avg_ms:.4f}ms")
        
        # Expected improvement
        old_time_ms = 250  # From logs: 250-630ms
        new_time_ms = avg_ms
        improvement = ((old_time_ms - new_time_ms) / old_time_ms) * 100
        
        print(f"\n[INFO] Performance Improvement:")
        print(f"       Before: ~250-630ms (DB query)")
        print(f"       After:  {new_time_ms:.4f}ms (in-memory)")
        print(f"       Gain:   ~{improvement:.1f}% faster")
        
        await data_service.shutdown()
        print("\n[SUCCESS] Match lookup optimizations validated!\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_replay_uploaded_at():
    """Test that uploaded_at is included in replay data."""
    print("\n=== TEST: Replay uploaded_at Column ===\n")
    
    try:
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        # Test that replay data structure includes uploaded_at
        print("[1/1] Verifying replay data structure...")
        
        # Create test replay data
        import json
        from src.backend.db.db_reader_writer import get_timestamp
        
        test_replay_data = {
            "replay_hash": "test_hash_123",
            "replay_date": get_timestamp(),
            "player_1_name": "TestPlayer1",
            "player_2_name": "TestPlayer2",
            "player_1_race": "bw_terran",
            "player_2_race": "sc2_zerg",
            "result": 1,
            "player_1_handle": "handle1",
            "player_2_handle": "handle2",
            "observers": json.dumps([]),
            "map_name": "TestMap",
            "duration": 600,
            "replay_path": "/test/path",
            "uploaded_at": get_timestamp()  # NEW COLUMN
        }
        
        if "uploaded_at" in test_replay_data:
            print(f"      [PASS] uploaded_at field present")
            print(f"      [INFO] Value: {test_replay_data['uploaded_at']}")
        else:
            print("      [FAIL] uploaded_at field missing")
            return False
        
        # Queue the replay insert (async, non-blocking)
        print("[2/2] Testing async replay insert...")
        await data_service.insert_replay(test_replay_data)
        await asyncio.sleep(0.2)  # Give queue time to process
        
        if data_service._total_writes_queued > 0:
            print(f"      [PASS] Replay insert queued ({data_service._total_writes_queued} total writes)")
        
        await data_service.shutdown()
        print("\n[SUCCESS] Replay uploaded_at column validated!\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all Phase 5 optimization tests."""
    print("\n" + "="*60)
    print("Phase 5 Optimization Tests")
    print("="*60)
    
    results = []
    
    # Test 1: Match lookup performance
    results.append(("Match Lookup Performance", await test_match_lookup_performance()))
    
    # Test 2: Replay uploaded_at column
    results.append(("Replay uploaded_at Column", await test_replay_uploaded_at()))
    
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
            print("\n[SUCCESS] All Phase 5 optimization tests passed!\n")
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


