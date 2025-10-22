"""
Comprehensive test suite for DataAccessService.

Tests the full integration of the DataAccessService including:
- All hot table operations (players, mmrs, preferences, matches, replays)
- Performance benchmarks
- Write queue functionality
- Integration with other services
- Error handling and edge cases
"""

import asyncio
import os
import sys
import time

# Set console encoding for Windows Unicode compatibility
os.system("chcp 65001 > nul")

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.backend.db.db_reader_writer import DatabaseWriter
from src.backend.services.data_access_service import DataAccessService
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS


# Test UIDs
TEST_PLAYER_UID = 999888777
TEST_PLAYER_UID_2 = 999888778


def _cleanup_test_data():
    """Clean up test data from previous runs."""
    try:
        writer = DatabaseWriter()
        conn = writer.adapter.get_connection()
        cursor = conn.cursor()
        
        # Delete test data in correct order (respecting foreign keys)
        cursor.execute('DELETE FROM mmrs_1v1 WHERE discord_uid IN (%s, %s)', 
                      (TEST_PLAYER_UID, TEST_PLAYER_UID_2))
        cursor.execute('DELETE FROM preferences_1v1 WHERE discord_uid IN (%s, %s)', 
                      (TEST_PLAYER_UID, TEST_PLAYER_UID_2))
        cursor.execute('DELETE FROM players WHERE discord_uid IN (%s, %s)', 
                      (TEST_PLAYER_UID, TEST_PLAYER_UID_2))
        
        conn.commit()
        cursor.close()
        writer.adapter.return_connection(conn)
        print("[Cleanup] Test data cleaned up successfully")
    except Exception as e:
        print(f"[Cleanup] Error during cleanup: {e}")


