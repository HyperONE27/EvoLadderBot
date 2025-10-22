"""
Test suite for DataAccessService.

This validates the core functionality of the in-memory data access layer.
"""

import asyncio
import sys
import os
from pathlib import Path

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    os.system("chcp 65001 > nul")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backend.services.data_access_service import data_access_service
from src.backend.db.connection_pool import initialize_pool, close_pool
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS


async def test_initialization():
    """Test that the service initializes correctly."""
    print("\n=== TEST: Initialization ===")
    
    try:
        await data_access_service.initialize_async()
        print("[PASS] Service initialized successfully")
        return True
    except Exception as e:
        print(f"[FAIL] Initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_player_reads():
    """Test reading player data from in-memory DataFrame."""
    print("\n=== TEST: Player Reads ===")
    
    try:
        # Test get_player_info (should return None for non-existent player)
        player = data_access_service.get_player_info(999999999)
        if player is None:
            print("[PASS] get_player_info correctly returns None for non-existent player")
        else:
            print(f"[FAIL] Expected None, got: {player}")
            return False
        
        # Test get_remaining_aborts (should return default 3 for non-existent player)
        aborts = data_access_service.get_remaining_aborts(999999999)
        if aborts == 3:
            print(f"[PASS] get_remaining_aborts correctly returns default value: {aborts}")
        else:
            print(f"[FAIL] Expected 3, got: {aborts}")
            return False
        
        # If there are actual players in the database, test with a real one
        if data_access_service._players_df is not None and len(data_access_service._players_df) > 0:
            # Get first player's discord_uid
            first_player_uid = data_access_service._players_df[0, "discord_uid"]
            player = data_access_service.get_player_info(first_player_uid)
            if player is not None:
                print(f"[PASS] Successfully retrieved real player: {player.get('player_name', 'N/A')}")
                
                aborts = data_access_service.get_remaining_aborts(first_player_uid)
                print(f"[INFO] Player has {aborts} remaining aborts")
            else:
                print("[FAIL] Failed to retrieve real player")
                return False
        else:
            print("[INFO] No players in database to test with")
        
        return True
    except Exception as e:
        print(f"[FAIL] Player read test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_write_queue():
    """Test the async write queue."""
    print("\n=== TEST: Write Queue ===")
    
    try:
        # Queue a player action log
        await data_access_service.log_player_action(
            discord_uid=123456,
            player_name="TestPlayer",
            setting_name="test_setting",
            old_value="old",
            new_value="new"
        )
        print("[PASS] Successfully queued player action log")
        
        # Queue a command call
        await data_access_service.insert_command_call(
            discord_uid=123456,
            player_name="TestPlayer",
            command="/test"
        )
        print("[PASS] Successfully queued command call")
        
        # Give the worker a moment to process
        await asyncio.sleep(0.5)
        
        # Check queue stats
        queued = data_access_service._total_writes_queued
        completed = data_access_service._total_writes_completed
        print(f"[INFO] Writes queued: {queued}, completed: {completed}")
        
        if queued >= 2:
            print("[PASS] Write queue is working")
            return True
        else:
            print(f"[FAIL] Expected at least 2 queued writes, got {queued}")
            return False
    except Exception as e:
        print(f"[FAIL] Write queue test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_player_writes():
    """Test write operations for players table."""
    print("\n=== TEST: Player Writes ===")
    
    try:
        # Test 1: Create a new player
        test_uid = 999888777
        success = await data_access_service.create_player(
            discord_uid=test_uid,
            discord_username="TestUser123",
            player_name="TestPlayer",
            country="US"
        )
        
        if success:
            print("[PASS] Successfully created new player")
        else:
            print("[FAIL] Failed to create player")
            return False
        
        # Verify player was added to in-memory DataFrame
        player = data_access_service.get_player_info(test_uid)
        if player is not None and player.get('player_name') == 'TestPlayer':
            print(f"[PASS] Player immediately available in memory: {player.get('player_name')}")
        else:
            print("[FAIL] Player not found in memory after creation")
            return False
        
        # Test 2: Update player info
        success = await data_access_service.update_player_info(
            discord_uid=test_uid,
            player_name="UpdatedPlayer",
            country="CA"
        )
        
        if success:
            print("[PASS] Successfully updated player info")
        else:
            print("[FAIL] Failed to update player info")
            return False
        
        # Verify update in memory
        player = data_access_service.get_player_info(test_uid)
        if player.get('player_name') == 'UpdatedPlayer' and player.get('country') == 'CA':
            print("[PASS] Player updates immediately visible in memory")
        else:
            print(f"[FAIL] Updates not reflected in memory: {player}")
            return False
        
        # Test 3: Update remaining aborts
        success = await data_access_service.update_remaining_aborts(test_uid, 2)
        
        if success:
            print("[PASS] Successfully updated remaining aborts")
        else:
            print("[FAIL] Failed to update aborts")
            return False
        
        # Verify abort update in memory
        aborts = data_access_service.get_remaining_aborts(test_uid)
        if aborts == 2:
            print(f"[PASS] Abort count immediately updated in memory: {aborts}")
        else:
            print(f"[FAIL] Abort count not updated correctly: {aborts}")
            return False
        
        # Test 4: Try to create duplicate player (should fail)
        success = await data_access_service.create_player(
            discord_uid=test_uid,
            discord_username="Duplicate"
        )
        
        if not success:
            print("[PASS] Correctly prevented duplicate player creation")
        else:
            print("[FAIL] Should have prevented duplicate player creation")
            return False
        
        # Give the write queue time to process
        await asyncio.sleep(0.5)
        
        # Check that writes were queued
        queued = data_access_service._total_writes_queued
        if queued >= 3:  # create + 2 updates
            print(f"[INFO] {queued} writes queued successfully")
        
        return True
    except Exception as e:
        print(f"[FAIL] Player write test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_mmr_operations():
    """Test MMR read and write operations."""
    print("\n=== TEST: MMR Operations ===")
    
    try:
        test_uid = 999888777
        test_race = "bw_terran"
        
        # Test 1: Create new MMR record
        success = await data_access_service.create_or_update_mmr(
            discord_uid=test_uid,
            player_name="TestPlayer",
            race=test_race,
            mmr=1500,
            games_played=10,
            games_won=6,
            games_lost=4
        )
        
        if success:
            print("[PASS] Successfully created MMR record")
        else:
            print("[FAIL] Failed to create MMR record")
            return False
        
        # Verify MMR was added to in-memory DataFrame
        mmr = data_access_service.get_player_mmr(test_uid, test_race)
        if mmr == 1500:
            print(f"[PASS] MMR immediately available in memory: {mmr}")
        else:
            print(f"[FAIL] MMR not found or incorrect: {mmr}")
            return False
        
        # Test 2: Get all MMRs for player
        all_mmrs = data_access_service.get_all_player_mmrs(test_uid)
        if test_race in all_mmrs and all_mmrs[test_race] == 1500:
            print(f"[PASS] get_all_player_mmrs returned correct data: {all_mmrs}")
        else:
            print(f"[FAIL] get_all_player_mmrs incorrect: {all_mmrs}")
            return False
        
        # Test 3: Update existing MMR
        success = await data_access_service.update_player_mmr(
            discord_uid=test_uid,
            race=test_race,
            new_mmr=1550,
            games_played=11,
            games_won=7,
            games_lost=4
        )
        
        if success:
            print("[PASS] Successfully updated MMR")
        else:
            print("[FAIL] Failed to update MMR")
            return False
        
        # Verify update in memory
        mmr = data_access_service.get_player_mmr(test_uid, test_race)
        if mmr == 1550:
            print(f"[PASS] MMR update immediately visible in memory: {mmr}")
        else:
            print(f"[FAIL] MMR update not reflected: {mmr}")
            return False
        
        # Test 4: Upsert (update) existing record
        success = await data_access_service.create_or_update_mmr(
            discord_uid=test_uid,
            player_name="TestPlayer",
            race=test_race,
            mmr=1600
        )
        
        if success:
            print("[PASS] Successfully upserted (updated) MMR record")
        else:
            print("[FAIL] Failed to upsert MMR")
            return False
        
        # Verify upsert
        mmr = data_access_service.get_player_mmr(test_uid, test_race)
        if mmr == 1600:
            print(f"[PASS] Upsert successful: {mmr}")
        else:
            print(f"[FAIL] Upsert not reflected: {mmr}")
            return False
        
        # Test 5: Create MMR for different race
        success = await data_access_service.create_or_update_mmr(
            discord_uid=test_uid,
            player_name="TestPlayer",
            race="sc2_zerg",
            mmr=1400
        )
        
        if success:
            print("[PASS] Successfully created second race MMR")
        else:
            print("[FAIL] Failed to create second race MMR")
            return False
        
        # Verify multiple races
        all_mmrs = data_access_service.get_all_player_mmrs(test_uid)
        if len(all_mmrs) == 2 and "sc2_zerg" in all_mmrs:
            print(f"[PASS] Player now has multiple race MMRs: {all_mmrs}")
        else:
            print(f"[FAIL] Multiple races not working: {all_mmrs}")
            return False
        
        # Give the write queue time to process
        await asyncio.sleep(0.5)
        
        # Check that writes were queued
        queued = data_access_service._total_writes_queued
        print(f"[INFO] {queued} total writes queued")
        
        return True
    except Exception as e:
        print(f"[FAIL] MMR operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_performance():
    """Test read performance from in-memory DataFrames."""
    print("\n=== TEST: Performance ===")
    
    try:
        import time
        
        # If we have players, test performance
        if data_access_service._players_df is not None and len(data_access_service._players_df) > 0:
            first_player_uid = data_access_service._players_df[0, "discord_uid"]
            
            # Warm-up
            data_access_service.get_player_info(first_player_uid)
            
            # Time 100 reads
            iterations = 100
            start = time.perf_counter()
            for _ in range(iterations):
                data_access_service.get_player_info(first_player_uid)
            elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
            
            avg_time = elapsed / iterations
            print(f"[PASS] Average read time: {avg_time:.4f}ms per read ({iterations} iterations)")
            
            if avg_time < 5:  # Should be sub-5ms
                print(f"[PASS] Performance excellent (< 5ms)")
                return True
            elif avg_time < 10:
                print(f"[WARN] Performance acceptable but could be better (< 10ms)")
                return True
            else:
                print(f"[FAIL] Performance poor (>= 10ms)")
                return False
        else:
            print("[INFO] No players in database to test performance with")
            return True
    except Exception as e:
        print(f"[FAIL] Performance test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all tests in sequence."""
    print("=" * 60)
    print("DataAccessService Test Suite")
    print("=" * 60)
    
    # Initialize database connection pool
    print("\nInitializing database connection pool...")
    try:
        initialize_pool(
            dsn=DATABASE_URL,
            min_conn=DB_POOL_MIN_CONNECTIONS,
            max_conn=DB_POOL_MAX_CONNECTIONS
        )
        print("Database pool initialized\n")
    except Exception as e:
        print(f"Failed to initialize database pool: {e}")
        return False
    
    results = []
    
    # Test 1: Initialization
    results.append(("Initialization", await test_initialization()))
    
    # Test 2: Player reads
    results.append(("Player Reads", await test_player_reads()))
    
    # Test 3: Write queue
    results.append(("Write Queue", await test_write_queue()))
    
    # Test 4: Player writes
    results.append(("Player Writes", await test_player_writes()))
    
    # Test 5: MMR operations
    results.append(("MMR Operations", await test_mmr_operations()))
    
    # Test 6: Performance
    results.append(("Performance", await test_performance()))
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} - {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    # Shutdown
    await data_access_service.shutdown()
    
    # Close database pool
    close_pool()
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)

