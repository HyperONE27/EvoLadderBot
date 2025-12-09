"""
Test to verify that MMR changes are correctly displayed in match completion notifications.

This is a regression test for the bug where the match result finalized embed
was displaying "+0" instead of the actual MMR changes.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.backend.services.match_completion_service import MatchCompletionService


@pytest.mark.asyncio
async def test_mmr_change_properly_passed_to_notification():
    """
    Test that MMR changes calculated by matchmaker are properly passed
    to the notification embed, eliminating the race condition where
    _get_match_final_results reads stale data.
    """
    service = MatchCompletionService()
    
    match_id = 88888
    player1_uid = 111
    player2_uid = 222
    
    # The calculated MMR change from matchmaker
    calculated_mmr_change = 20.0
    
    # Match data BEFORE MMR calculation (as it exists in DAS during the call)
    match_data_before = {
        'match_id': match_id,
        'player_1_discord_uid': player1_uid,
        'player_2_discord_uid': player2_uid,
        'status': 'PENDING',
        'player_1_report': 1,
        'player_2_report': 1,
        'match_result': 1,
        'player_1_mmr': 1498,
        'player_2_mmr': 1502,
        'player_1_race': 'bw_terran',
        'player_2_race': 'sc2_zerg',
        'mmr_change': 0,  # Not yet updated
    }
    
    # Match data AFTER MMR calculation (as it would be after async update)
    match_data_after = {
        **match_data_before,
        'mmr_change': calculated_mmr_change,  # Now updated
    }
    
    # Track the final data passed to notifications
    notification_data = {'data': None}
    
    async def test_callback(status: str, data: dict):
        """Capture notification data."""
        if status == "complete":
            notification_data['data'] = data
    
    # Register callback
    service.notification_callbacks[match_id] = [test_callback]
    
    # Get the real DataAccessService instance
    from src.backend.services.data_access_service import DataAccessService
    das_instance = DataAccessService()
    
    # Mock matchmaker to return our calculated MMR change
    from src.backend.services.matchmaking_service import matchmaker
    
    with patch.object(das_instance, 'get_match', return_value=match_data_before), \
         patch.object(das_instance, 'get_player_info', side_effect=lambda uid: {
             'player_name': f'Player{uid}',
             'country': 'US'
         }), \
         patch.object(matchmaker, '_calculate_and_write_mmr', new_callable=AsyncMock) as mock_calc_mmr, \
         patch.object(matchmaker, 'release_queue_lock_for_players', new_callable=AsyncMock):
        
        # Setup matchmaker to return the calculated MMR change
        mock_calc_mmr.return_value = calculated_mmr_change
        
        # Call _handle_match_completion
        await service._handle_match_completion(match_id, match_data_before)
        
        # Verify notification callback was invoked
        assert notification_data['data'] is not None, "Notification callback should be invoked"
        
        # Verify the MMR change in the notification data matches what matchmaker calculated
        assert notification_data['data']['p1_mmr_change'] == calculated_mmr_change, \
            f"Player 1 MMR change should be {calculated_mmr_change}, got {notification_data['data']['p1_mmr_change']}"
        
        assert notification_data['data']['p2_mmr_change'] == -calculated_mmr_change, \
            f"Player 2 MMR change should be {-calculated_mmr_change}, got {notification_data['data']['p2_mmr_change']}"
        
        print(f"✅ MMR changes correctly passed: P1={notification_data['data']['p1_mmr_change']:+}, P2={notification_data['data']['p2_mmr_change']:+}")


@pytest.mark.asyncio
async def test_mmr_change_zero_for_aborts():
    """
    Test that aborted matches have MMR change of 0.
    """
    service = MatchCompletionService()
    
    match_id = 77777
    player1_uid = 111
    player2_uid = 222
    
    match_data = {
        'match_id': match_id,
        'player_1_discord_uid': player1_uid,
        'player_2_discord_uid': player2_uid,
        'status': 'ABORTED',
        'player_1_report': -4,
        'player_2_report': -4,
        'match_result': -1,
        'player_1_mmr': 1500,
        'player_2_mmr': 1500,
        'player_1_race': 'bw_terran',
        'player_2_race': 'sc2_zerg',
        'mmr_change': 0,
    }
    
    # Track notification data
    notification_data = {'data': None}
    
    async def test_callback(status: str, data: dict):
        """Capture notification data."""
        if status == "abort":
            notification_data['data'] = data
    
    # Register callback
    service.notification_callbacks[match_id] = [test_callback]
    
    # Get the real DataAccessService instance
    from src.backend.services.data_access_service import DataAccessService
    das_instance = DataAccessService()
    
    from src.backend.services.matchmaking_service import matchmaker
    
    with patch.object(das_instance, 'get_match', return_value=match_data), \
         patch.object(das_instance, 'get_player_info', side_effect=lambda uid: {
             'player_name': f'Player{uid}',
             'country': 'US'
         }), \
         patch.object(matchmaker, 'release_queue_lock_for_players', new_callable=AsyncMock):
        
        # Call _handle_match_abort
        await service._handle_match_abort(match_id, match_data)
        
        # Verify notification callback was invoked
        assert notification_data['data'] is not None, "Notification callback should be invoked"
        
        # For aborts, MMR changes are in the nested match_data structure
        match_data_from_notification = notification_data['data']['match_data']
        
        # Verify MMR changes are 0 for aborted matches
        assert match_data_from_notification['p1_mmr_change'] == 0.0, \
            f"Aborted match should have 0 MMR change for P1, got {match_data_from_notification['p1_mmr_change']}"
        
        assert match_data_from_notification['p2_mmr_change'] == 0.0, \
            f"Aborted match should have 0 MMR change for P2, got {match_data_from_notification['p2_mmr_change']}"
        
        print(f"✅ Aborted match correctly has 0 MMR change")


if __name__ == "__main__":
    import asyncio
    
    async def main():
        print("Running MMR display fix tests...")
        await test_mmr_change_properly_passed_to_notification()
        await test_mmr_change_zero_for_aborts()
        print("\n✅ All tests passed!")
    
    asyncio.run(main())

