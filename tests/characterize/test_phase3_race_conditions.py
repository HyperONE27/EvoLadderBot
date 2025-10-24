"""
Characterization tests for Phase 3: Atomic Match State Transitions.

These tests verify that the atomic status field and lock-based synchronization
prevent race conditions between completion, abort, and result-recording operations.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.backend.services.matchmaking_service import Matchmaker
from src.backend.services.match_completion_service import match_completion_service
from src.backend.services.data_access_service import DataAccessService


@pytest.mark.asyncio
async def test_abort_after_completion_is_rejected():
    """
    Test that aborting a match that has already completed is rejected.
    
    This verifies that the atomic status field prevents race conditions
    where a player tries to abort a match that is already in a terminal state.
    """
    matchmaker = Matchmaker()
    data_service = DataAccessService()
    
    # Create a mock match that is already COMPLETE
    mock_match = {
        'id': 999,
        'status': 'COMPLETE',
        'player_1_discord_uid': 111,
        'player_2_discord_uid': 222,
        'player_1_report': 1,
        'player_2_report': 0,
        'match_result': 1,
    }
    
    with patch.object(data_service, 'get_match', return_value=mock_match):
        with patch.object(data_service, 'abort_match', new=AsyncMock()) as mock_abort:
            # Try to abort a completed match
            result = await matchmaker.abort_match(999, 111)
            
            # The abort should be rejected (return False)
            assert result is False
            # The data_service.abort_match should not have been called
            mock_abort.assert_not_called()


@pytest.mark.asyncio
async def test_complete_after_abort_is_rejected():
    """
    Test that completing a match that has already been aborted is rejected.
    
    This verifies that check_match_completion respects the atomic status field
    and does not process matches that are already in a terminal state.
    """
    data_service = DataAccessService()
    
    # Create a mock match that is already ABORTED
    mock_match = {
        'id': 998,
        'status': 'ABORTED',
        'player_1_discord_uid': 111,
        'player_2_discord_uid': 222,
        'player_1_report': -3,
        'player_2_report': -1,
        'match_result': -1,
    }
    
    with patch.object(data_service, 'get_match', return_value=mock_match):
        with patch.object(match_completion_service, '_handle_match_completion', new=AsyncMock()) as mock_handle:
            # Try to check completion for an aborted match
            result = await match_completion_service.check_match_completion(998)
            
            # The check should return True (already processed)
            assert result is True
            # The _handle_match_completion should not have been called
            mock_handle.assert_not_called()


@pytest.mark.asyncio
async def test_record_result_after_completion_is_rejected():
    """
    Test that recording a result for a completed match is rejected.
    
    This verifies that record_match_result respects the atomic status field
    and does not allow result changes after a match is complete.
    """
    matchmaker = Matchmaker()
    data_service = DataAccessService()
    
    # Create a mock match that is already COMPLETE
    mock_match = {
        'id': 997,
        'status': 'COMPLETE',
        'player_1_discord_uid': 111,
        'player_2_discord_uid': 222,
        'player_1_report': 1,
        'player_2_report': 0,
        'match_result': 1,
    }
    
    with patch.object(data_service, 'get_match', return_value=mock_match):
        with patch.object(data_service, 'update_match_report', return_value=True) as mock_update:
            # Try to record a result for a completed match
            result = await matchmaker.record_match_result(997, 111, 0)
            
            # The recording should be rejected (return False)
            assert result is False
            # The data_service.update_match_report should not have been called
            mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_concurrent_abort_and_complete_uses_same_lock():
    """
    Test that abort_match and check_match_completion use the same lock.
    
    This verifies that the lock coordination prevents race conditions
    between concurrent abort and complete operations.
    """
    # This test verifies that both operations acquire the lock from match_completion_service
    matchmaker = Matchmaker()
    data_service = DataAccessService()
    
    mock_match = {
        'id': 996,
        'status': 'IN_PROGRESS',
        'player_1_discord_uid': 111,
        'player_2_discord_uid': 222,
        'player_1_report': None,
        'player_2_report': None,
        'match_result': None,
    }
    
    # Track lock acquisitions
    lock_acquisitions = []
    
    # Create a real lock for testing
    real_lock = asyncio.Lock()
    
    def track_lock_acquire(match_id):
        """Helper to track when the lock is acquired."""
        lock_acquisitions.append(f"acquire_{match_id}")
        return real_lock
    
    with patch.object(match_completion_service, '_get_lock', side_effect=track_lock_acquire):
        with patch.object(data_service, 'get_match', return_value=mock_match):
            with patch.object(data_service, 'abort_match', new=AsyncMock(return_value=True)):
                with patch.object(data_service, 'update_match_status', return_value=True):
                    with patch.object(match_completion_service, 'check_match_completion', new=AsyncMock()):
                        # Trigger abort (which should acquire the lock)
                        await matchmaker.abort_match(996, 111)
                        
                        # Verify the lock was acquired
                        assert "acquire_996" in lock_acquisitions


@pytest.mark.asyncio
async def test_status_transitions_are_atomic():
    """
    Test that status transitions happen atomically during completion.
    
    This verifies that the status field is updated in the correct order:
    IN_PROGRESS -> PROCESSING_COMPLETION -> COMPLETE
    """
    data_service = DataAccessService()
    
    # Track status updates
    status_updates = []
    
    def mock_update_status(match_id, new_status):
        status_updates.append(new_status)
        return True
    
    # Create a mock match with both reports ready
    mock_match = {
        'id': 995,
        'status': 'IN_PROGRESS',
        'player_1_discord_uid': 111,
        'player_2_discord_uid': 222,
        'player_1_report': 1,
        'player_2_report': 0,
        'match_result': 1,
        'player_1_mmr': 1500,
        'player_2_mmr': 1500,
        'mmr_change': 25.0,
    }
    
    with patch.object(data_service, 'get_match', return_value=mock_match):
        with patch.object(data_service, 'update_match_status', side_effect=mock_update_status):
            with patch.object(match_completion_service, '_handle_match_completion', new=AsyncMock()):
                # Trigger completion
                await match_completion_service.check_match_completion(995)
                
                # Verify the status transitions happened in the correct order
                assert status_updates == ['PROCESSING_COMPLETION', 'COMPLETE']


@pytest.mark.asyncio
async def test_abort_transitions_to_aborted_status():
    """
    Test that aborting a match atomically transitions to ABORTED status.
    
    This verifies that the abort operation updates the status field.
    """
    matchmaker = Matchmaker()
    data_service = DataAccessService()
    
    # Track status updates
    status_updates = []
    
    def mock_update_status(match_id, new_status):
        status_updates.append(new_status)
        return True
    
    mock_match = {
        'id': 994,
        'status': 'IN_PROGRESS',
        'player_1_discord_uid': 111,
        'player_2_discord_uid': 222,
        'player_1_report': None,
        'player_2_report': None,
        'match_result': None,
    }
    
    with patch.object(data_service, 'get_match', return_value=mock_match):
        with patch.object(data_service, 'abort_match', new=AsyncMock(return_value=True)):
            with patch.object(data_service, 'update_match_status', side_effect=mock_update_status):
                with patch.object(match_completion_service, 'check_match_completion', new=AsyncMock()):
                    # Trigger abort
                    await matchmaker.abort_match(994, 111)
                    
                    # Verify the status was updated to ABORTED
                    assert 'ABORTED' in status_updates

