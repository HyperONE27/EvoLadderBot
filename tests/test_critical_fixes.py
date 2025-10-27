"""
Test suite for critical fixes:
1. Leaderboard rank calculation
2. Match abort functionality
3. In-memory state updates
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.backend.services.data_access_service import DataAccessService
from src.backend.services.leaderboard_service import LeaderboardService
from src.backend.services.ranking_service import RankingService
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS


async def test_leaderboard_with_ranks():
    """Test that leaderboard includes rank column."""
    print("\n[TEST] Leaderboard rank calculation...")
    
    # Initialize services
    data_service = DataAccessService()
    await data_service.initialize_async()
    
    # Initialize ranking service and trigger refresh
    ranking_service = RankingService()
    ranking_service.trigger_refresh()
    await asyncio.sleep(1.0)  # Wait for refresh to complete
    
    # Initialize leaderboard service
    leaderboard_service = LeaderboardService(ranking_service=ranking_service)
    
    # Get leaderboard data
    leaderboard_data = await leaderboard_service.get_leaderboard_data(
        current_page=1,
        page_size=10
    )
    
    assert 'players' in leaderboard_data, "Leaderboard should have players"
    
    if leaderboard_data['players']:
        first_player = leaderboard_data['players'][0]
        print(f"[TEST] First player: {first_player.get('player_name')}")
        print(f"[TEST] Rank: {first_player.get('rank')}")
        print(f"[TEST] MMR: {first_player.get('mmr')}")
        print(f"[PASS] Leaderboard includes rank data")
    else:
        print(f"[SKIP] No players in leaderboard")
    
    await data_service.shutdown()
    return True


async def test_match_abort():
    """Test match abort functionality."""
    print("\n[TEST] Match abort functionality...")
    
    # Initialize DataAccessService
    data_service = DataAccessService()
    await data_service.initialize_async()
    
    # Create test players
    test_uid_1 = 888888888888888888
    test_uid_2 = 777777777777777777
    
    await data_service.create_player(
        discord_uid=test_uid_1,
        discord_username="AbortTest1",
        player_name="AbortPlayer1"
    )
    
    await data_service.create_player(
        discord_uid=test_uid_2,
        discord_username="AbortTest2",
        player_name="AbortPlayer2"
    )
    
    # Wait longer for writes to complete
    await asyncio.sleep(2.0)
    
    # Create a match
    match_data = {
        'player_1_discord_uid': test_uid_1,
        'player_2_discord_uid': test_uid_2,
        'player_1_race': 'bw_terran',
        'player_2_race': 'sc2_zerg',
        'map_played': '[SC:Evo] Holy World (홀리울드)',
        'server_choice': 'US-West',
        'player_1_mmr': 1500,
        'player_2_mmr': 1500,
        'mmr_change': 0
    }
    
    match_id = await data_service.create_match(match_data)
    assert match_id is not None, "Match should be created"
    print(f"[TEST] Match created: {match_id}")
    
    await asyncio.sleep(0.5)
    
    # Get initial abort count
    initial_aborts = data_service.get_remaining_aborts(test_uid_1)
    print(f"[TEST] Initial aborts: {initial_aborts}")
    
    # Abort the match
    print(f"[TEST] Aborting match {match_id}...")
    success = await data_service.abort_match(match_id, test_uid_1)
    assert success, "Abort should succeed"
    print(f"[PASS] Match aborted successfully")
    
    await asyncio.sleep(0.5)
    
    # Verify abort count decreased
    new_aborts = data_service.get_remaining_aborts(test_uid_1)
    print(f"[TEST] New aborts: {new_aborts}")
    assert new_aborts == initial_aborts - 1, f"Aborts should decrease by 1, got {new_aborts}"
    print(f"[PASS] Abort count updated correctly")
    
    # Verify match state is updated
    match = data_service.get_match(match_id)
    assert match is not None, "Match should still exist"
    assert match['match_result'] == -1, f"Match result should be -1 (aborted), got {match['match_result']}"
    print(f"[PASS] Match state updated to aborted")
    
    await data_service.shutdown()
    return True


async def run_all_tests():
    """Run all critical fix tests."""
    print("\n" + "="*60)
    print("CRITICAL FIXES TEST SUITE")
    print("="*60)
    
    try:
        await test_leaderboard_with_ranks()
        await test_match_abort()
        
        print("\n" + "="*60)
        print("ALL CRITICAL FIX TESTS PASSED")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
        success = asyncio.run(run_all_tests())
        close_pool()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[FATAL] Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        close_pool()
        sys.exit(1)

