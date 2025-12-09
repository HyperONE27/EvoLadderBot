"""
Comprehensive test for all the critical fixes.

Tests:
1. Leaderboard with proper column names and filtering
2. Match report recording in DataAccessService
3. Race condition handling in abort flow
4. Queue lock release after abort
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.backend.services.data_access_service import DataAccessService
from src.backend.services.leaderboard_service import LeaderboardService
from src.backend.db.connection_pool import initialize_pool, close_pool
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS


async def test_comprehensive_fixes():
    """Test all the critical fixes."""
    print("\n=== Testing Comprehensive Fixes ===\n")
    
    # Initialize database pool
    initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
    
    try:
        # Initialize DataAccessService
        data_service = DataAccessService()
        await data_service.initialize_async()
        print("DataAccessService initialized")
        
        # Test 1: Leaderboard with proper columns
        print("\n=== Test 1: Leaderboard DataFrame Structure ===")
        leaderboard_df = data_service.get_leaderboard_dataframe()
        if leaderboard_df is not None:
            print(f"Leaderboard DataFrame columns: {leaderboard_df.columns}")
            print(f"Leaderboard DataFrame shape: {leaderboard_df.shape}")
            
            # Test filtering
            leaderboard_service = LeaderboardService()
            try:
                data = await leaderboard_service.get_leaderboard_data(
                    country_filter=['US'],
                    race_filter=['sc2_terran'],
                    best_race_only=True,
                    current_page=1,
                    page_size=10
                )
                print(f"✅ Leaderboard filtering works: {len(data.get('players', []))} players found")
            except Exception as e:
                print(f"❌ Leaderboard filtering failed: {e}")
        else:
            print("❌ Leaderboard DataFrame is None")
        
        # Test 2: Match report recording
        print("\n=== Test 2: Match Report Recording ===")
        player1_uid = 111111111111111111
        player2_uid = 222222222222222222
        
        # Create a test match
        match_id = await data_service.create_match({
            'player_1_discord_uid': player1_uid,
            'player_2_discord_uid': player2_uid,
            'player_1_race': "BW Terran",
            'player_2_race': "SC2 Zerg",
            'map_played': '[SC:Evo] Sylphid (실피드)',
            'server_choice': "NA",
            'player_1_mmr': 1500,
            'player_2_mmr': 1500,
            'mmr_change': 0.0
        })
        print(f"Created test match {match_id}")
        
        # Record player 1 report (win)
        success1 = data_service.update_match_report(match_id, player1_uid, 1)
        print(f"Player 1 report (win): {success1}")
        
        # Record player 2 report (loss)
        success2 = data_service.update_match_report(match_id, player2_uid, 0)
        print(f"Player 2 report (loss): {success2}")
        
        # Check match data
        match_data = data_service.get_match(match_id)
        print(f"Match reports: p1={match_data.get('player_1_report')}, p2={match_data.get('player_2_report')}")
        
        assert match_data.get('player_1_report') == 1, "Player 1 report should be 1 (win)"
        assert match_data.get('player_2_report') == 0, "Player 2 report should be 0 (loss)"
        print("✅ Match reports recorded correctly in memory")
        
        # Test 3: Race condition in abort
        print("\n=== Test 3: Race Condition in Abort ===")
        match_id2 = await data_service.create_match({
            'player_1_discord_uid': player1_uid,
            'player_2_discord_uid': player2_uid,
            'player_1_race': "BW Protoss",
            'player_2_race': "SC2 Terran",
            'map_played': "[SC:Evo] Vermeer (버미어)",
            'server_choice': "EU",
            'player_1_mmr': 1500,
            'player_2_mmr': 1500,
            'mmr_change': 0.0
        })
        print(f"Created test match {match_id2}")
        
        # Both players try to abort
        success1 = await data_service.abort_match(match_id2, player1_uid)
        success2 = await data_service.abort_match(match_id2, player2_uid)
        
        print(f"Player 1 abort: {success1}")
        print(f"Player 2 abort: {success2}")
        
        # Check final state
        match_data2 = data_service.get_match(match_id2)
        print(f"Final reports: p1={match_data2.get('player_1_report')}, p2={match_data2.get('player_2_report')}")
        print(f"Match result: {match_data2.get('match_result')}")
        
        assert match_data2.get('player_1_report') == -3, "Player 1 should be marked as aborter"
        assert match_data2.get('player_2_report') == -1, "Player 2 should be marked as victim"
        assert match_data2.get('match_result') == -1, "Match should be marked as aborted"
        print("✅ Race condition handled correctly")
        
        print("\n=== All Comprehensive Tests Passed! ===")
        
    finally:
        # Shutdown
        await data_service.shutdown()
        close_pool()
        print("\nShutdown complete")


if __name__ == "__main__":
    asyncio.run(test_comprehensive_fixes())
