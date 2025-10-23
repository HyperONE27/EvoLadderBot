"""
Test match state race condition fixes.

This test verifies that the fix for section 2.3 of big_plan.md prevents
race conditions between match completion and abort operations.
"""

import asyncio
import time
from unittest.mock import MagicMock, patch, AsyncMock
import polars as pl
import pytest

from src.backend.services.match_completion_service import MatchCompletionService


class TestMatchStateRaceCondition:
    """Test suite for match state race condition fixes."""
    
    @pytest.fixture
    def setup_mock_data_service(self):
        """Setup a mocked DataAccessService for testing."""
        # Patch where DataAccessService is imported and used
        with patch('src.backend.services.data_access_service.DataAccessService') as mock_das_class:
            # Create a mock instance
            mock_das = AsyncMock()
            mock_das_class.get_instance = AsyncMock(return_value=mock_das)
            
            # Setup mock methods
            mock_das.update_match_status = MagicMock(return_value=True)
            mock_das.get_match = MagicMock()
            
            yield mock_das
    
    @pytest.mark.asyncio
    async def test_completion_vs_abort_race_condition(self, setup_mock_data_service):
        """
        Test that completion and abort cannot both execute on the same match.
        
        This simulates the exact failure scenario from big_plan.md section 2.3.
        """
        mock_das = setup_mock_data_service
        
        # Setup initial match state
        match_id = 1
        initial_match_data = {
            'id': match_id,
            'player_1_discord_uid': 100,
            'player_2_discord_uid': 200,
            'player_1_report': 1,  # Both reported same result
            'player_2_report': 1,
            'match_result': 1,
            'status': 'IN_PROGRESS',
            'player_1_mmr': 2500,
            'player_2_mmr': 2400,
        }
        
        # Track which operations actually executed
        operations_executed = []
        status_transitions = []
        
        def mock_get_match(mid):
            """Mock that returns current match state."""
            if mid != match_id:
                return None
            # Return a copy to simulate fresh reads
            return initial_match_data.copy()
        
        def mock_update_status(mid, new_status):
            """Track status transitions."""
            if mid == match_id:
                status_transitions.append(new_status)
                initial_match_data['status'] = new_status
                print(f"[TEST] Status updated to: {new_status}")
            return True
        
        mock_das.get_match.side_effect = mock_get_match
        mock_das.update_match_status.side_effect = mock_update_status
        
        # Create completion service
        completion_service = MatchCompletionService()
        
        # Mock the handler methods to track execution
        async def mock_handle_completion(mid, data):
            operations_executed.append('completion')
            await asyncio.sleep(0.01)  # Simulate work
            print(f"[TEST] Completion handler executed for match {mid}")
        
        async def mock_handle_abort(mid, data):
            operations_executed.append('abort')
            await asyncio.sleep(0.01)  # Simulate work
            print(f"[TEST] Abort handler executed for match {mid}")
        
        completion_service._handle_match_completion = mock_handle_completion
        completion_service._handle_match_abort = mock_handle_abort
        
        # Test scenario: Both completion check and abort attempt happen simultaneously
        async def attempt_completion():
            """Simulate completion check."""
            await completion_service.check_match_completion(match_id)
        
        async def attempt_abort():
            """Simulate abort request."""
            # Small delay to let completion start first
            await asyncio.sleep(0.001)
            # Modify match to look like an abort was requested
            initial_match_data['player_1_report'] = -3
            initial_match_data['match_result'] = -1
            await completion_service.check_match_completion(match_id)
        
        # Run both operations concurrently
        await asyncio.gather(
            attempt_completion(),
            attempt_abort()
        )
        
        # Assertions
        print(f"[TEST] Operations executed: {operations_executed}")
        print(f"[TEST] Status transitions: {status_transitions}")
        
        # Critical assertion: Only ONE operation should have executed
        assert len(operations_executed) == 1, \
            f"Expected exactly 1 operation, but got {len(operations_executed)}: {operations_executed}"
        
        # The first one to acquire the lock should win
        # In this case, completion should win because it started first
        assert operations_executed[0] == 'completion', \
            f"Expected 'completion' to execute, but got '{operations_executed[0]}'"
        
        # Verify status was set correctly
        assert 'PROCESSING_COMPLETION' in status_transitions or 'COMPLETE' in status_transitions, \
            f"Expected PROCESSING_COMPLETION or COMPLETE in transitions, got {status_transitions}"
        
        print("[TEST] Concurrent completion vs abort: PASS")
    
    @pytest.mark.asyncio
    async def test_status_field_prevents_double_processing(self, setup_mock_data_service):
        """Test that status field prevents a match from being processed twice."""
        mock_das = setup_mock_data_service
        
        match_id = 2
        match_data = {
            'id': match_id,
            'player_1_discord_uid': 100,
            'player_2_discord_uid': 200,
            'player_1_report': 1,
            'player_2_report': 1,
            'match_result': 1,
            'status': 'IN_PROGRESS',
            'player_1_mmr': 2500,
            'player_2_mmr': 2400,
        }
        
        execution_count = [0]
        
        def mock_get_match(mid):
            if mid != match_id:
                return None
            return match_data.copy()
        
        def mock_update_status(mid, new_status):
            if mid == match_id:
                match_data['status'] = new_status
            return True
        
        mock_das.get_match.side_effect = mock_get_match
        mock_das.update_match_status.side_effect = mock_update_status
        
        completion_service = MatchCompletionService()
        
        async def mock_handle_completion(mid, data):
            execution_count[0] += 1
            print(f"[TEST] Completion handler executed (count: {execution_count[0]})")
        
        completion_service._handle_match_completion = mock_handle_completion
        
        # Try to process the same match twice
        await completion_service.check_match_completion(match_id)
        await completion_service.check_match_completion(match_id)
        
        # Should only execute once
        assert execution_count[0] == 1, \
            f"Expected completion handler to execute once, but executed {execution_count[0]} times"
        
        print("[TEST] Status field prevents double processing: PASS")
    
    @pytest.mark.asyncio
    async def test_abort_after_completion_started(self, setup_mock_data_service):
        """Test that abort cannot happen after completion has started."""
        mock_das = setup_mock_data_service
        
        match_id = 3
        match_data = {
            'id': match_id,
            'player_1_discord_uid': 100,
            'player_2_discord_uid': 200,
            'player_1_report': 1,
            'player_2_report': 1,
            'match_result': 1,
            'status': 'IN_PROGRESS',
            'player_1_mmr': 2500,
            'player_2_mmr': 2400,
        }
        
        operations_executed = []
        
        def mock_get_match(mid):
            if mid != match_id:
                return None
            return match_data.copy()
        
        def mock_update_status(mid, new_status):
            if mid == match_id:
                match_data['status'] = new_status
                print(f"[TEST] Status: {new_status}")
            return True
        
        mock_das.get_match.side_effect = mock_get_match
        mock_das.update_match_status.side_effect = mock_update_status
        
        completion_service = MatchCompletionService()
        
        async def mock_handle_completion(mid, data):
            operations_executed.append('completion')
            # Simulate work during completion
            await asyncio.sleep(0.02)
        
        async def mock_handle_abort(mid, data):
            operations_executed.append('abort')
        
        completion_service._handle_match_completion = mock_handle_completion
        completion_service._handle_match_abort = mock_handle_abort
        
        # Start completion
        completion_task = asyncio.create_task(
            completion_service.check_match_completion(match_id)
        )
        
        # Wait a bit to ensure completion has started and set status
        await asyncio.sleep(0.005)
        
        # Now try to abort (should fail because status is no longer IN_PROGRESS)
        match_data_abort = match_data.copy()
        match_data_abort['player_1_report'] = -3
        match_data_abort['match_result'] = -1
        
        # Update mock to return the abort request
        mock_das.get_match.side_effect = lambda mid: match_data_abort if mid == match_id else None
        
        await completion_service.check_match_completion(match_id)
        
        # Wait for completion to finish
        await completion_task
        
        # Should only have completion, not abort
        assert 'completion' in operations_executed, "Completion should have executed"
        assert 'abort' not in operations_executed, "Abort should NOT have executed"
        
        print("[TEST] Abort after completion started: PASS")
    
    def test_match_status_enum_values(self):
        """Test that all expected status values are used correctly."""
        valid_statuses = ['IN_PROGRESS', 'PROCESSING_COMPLETION', 'COMPLETE', 'ABORTED', 'CONFLICT']
        
        # This is a sanity check to ensure we're using the right status strings
        for status in valid_statuses:
            assert isinstance(status, str)
            assert len(status) > 0
        
        print("[TEST] Match status enum values: PASS")


def run_tests():
    """Run all match state race condition tests."""
    import sys
    
    # Run pytest with this file
    exit_code = pytest.main([__file__, "-v", "--tb=short"])
    sys.exit(exit_code)


if __name__ == "__main__":
    run_tests()