async def test_initialization():
    """Test DataAccessService initialization."""
    print("\n" + "="*60)
    print("TEST SUITE: Comprehensive DataAccessService Tests")
    print("="*60)
    
    print("\n=== TEST 1: Initialization ===")
    
    try:
        data_service = DataAccessService()
        
        # Initialize async (this loads all tables)
        print("[INFO] Initializing DataAccessService...")
        await data_service.initialize_async()
        
        # Check singleton
        data_service2 = DataAccessService()
        if data_service is data_service2:
            print("[PASS] Singleton pattern working")
        else:
            print("[FAIL] Singleton pattern broken")
            return False
        
        # Check that tables are loaded
        if data_service._players_df is not None:
            player_count = len(data_service._players_df)
            print(f"[PASS] Players table loaded: {player_count} rows")
        else:
            print("[FAIL] Players table not loaded")
            return False
        
        if data_service._mmrs_df is not None:
            mmr_count = len(data_service._mmrs_df)
            print(f"[PASS] MMRs table loaded: {mmr_count} rows")
        else:
            print("[FAIL] MMRs table not loaded")
            return False
        
        print("[PASS] Initialization successful")
        return True
    except Exception as e:
        print(f"[FAIL] Initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_player_operations():
    """Test comprehensive player operations."""
    print("\n=== TEST 2: Player Operations ===")
    
    try:
        data_service = DataAccessService()
        
        # Test 1: Create player
        success = await data_service.create_player(
            discord_uid=TEST_PLAYER_UID,
            discord_username="TestUser1",
            player_name="TestPlayer1",
            country="US"
        )
        
        if not success:
            print("[FAIL] Failed to create player 1")
            return False
        print("[PASS] Player 1 created")
        
        # Test 2: Verify immediate availability
        player = data_service.get_player_info(TEST_PLAYER_UID)
        if player and player.get('player_name') == 'TestPlayer1':
            print("[PASS] Player 1 immediately available in memory")
        else:
            print(f"[FAIL] Player 1 not in memory: {player}")
            return False
        
        # Test 3: Check player_exists
        if data_service.player_exists(TEST_PLAYER_UID):
            print("[PASS] player_exists() working")
        else:
            print("[FAIL] player_exists() not working")
            return False
        
        # Test 4: Update player
        success = await data_service.update_player_info(
            discord_uid=TEST_PLAYER_UID,
            player_name="UpdatedPlayer1",
            country="CA"
        )
        
        if success:
            player = data_service.get_player_info(TEST_PLAYER_UID)
            if player.get('player_name') == 'UpdatedPlayer1' and player.get('country') == 'CA':
                print("[PASS] Player update successful")
            else:
                print(f"[FAIL] Player update not reflected: {player}")
                return False
        else:
            print("[FAIL] Player update failed")
            return False
        
        # Test 5: Remaining aborts
        aborts = data_service.get_remaining_aborts(TEST_PLAYER_UID)
        print(f"[INFO] Player has {aborts} remaining aborts")
        
        success = await data_service.update_remaining_aborts(TEST_PLAYER_UID, 2)
        if success and data_service.get_remaining_aborts(TEST_PLAYER_UID) == 2:
            print("[PASS] Abort count update successful")
        else:
            print("[FAIL] Abort count update failed")
            return False
        
        # Test 6: Create second player
        success = await data_service.create_player(
            discord_uid=TEST_PLAYER_UID_2,
            discord_username="TestUser2",
            player_name="TestPlayer2",
            country="GB"
        )
        
        if success:
            print("[PASS] Player 2 created")
        else:
            print("[FAIL] Failed to create player 2")
            return False
        
        # Give write queue time to process
        await asyncio.sleep(0.5)
        
        print(f"[INFO] Total writes queued: {data_service._total_writes_queued}")
        print("[PASS] All player operations successful")
        return True
        
    except Exception as e:
        print(f"[FAIL] Player operations failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_mmr_operations():
    """Test comprehensive MMR operations."""
    print("\n=== TEST 3: MMR Operations ===")
    
    try:
        data_service = DataAccessService()
        
        # Test 1: Create MMR records for player 1
        races = [("bw_terran", 1500), ("bw_zerg", 1450), ("sc2_protoss", 1600)]
        
        for race, mmr in races:
            success = await data_service.create_or_update_mmr(
                discord_uid=TEST_PLAYER_UID,
                player_name="TestPlayer1",
                race=race,
                mmr=mmr,
                games_played=10,
                games_won=6,
                games_lost=4
            )
            
            if not success:
                print(f"[FAIL] Failed to create MMR for {race}")
                return False
        
        print(f"[PASS] Created {len(races)} MMR records")
        
        # Test 2: Get individual MMR
        mmr = data_service.get_player_mmr(TEST_PLAYER_UID, "bw_terran")
        if mmr == 1500.0:
            print(f"[PASS] Individual MMR lookup: {mmr}")
        else:
            print(f"[FAIL] Individual MMR lookup failed: {mmr}")
            return False
        
        # Test 3: Get all player MMRs
        all_mmrs = data_service.get_all_player_mmrs(TEST_PLAYER_UID)
        if len(all_mmrs) == 3:
            print(f"[PASS] Retrieved all MMRs: {all_mmrs}")
        else:
            print(f"[FAIL] Wrong number of MMRs: {len(all_mmrs)}")
            return False
        
        # Test 4: Update MMR
        success = await data_service.update_player_mmr(
            discord_uid=TEST_PLAYER_UID,
            race="bw_terran",
            new_mmr=1550,
            games_played=11,
            games_won=7
        )
        
        if success:
            mmr = data_service.get_player_mmr(TEST_PLAYER_UID, "bw_terran")
            if mmr == 1550.0:
                print(f"[PASS] MMR update successful: {mmr}")
            else:
                print(f"[FAIL] MMR update not reflected: {mmr}")
                return False
        else:
            print("[FAIL] MMR update failed")
            return False
        
        # Test 5: Create MMRs for player 2
        success = await data_service.create_or_update_mmr(
            discord_uid=TEST_PLAYER_UID_2,
            player_name="TestPlayer2",
            race="sc2_zerg",
            mmr=1700
        )
        
        if success:
            print("[PASS] Player 2 MMR created")
        else:
            print("[FAIL] Failed to create player 2 MMR")
            return False
        
        # Test 6: Get leaderboard dataframe
        leaderboard = data_service.get_leaderboard_dataframe()
        if leaderboard is not None and len(leaderboard) > 0:
            print(f"[PASS] Leaderboard dataframe retrieved: {len(leaderboard)} rows")
        else:
            print("[FAIL] Leaderboard dataframe empty")
            return False
        
        await asyncio.sleep(0.5)
        print("[PASS] All MMR operations successful")
        return True
        
    except Exception as e:
        print(f"[FAIL] MMR operations failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_preferences_operations():
    """Test preferences operations."""
    print("\n=== TEST 4: Preferences Operations ===")
    
    try:
        data_service = DataAccessService()
        
        # Test 1: Create preferences
        success = await data_service.update_player_preferences(
            discord_uid=TEST_PLAYER_UID,
            last_chosen_races='["bw_terran", "sc2_protoss"]',
            last_chosen_vetoes='["Map1", "Map2"]'
        )
        
        if not success:
            print("[FAIL] Failed to create preferences")
            return False
        print("[PASS] Preferences created")
        
        # Test 2: Get preferences
        prefs = data_service.get_player_preferences(TEST_PLAYER_UID)
        if prefs:
            print(f"[PASS] Retrieved preferences: {prefs}")
        else:
            print("[FAIL] Failed to retrieve preferences")
            return False
        
        # Test 3: Get last races
        races = data_service.get_player_last_races(TEST_PLAYER_UID)
        if races:
            print(f"[PASS] Retrieved last races: {races}")
        else:
            print("[FAIL] Failed to retrieve last races")
            return False
        
        # Test 4: Update preferences
        success = await data_service.update_player_preferences(
            discord_uid=TEST_PLAYER_UID,
            last_chosen_vetoes='["Map3", "Map4", "Map5"]'
        )
        
        if success:
            prefs = data_service.get_player_preferences(TEST_PLAYER_UID)
            if '"Map3"' in prefs.get('last_chosen_vetoes', ''):
                print("[PASS] Preferences update successful")
            else:
                print(f"[FAIL] Preferences update not reflected: {prefs}")
                return False
        else:
            print("[FAIL] Preferences update failed")
            return False
        
        await asyncio.sleep(0.3)
        print("[PASS] All preferences operations successful")
        return True
        
    except Exception as e:
        print(f"[FAIL] Preferences operations failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_performance_benchmarks():
    """Test performance of in-memory operations."""
    print("\n=== TEST 5: Performance Benchmarks ===")
    
    try:
        data_service = DataAccessService()
        
        # Benchmark 1: Player info lookups
        iterations = 1000
        start_time = time.perf_counter()
        
        for _ in range(iterations):
            data_service.get_player_info(TEST_PLAYER_UID)
        
        end_time = time.perf_counter()
        avg_time_ms = ((end_time - start_time) / iterations) * 1000
        
        print(f"[PERF] Player info lookup: {avg_time_ms:.4f}ms avg ({iterations} iterations)")
        if avg_time_ms < 1.0:
            print("[PASS] Excellent performance (< 1ms)")
        elif avg_time_ms < 5.0:
            print("[PASS] Good performance (< 5ms)")
        else:
            print(f"[WARN] Slower than expected: {avg_time_ms:.4f}ms")
        
        # Benchmark 2: MMR lookups
        start_time = time.perf_counter()
        
        for _ in range(iterations):
            data_service.get_player_mmr(TEST_PLAYER_UID, "bw_terran")
        
        end_time = time.perf_counter()
        avg_time_ms = ((end_time - start_time) / iterations) * 1000
        
        print(f"[PERF] MMR lookup: {avg_time_ms:.4f}ms avg ({iterations} iterations)")
        if avg_time_ms < 1.0:
            print("[PASS] Excellent performance (< 1ms)")
        else:
            print(f"[WARN] Slower than expected: {avg_time_ms:.4f}ms")
        
        # Benchmark 3: player_exists checks
        start_time = time.perf_counter()
        
        for _ in range(iterations):
            data_service.player_exists(TEST_PLAYER_UID)
        
        end_time = time.perf_counter()
        avg_time_ms = ((end_time - start_time) / iterations) * 1000
        
        print(f"[PERF] player_exists check: {avg_time_ms:.4f}ms avg ({iterations} iterations)")
        if avg_time_ms < 1.0:
            print("[PASS] Excellent performance (< 1ms)")
        else:
            print(f"[WARN] Slower than expected: {avg_time_ms:.4f}ms")
        
        # Benchmark 4: get_all_player_mmrs
        start_time = time.perf_counter()
        
        for _ in range(iterations):
            data_service.get_all_player_mmrs(TEST_PLAYER_UID)
        
        end_time = time.perf_counter()
        avg_time_ms = ((end_time - start_time) / iterations) * 1000
        
        print(f"[PERF] get_all_player_mmrs: {avg_time_ms:.4f}ms avg ({iterations} iterations)")
        if avg_time_ms < 2.0:
            print("[PASS] Excellent performance (< 2ms)")
        else:
            print(f"[WARN] Slower than expected: {avg_time_ms:.4f}ms")
        
        print("[PASS] All performance benchmarks complete")
        return True
        
    except Exception as e:
        print(f"[FAIL] Performance benchmarks failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_write_queue():
    """Test async write queue functionality."""
    print("\n=== TEST 6: Write Queue Functionality ===")
    
    try:
        data_service = DataAccessService()
        
        writes_before = data_service._total_writes_queued
        print(f"[INFO] Writes queued before test: {writes_before}")
        
        # Queue several writes rapidly
        await data_service.log_player_action(
            TEST_PLAYER_UID,
            "TestPlayer1",
            "test_setting",
            "old_val",
            "new_val"
        )
        
        await data_service.insert_command_call(
            TEST_PLAYER_UID,
            "TestPlayer1",
            "test_command"
        )
        
        await data_service.update_remaining_aborts(TEST_PLAYER_UID, 1)
        
        writes_after = data_service._total_writes_queued
        new_writes = writes_after - writes_before
        
        if new_writes >= 3:
            print(f"[PASS] Queued {new_writes} writes successfully")
        else:
            print(f"[FAIL] Expected 3+ writes, got {new_writes}")
            return False
        
        # Give queue time to process
        print("[INFO] Waiting for write queue to process...")
        await asyncio.sleep(1.0)
        
        queue_size = data_service._write_queue.qsize()
        print(f"[INFO] Current queue size: {queue_size}")
        print(f"[INFO] Total writes completed: {data_service._total_writes_completed}")
        print(f"[INFO] Peak queue size: {data_service._write_queue_size_peak}")
        
        if queue_size < 5:
            print("[PASS] Write queue processing efficiently")
        else:
            print(f"[WARN] Queue backlog: {queue_size} pending")
        
        print("[PASS] Write queue functionality verified")
        return True
        
    except Exception as e:
        print(f"[FAIL] Write queue test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_edge_cases():
    """Test edge cases and error handling."""
    print("\n=== TEST 7: Edge Cases & Error Handling ===")
    
    try:
        data_service = DataAccessService()
        
        # Test 1: Non-existent player
        player = data_service.get_player_info(999999999)
        if player is None:
            print("[PASS] Correctly returns None for non-existent player")
        else:
            print(f"[FAIL] Should return None, got: {player}")
            return False
        
        # Test 2: Non-existent MMR
        mmr = data_service.get_player_mmr(TEST_PLAYER_UID, "invalid_race")
        if mmr is None:
            print("[PASS] Correctly returns None for non-existent MMR")
        else:
            print(f"[FAIL] Should return None, got: {mmr}")
            return False
        
        # Test 3: Duplicate player prevention
        success = await data_service.create_player(
            discord_uid=TEST_PLAYER_UID,
            discord_username="Duplicate"
        )
        
        if not success:
            print("[PASS] Correctly prevents duplicate player creation")
        else:
            print("[FAIL] Should prevent duplicate")
            return False
        
        # Test 4: Default abort count
        aborts = data_service.get_remaining_aborts(999999999)
        if aborts == 3:
            print(f"[PASS] Correctly returns default abort count: {aborts}")
        else:
            print(f"[FAIL] Wrong default abort count: {aborts}")
            return False
        
        # Test 5: Empty all_mmrs for non-existent player
        all_mmrs = data_service.get_all_player_mmrs(999999999)
        if all_mmrs == {}:
            print("[PASS] Correctly returns empty dict for non-existent player MMRs")
        else:
            print(f"[FAIL] Should return empty dict, got: {all_mmrs}")
            return False
        
        print("[PASS] All edge cases handled correctly")
        return True
        
    except Exception as e:
        print(f"[FAIL] Edge cases test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all comprehensive tests."""
    results = []
    
    # Test 1: Initialization
    results.append(("Initialization", await test_initialization()))
    
    # Test 2: Player operations
    results.append(("Player Operations", await test_player_operations()))
    
    # Test 3: MMR operations
    results.append(("MMR Operations", await test_mmr_operations()))
    
    # Test 4: Preferences operations
    results.append(("Preferences Operations", await test_preferences_operations()))
    
    # Test 5: Performance benchmarks
    results.append(("Performance Benchmarks", await test_performance_benchmarks()))
    
    # Test 6: Write queue
    results.append(("Write Queue", await test_write_queue()))
    
    # Test 7: Edge cases
    results.append(("Edge Cases", await test_edge_cases()))
    
    # Print summary
    print("\n" + "="*60)
    print("COMPREHENSIVE TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} - {test_name}")
    
    print("="*60)
    print(f"Total: {passed}/{total} tests passed")
    print("="*60)
    
    # Shutdown
    data_service = DataAccessService()
    await data_service.shutdown()
    
    return passed == total


if __name__ == "__main__":
    print("\n" + "="*60)
    print("DataAccessService Comprehensive Test Suite")
    print("="*60)
    
    # Initialize database connection pool
    try:
        initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
    except Exception as e:
        print(f"[FATAL] Failed to initialize connection pool: {e}")
        sys.exit(1)
    
    # Clean up test data from previous runs
    _cleanup_test_data()
    
    # Run tests
    try:
        success = asyncio.run(run_all_tests())
        
        # Final cleanup
        _cleanup_test_data()
        
        # Close connection pool
        close_pool()
        
        if success:
            print("\n[SUCCESS] All comprehensive tests passed!")
            sys.exit(0)
        else:
            print("\n[FAILURE] Some tests failed")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Tests cancelled by user")
        close_pool()
        sys.exit(130)
    except Exception as e:
        print(f"\n[FATAL] Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        close_pool()
        sys.exit(1)

