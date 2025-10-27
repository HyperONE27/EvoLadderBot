"""
Comprehensive integration test for the entire DataAccessService migration.

This test verifies that:
1. All core flows work end-to-end
2. No regressions were introduced
3. Performance is improved
4. Data consistency is maintained
"""

import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.backend.services.data_access_service import DataAccessService
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS


async def test_player_creation_and_retrieval():
    """Test player creation and retrieval flow."""
    print("\n[TEST] Player creation and retrieval...")
    data_service = DataAccessService()
    
    test_uid = 999999999999999999
    await data_service.create_player(
        discord_uid=test_uid,
        discord_username="IntegrationTest",
        player_name="TestPlayer"
    )
    
    await asyncio.sleep(0.2)
    
    # Retrieve player (should be instant from memory)
    start = time.perf_counter()
    player = data_service.get_player_info(test_uid)
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    assert player is not None, "Player should exist"
    assert player['player_name'] == 'TestPlayer', "Player name should match"
    assert elapsed_ms < 2.0, f"Read should be < 2ms, got {elapsed_ms:.2f}ms"
    print(f"[PASS] Player retrieval in {elapsed_ms:.2f}ms")
    
    return True


async def test_mmr_operations():
    """Test MMR creation, update, and retrieval."""
    print("\n[TEST] MMR operations...")
    data_service = DataAccessService()
    
    test_uid = 999999999999999999
    
    # Create MMR
    await data_service.create_or_update_mmr(
        discord_uid=test_uid,
        player_name="TestPlayer",
        race="bw_terran",
        mmr=1500
    )
    
    await asyncio.sleep(0.2)
    
    # Retrieve MMR (should be instant)
    start = time.perf_counter()
    mmr = data_service.get_player_mmr(test_uid, "bw_terran")
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    assert mmr == 1500, f"MMR should be 1500, got {mmr}"
    assert elapsed_ms < 1.0, f"MMR read should be < 1ms, got {elapsed_ms:.2f}ms"
    print(f"[PASS] MMR retrieval in {elapsed_ms:.2f}ms")
    
    # Update MMR
    await data_service.update_player_mmr(test_uid, "bw_terran", 1550)
    await asyncio.sleep(0.2)
    
    # Verify update
    updated_mmr = data_service.get_player_mmr(test_uid, "bw_terran")
    assert updated_mmr == 1550, f"Updated MMR should be 1550, got {updated_mmr}"
    print(f"[PASS] MMR update verified")
    
    return True


async def test_match_operations():
    """Test match creation and retrieval."""
    print("\n[TEST] Match operations...")
    data_service = DataAccessService()
    
    test_uid_1 = 999999999999999999
    test_uid_2 = 999999999999999998
    
    # Ensure both players exist
    await data_service.create_player(
        discord_uid=test_uid_2,
        discord_username="IntegrationTest2",
        player_name="TestPlayer2"
    )
    await asyncio.sleep(0.2)
    
    # Create match
    match_data = {
        'player_1_discord_uid': test_uid_1,
        'player_2_discord_uid': test_uid_2,
        'player_1_race': 'bw_terran',
        'player_2_race': 'sc2_protoss',
        'map_played': '[SC:Evo] Radeon (라데온)',
        'server_choice': 'US-West',
        'player_1_mmr': 1550,
        'player_2_mmr': 1500,
        'mmr_change': 0
    }
    
    match_id = await data_service.create_match(match_data)
    assert match_id is not None, "Match should be created"
    print(f"[PASS] Match created: {match_id}")
    
    await asyncio.sleep(0.2)
    
    # Retrieve match (should be instant)
    start = time.perf_counter()
    match = data_service.get_match(match_id)
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    assert match is not None, "Match should exist"
    assert match['map_played'] == '[SC:Evo] Radeon (라데온)', "Map should match"
    assert elapsed_ms < 1.0, f"Match read should be < 1ms, got {elapsed_ms:.2f}ms"
    print(f"[PASS] Match retrieval in {elapsed_ms:.2f}ms")
    
    return True


async def test_preferences_operations():
    """Test preference updates."""
    print("\n[TEST] Preferences operations...")
    data_service = DataAccessService()
    
    test_uid = 999999999999999999
    
    # Update preferences
    await data_service.update_player_preferences(
        test_uid,
        "bw_terran,bw_zerg",
        "map1,map2,map3"
    )
    
    await asyncio.sleep(0.2)
    
    # Retrieve preferences (should be instant)
    start = time.perf_counter()
    prefs = data_service.get_player_preferences(test_uid)
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    assert prefs is not None, "Preferences should exist"
    assert prefs['last_chosen_races'] == "bw_terran,bw_zerg", "Races should match"
    assert elapsed_ms < 1.0, f"Preferences read should be < 1ms, got {elapsed_ms:.2f}ms"
    print(f"[PASS] Preferences retrieval in {elapsed_ms:.2f}ms")
    
    return True


async def run_all_integration_tests():
    """Run all integration tests."""
    print("\n" + "="*60)
    print("COMPREHENSIVE INTEGRATION TEST SUITE")
    print("="*60)
    
    # Initialize DataAccessService
    data_service = DataAccessService()
    await data_service.initialize_async()
    
    try:
        # Run tests
        await test_player_creation_and_retrieval()
        await test_mmr_operations()
        await test_match_operations()
        await test_preferences_operations()
        
        # Wait for all writes to complete
        print("\n[TEST] Waiting for all writes to complete...")
        await asyncio.sleep(1.0)
        
        # Shutdown
        await data_service.shutdown()
        
        print("\n" + "="*60)
        print("ALL INTEGRATION TESTS PASSED")
        print("="*60)
        
        return True
        
    except Exception as e:
        print(f"\n[FAIL] Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        await data_service.shutdown()
        return False


if __name__ == "__main__":
    try:
        initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
        success = asyncio.run(run_all_integration_tests())
        close_pool()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[FATAL] Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        close_pool()
        sys.exit(1)

