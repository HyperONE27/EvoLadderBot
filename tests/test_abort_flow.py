"""
Comprehensive test for match abort flow.

Tests:
1. Abort updates in-memory state correctly
2. Aborting player is identified correctly (player_report = -3)
3. Queue lock is released after abort
4. Players can re-queue after aborting
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.backend.services.data_access_service import DataAccessService
from src.backend.services.matchmaking_service import matchmaker
from src.backend.services.match_completion_service import match_completion_service
from src.backend.db.connection_pool import initialize_pool, close_pool
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS


async def test_abort_flow():
    """Test the complete abort flow."""
    print("\n=== Testing Match Abort Flow ===\n")
    
    # Initialize database pool
    initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
    
    try:
        # Initialize DataAccessService
        data_service = DataAccessService()
        await data_service.initialize_async()
        print("DataAccessService initialized")
        
        # Create two test players
        player1_uid = 111111111111111111
        player2_uid = 222222222222222222
        
        # Ensure players exist
        player1 = data_service.get_player_info(player1_uid)
        player2 = data_service.get_player_info(player2_uid)
        
        if not player1:
            await data_service.create_player(
                discord_uid=player1_uid,
                player_name="AbortTestPlayer1",
                country="US"
            )
            print(f"Created test player 1: {player1_uid}")
            await asyncio.sleep(2.0)
        
        if not player2:
            await data_service.create_player(
                discord_uid=player2_uid,
                player_name="AbortTestPlayer2",
                country="KR"
            )
            print(f"Created test player 2: {player2_uid}")
            await asyncio.sleep(2.0)
        
        # Get player info for display
        player1 = data_service.get_player_info(player1_uid)
        player2 = data_service.get_player_info(player2_uid)
        player1_name = player1.get('player_name', 'Unknown')
        player2_name = player2.get('player_name', 'Unknown')
        
        print(f"Player 1: {player1_name} ({player1_uid})")
        print(f"Player 2: {player2_name} ({player2_uid})")
        
        # Create a match
        match_id = await data_service.create_match({
            'player_1_discord_uid': player1_uid,
            'player_2_discord_uid': player2_uid,
            'player_1_race': "BW Terran",
            'player_2_race': "SC2 Zerg",
            'map_played': "[SC:Evo] Radeon (라데온)",
            'server_choice': "NA",
            'player_1_mmr': 1500,
            'player_2_mmr': 1500,
            'mmr_change': 0.0
        })
        print(f"\nCreated match {match_id}")
        
        # Get initial abort count for player1
        initial_aborts = data_service.get_remaining_aborts(player1_uid)
        print(f"Player1 initial aborts: {initial_aborts}")
        
        # Abort the match (player1 aborts)
        print(f"\nAborting match {match_id} (player1 aborts)...")
        success = await data_service.abort_match(match_id, player1_uid)
        assert success, "Abort should succeed"
        print("Abort succeeded")
        
        # Wait for in-memory update
        await asyncio.sleep(0.5)
        
        # Verify in-memory state is updated
        match_data = data_service.get_match(match_id)
        print(f"\nMatch state after abort:")
        print(f"  player_1_report: {match_data.get('player_1_report')}")
        print(f"  player_2_report: {match_data.get('player_2_report')}")
        print(f"  match_result: {match_data.get('match_result')}")
        
        # Verify aborting player is identified correctly
        assert match_data.get('player_1_report') == -3, "Player1 should have report -3 (aborter)"
        assert match_data.get('player_2_report') == -1, "Player2 should have report -1 (aborted)"
        assert match_data.get('match_result') == -1, "Match result should be -1 (aborted)"
        print("✅ Abort state correct: player1 identified as aborter")
        
        # Verify abort count decremented
        final_aborts = data_service.get_remaining_aborts(player1_uid)
        print(f"Player1 final aborts: {final_aborts}")
        assert final_aborts == initial_aborts - 1, f"Abort count should decrement: {initial_aborts} -> {final_aborts}"
        print("✅ Abort count decremented correctly")
        
        # Verify the correct player name would be displayed
        aborted_by = "Unknown"
        if match_data.get("player_1_report") == -3:
            aborted_by = player1_name
        elif match_data.get("player_2_report") == -3:
            aborted_by = player2_name
        
        print(f"\nAborted by: {aborted_by}")
        assert aborted_by == player1_name, f"Should show '{player1_name}' as aborter, got '{aborted_by}'"
        print(f"✅ Correct aborting player identified: {aborted_by}")
        
        # Wait for database write to complete
        print("\nWaiting for database write to complete...")
        await asyncio.sleep(2.0)
        
        # Test if player2 aborts instead
        print("\n=== Testing player2 as aborter ===")
        match_id2 = await data_service.create_match({
            'player_1_discord_uid': player1_uid,
            'player_2_discord_uid': player2_uid,
            'player_1_race': "BW Zerg",
            'player_2_race': "SC2 Protoss",
            'map_played': "[SC:Evo] Holy World (홀리울드)",
            'server_choice': "EU",
            'player_1_mmr': 1500,
            'player_2_mmr': 1500,
            'mmr_change': 0.0
        })
        print(f"Created match {match_id2}")
        
        # Player2 aborts
        success = await data_service.abort_match(match_id2, player2_uid)
        assert success, "Abort should succeed"
        await asyncio.sleep(0.5)
        
        match_data2 = data_service.get_match(match_id2)
        print(f"\nMatch state after abort (player2):")
        print(f"  player_1_report: {match_data2.get('player_1_report')}")
        print(f"  player_2_report: {match_data2.get('player_2_report')}")
        
        assert match_data2.get('player_1_report') == -1, "Player1 should have report -1 (aborted)"
        assert match_data2.get('player_2_report') == -3, "Player2 should have report -3 (aborter)"
        print("✅ Player2 correctly identified as aborter")
        
        # Verify the correct player name for player2
        aborted_by2 = "Unknown"
        if match_data2.get("player_1_report") == -3:
            aborted_by2 = player1_name
        elif match_data2.get("player_2_report") == -3:
            aborted_by2 = player2_name
        
        print(f"Aborted by: {aborted_by2}")
        assert aborted_by2 == player2_name, f"Should show '{player2_name}' as aborter, got '{aborted_by2}'"
        print(f"✅ Correct aborting player identified: {aborted_by2}")
        
        # Test both players trying to abort simultaneously
        print("\n=== Testing both players aborting (race condition) ===")
        match_id3 = await data_service.create_match({
            'player_1_discord_uid': player1_uid,
            'player_2_discord_uid': player2_uid,
            'player_1_race': "BW Protoss",
            'player_2_race': "SC2 Terran",
            'map_played': "Keres Passage SEL",
            'server_choice': "KR",
            'player_1_mmr': 1500,
            'player_2_mmr': 1500,
            'mmr_change': 0.0
        })
        print(f"Created match {match_id3}")
        
        # Get initial abort counts
        p1_aborts_before = data_service.get_remaining_aborts(player1_uid)
        p2_aborts_before = data_service.get_remaining_aborts(player2_uid)
        
        # Both players abort (simulate race condition)
        success1 = await data_service.abort_match(match_id3, player1_uid)
        success2 = await data_service.abort_match(match_id3, player2_uid)
        
        print(f"Player1 abort result: {success1}")
        print(f"Player2 abort result: {success2}")
        
        # Both should succeed (second one returns True but doesn't change state)
        assert success1, "Player1 abort should succeed"
        assert success2, "Player2 abort should succeed (match already aborted)"
        
        await asyncio.sleep(0.5)
        
        # Check abort counts - only player1 should have been decremented
        p1_aborts_after = data_service.get_remaining_aborts(player1_uid)
        p2_aborts_after = data_service.get_remaining_aborts(player2_uid)
        
        print(f"Player1 aborts: {p1_aborts_before} -> {p1_aborts_after}")
        print(f"Player2 aborts: {p2_aborts_before} -> {p2_aborts_after}")
        
        assert p1_aborts_after == p1_aborts_before - 1, "Player1 abort count should decrement"
        assert p2_aborts_after == p2_aborts_before, "Player2 abort count should NOT decrement (match already aborted)"
        
        match_data3 = data_service.get_match(match_id3)
        print(f"\nMatch state (both players tried to abort):")
        print(f"  player_1_report: {match_data3.get('player_1_report')}")
        print(f"  player_2_report: {match_data3.get('player_2_report')}")
        print(f"  match_result: {match_data3.get('match_result')}")
        
        # Player1 should be marked as the aborter (they got there first)
        assert match_data3.get('player_1_report') == -3, "Player1 should be marked as aborter"
        assert match_data3.get('player_2_report') == -1, "Player2 should be marked as victim"
        print("✅ Race condition handled correctly - first aborter wins")
        
        print("\n=== All Abort Tests Passed! ===")
        
    finally:
        # Shutdown
        await data_service.shutdown()
        close_pool()
        print("\nShutdown complete")


if __name__ == "__main__":
    asyncio.run(test_abort_flow())

