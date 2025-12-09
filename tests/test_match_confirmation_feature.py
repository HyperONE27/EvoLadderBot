"""
Test the match confirmation feature implementation.

This tests the new functionality where players must confirm matches
within the abort timer window, or the match will be auto-aborted
without decrementing abort counters.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.backend.services.match_completion_service import MatchCompletionService
from src.backend.services.data_access_service import DataAccessService, WriteJobType


@pytest.mark.asyncio
async def test_confirm_match_single_player():
    """Test that a single player can confirm a match."""
    service = MatchCompletionService()
    
    # Initialize confirmations for a test match
    match_id = 12345
    player1_uid = 111
    player2_uid = 222
    
    service.match_confirmations[match_id] = set()
    
    # Confirm from player 1
    result = await service.confirm_match(match_id, player1_uid)
    
    assert result is True
    assert player1_uid in service.match_confirmations[match_id]
    assert len(service.match_confirmations[match_id]) == 1


@pytest.mark.asyncio
async def test_confirm_match_both_players_cancels_timer():
    """Test that both players confirming cancels the auto-abort timer."""
    service = MatchCompletionService()
    
    match_id = 12345
    player1_uid = 111
    player2_uid = 222
    
    # Create a mock task for the monitoring
    mock_task = MagicMock()
    mock_task.cancel = MagicMock()
    
    service.match_confirmations[match_id] = set()
    service.monitoring_tasks[match_id] = mock_task
    
    # Confirm from both players
    await service.confirm_match(match_id, player1_uid)
    await service.confirm_match(match_id, player2_uid)
    
    # Task should be cancelled
    mock_task.cancel.assert_called_once()
    
    # Confirmations should be cleaned up
    assert match_id not in service.match_confirmations


@pytest.mark.asyncio
async def test_data_access_service_record_system_abort():
    """Test the new record_system_abort method in DataAccessService."""
    
    with patch('src.backend.services.data_access_service.DatabaseReader'), \
         patch('src.backend.services.data_access_service.DatabaseWriter'):
        
        service = DataAccessService()
        service._write_queue = AsyncMock()
        service._write_queue.put = AsyncMock()
        service._write_event = MagicMock()
        service._write_event.set = MagicMock()
        
        match_id = 12345
        p1_report = -4  # Player 1 didn't confirm
        p2_report = None  # Player 2 did confirm
        
        # Call the method
        await service.record_system_abort(match_id, p1_report, p2_report)
        
        # Verify a write job was queued
        service._write_queue.put.assert_called_once()
        
        # Get the job that was queued
        queued_job = service._write_queue.put.call_args[0][0]
        
        assert queued_job.job_type == WriteJobType.SYSTEM_ABORT_UNCONFIRMED
        assert queued_job.data['match_id'] == match_id
        assert queued_job.data['player_1_report'] == p1_report
        assert queued_job.data['player_2_report'] == p2_report


def test_database_writer_update_match_reports_and_result():
    """Test the new update_match_reports_and_result method in DatabaseWriter."""
    from src.backend.db.db_reader_writer import DatabaseWriter
    
    with patch('src.backend.db.db_reader_writer.get_adapter') as mock_get_adapter:
        mock_adapter_instance = MagicMock()
        mock_adapter_instance.execute_write = MagicMock(return_value=1)
        mock_get_adapter.return_value = mock_adapter_instance
        
        writer = DatabaseWriter()
        
        match_id = 12345
        p1_report = -4
        p2_report = None
        match_result = -1
        
        result = writer.update_match_reports_and_result(
            match_id, p1_report, p2_report, match_result
        )
        
        assert result is True
        mock_adapter_instance.execute_write.assert_called_once()
        
        # Verify the SQL query includes all necessary fields
        call_args = mock_adapter_instance.execute_write.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        
        assert "UPDATE matches_1v1" in query
        assert "player_1_report" in query
        assert "player_2_report" in query
        assert "match_result" in query
        assert params['match_id'] == match_id
        assert params['p1_report'] == p1_report
        assert params['p2_report'] == p2_report
        assert params['match_result'] == match_result


@pytest.mark.asyncio
async def test_unconfirmed_abort_invokes_callbacks():
    """
    Test that unconfirmed aborts properly invoke notification callbacks.
    
    This is a regression test for the bug where callbacks were not being
    invoked when matches were auto-aborted due to timeout.
    """
    service = MatchCompletionService()
    
    match_id = 99999
    player1_uid = 111
    player2_uid = 222
    
    # Setup match data with ABORTED status to test abort handling
    mock_match_data = {
        'match_id': match_id,
        'player_1_discord_uid': player1_uid,
        'player_2_discord_uid': player2_uid,
        'status': 'ABORTED',  # Set to ABORTED after record_system_abort
        'player_1_report': -4,
        'player_2_report': -4,
        'match_result': -1,
        'player_1_mmr': 1500,
        'player_2_mmr': 1500,
        'player_1_race': 'bw_terran',
        'player_2_race': 'sc2_zerg',
    }
    
    # Create a callback tracker
    callback_invoked = {'count': 0, 'status': None, 'data': None}
    
    async def test_callback(status: str, data: dict):
        """Track callback invocations."""
        callback_invoked['count'] += 1
        callback_invoked['status'] = status
        callback_invoked['data'] = data
    
    # Start monitoring with the callback
    service.start_monitoring_match(match_id, on_complete_callback=test_callback)
    
    # Verify callback was registered
    assert match_id in service.notification_callbacks
    assert len(service.notification_callbacks[match_id]) == 1
    
    # Get the real DataAccessService instance and patch its methods
    from src.backend.services.data_access_service import DataAccessService
    das_instance = DataAccessService()
    
    # Patch the methods we need to mock
    with patch.object(das_instance, 'get_match', return_value=mock_match_data), \
         patch.object(das_instance, 'record_system_abort', new_callable=AsyncMock), \
         patch.object(das_instance, 'update_match_status', return_value=None), \
         patch.object(das_instance, 'get_player_info', side_effect=lambda uid: {
             'player_name': f'Player{uid}',
             'country': 'US'
         }):
        
        # Mock matchmaker.release_queue_lock_for_players
        with patch('src.backend.services.matchmaking_service.matchmaker') as mock_matchmaker:
            mock_matchmaker.release_queue_lock_for_players = AsyncMock()
            
            # Simulate the unconfirmed abort
            await service._handle_unconfirmed_abort(match_id, mock_match_data)
            
            # Verify callback was invoked
            assert callback_invoked['count'] == 1, f"Callback should be invoked exactly once, got {callback_invoked['count']}"
            assert callback_invoked['status'] == 'abort', f"Callback should receive 'abort' status, got {callback_invoked['status']}"
            assert callback_invoked['data'] is not None, "Callback should receive data payload"
            
            # Verify data payload contains report codes
            data = callback_invoked['data']
            assert 'p1_report' in data, "Data should include p1_report"
            assert 'p2_report' in data, "Data should include p2_report"
            assert data['p1_report'] == -4, f"p1_report should be -4 for unconfirmed, got {data['p1_report']}"
            assert data['p2_report'] == -4, f"p2_report should be -4 for unconfirmed, got {data['p2_report']}"
            
            print("✅ Test passed: Unconfirmed abort properly invokes callbacks with correct data")


@pytest.mark.asyncio
async def test_partial_unconfirmed_abort_invokes_callbacks():
    """
    Test that partial unconfirmed aborts (one player confirmed) invoke callbacks correctly.
    """
    service = MatchCompletionService()
    
    match_id = 99998
    player1_uid = 111
    player2_uid = 222
    
    # Setup: Player 2 confirmed, Player 1 did not
    service.match_confirmations[match_id] = {player2_uid}
    
    # Setup match data with ABORTED status and partial reports
    mock_match_data = {
        'match_id': match_id,
        'player_1_discord_uid': player1_uid,
        'player_2_discord_uid': player2_uid,
        'status': 'ABORTED',  # Set to ABORTED after record_system_abort
        'player_1_report': -4,  # Player 1 didn't confirm
        'player_2_report': None,  # Player 2 confirmed
        'match_result': -1,
        'player_1_mmr': 1500,
        'player_2_mmr': 1500,
        'player_1_race': 'bw_terran',
        'player_2_race': 'sc2_zerg',
    }
    
    # Create a callback tracker
    callback_invoked = {'count': 0, 'data': None}
    
    async def test_callback(status: str, data: dict):
        """Track callback invocations."""
        callback_invoked['count'] += 1
        callback_invoked['data'] = data
    
    # Register callback
    service.notification_callbacks[match_id] = [test_callback]
    
    # Get the real DataAccessService instance and patch its methods
    from src.backend.services.data_access_service import DataAccessService
    das_instance = DataAccessService()
    
    # Patch the methods we need to mock
    with patch.object(das_instance, 'get_match', return_value=mock_match_data), \
         patch.object(das_instance, 'record_system_abort', new_callable=AsyncMock), \
         patch.object(das_instance, 'update_match_status', return_value=None), \
         patch.object(das_instance, 'get_player_info', side_effect=lambda uid: {
             'player_name': f'Player{uid}',
             'country': 'US'
         }):
        
        # Mock matchmaker
        with patch('src.backend.services.matchmaking_service.matchmaker') as mock_matchmaker:
            mock_matchmaker.release_queue_lock_for_players = AsyncMock()
            
            # Simulate the partial unconfirmed abort
            await service._handle_unconfirmed_abort(match_id, mock_match_data)
            
            # Verify callback was invoked
            assert callback_invoked['count'] == 1, "Callback should be invoked"
            
            # Verify data payload reflects partial confirmation
            data = callback_invoked['data']
            assert data['p1_report'] == -4, f"p1_report should be -4 (unconfirmed), got {data['p1_report']}"
            assert data['p2_report'] is None, f"p2_report should be None (confirmed), got {data['p2_report']}"
            
            print("✅ Test passed: Partial unconfirmed abort properly tracks which player failed to confirm")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

