"""
Test suite for failed DB write handling in DataAccessService.

This tests the retry mechanism and dead-letter queue functionality
that was implemented to handle database write failures gracefully.
"""

import asyncio
import json
import os
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.backend.services.data_access_service import DataAccessService, WriteJob, WriteJobType


class TestFailedDBWriteHandling:
    """Test failed database write handling mechanisms."""

    @pytest.fixture
    def data_service(self):
        """Create a DataAccessService instance for testing."""
        service = DataAccessService()
        # Mock the database writer to simulate failures
        service._db_writer = MagicMock()
        return service

    @pytest.fixture
    def temp_log_dir(self):
        """Create a temporary directory for log files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.mark.asyncio
    async def test_write_job_retry_mechanism(self, data_service):
        """Test that failed write jobs are retried up to max_retries times."""
        # Mock the database writer to fail on the first few attempts
        call_count = 0
        def mock_failing_write(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Fail first 2 attempts
                raise Exception(f"Simulated DB failure {call_count}")
            return True  # Succeed on 3rd attempt

        data_service._db_writer.create_player = mock_failing_write

        # Create a write job
        job = WriteJob(
            job_type=WriteJobType.CREATE_PLAYER,
            data={
                'discord_uid': 12345,
                'discord_username': 'testuser',
                'player_name': 'TestUser'
            },
            timestamp=time.time()
        )

        # Process the job (should retry and eventually succeed)
        await data_service._process_write_job(job)

        # Verify it was called 3 times (2 failures + 1 success)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_write_job_dead_letter_queue(self, data_service, temp_log_dir):
        """Test that jobs that fail after max retries are logged to dead-letter queue."""
        # Mock the database writer to always fail
        data_service._db_writer.create_player = MagicMock(side_effect=Exception("Persistent DB failure"))

        # Create a write job
        job = WriteJob(
            job_type=WriteJobType.CREATE_PLAYER,
            data={
                'discord_uid': 12345,
                'discord_username': 'testuser',
                'player_name': 'TestUser'
            },
            timestamp=time.time()
        )

        # Mock the log directory
        with patch('src.backend.services.data_access_service.os.makedirs'):
            with patch('src.backend.services.data_access_service.os.path.join', return_value=os.path.join(temp_log_dir, 'failed_writes.log')):
                # Process the job (should fail after max retries)
                await data_service._process_write_job(job)

        # Verify the job was retried the maximum number of times
        assert data_service._db_writer.create_player.call_count == 4  # 1 initial + 3 retries

    @pytest.mark.asyncio
    async def test_dead_letter_log_format(self, data_service, temp_log_dir):
        """Test that failed jobs are logged in the correct format."""
        # Mock the database writer to always fail
        data_service._db_writer.create_player = MagicMock(side_effect=Exception("Test error"))

        # Create a write job
        job = WriteJob(
            job_type=WriteJobType.CREATE_PLAYER,
            data={
                'discord_uid': 12345,
                'discord_username': 'testuser',
                'player_name': 'TestUser'
            },
            timestamp=time.time()
        )

        # Mock the log directory and file writing
        log_file_path = os.path.join(temp_log_dir, 'failed_writes.log')
        
        with patch('src.backend.services.data_access_service.os.makedirs'):
            with patch('src.backend.services.data_access_service.os.path.join', return_value=log_file_path):
                with patch('builtins.open', create=True) as mock_open:
                    mock_file = MagicMock()
                    mock_open.return_value.__enter__.return_value = mock_file
                    
                    # Process the job
                    await data_service._process_write_job(job)

        # Verify the log entry was written
        mock_file.write.assert_called_once()
        log_entry = mock_file.write.call_args[0][0]
        
        # Parse the JSON log entry
        log_data = json.loads(log_entry.strip())
        
        # Verify the log entry structure
        assert log_data['job_type'] == 'create_player'
        assert log_data['job_data']['discord_uid'] == 12345
        assert log_data['job_data']['discord_username'] == 'testuser'
        assert log_data['job_data']['player_name'] == 'TestUser'
        assert 'Test error' in log_data['error_message']
        assert log_data['retry_count'] == 3  # Max retries reached

    @pytest.mark.asyncio
    async def test_different_job_types_retry(self, data_service):
        """Test that different job types are retried correctly."""
        # Mock different methods to fail
        data_service._db_writer.create_player = MagicMock(side_effect=Exception("Player creation failed"))
        data_service._db_writer.update_mmr_after_match = MagicMock(side_effect=Exception("MMR update failed"))

        # Test CREATE_PLAYER job
        player_job = WriteJob(
            job_type=WriteJobType.CREATE_PLAYER,
            data={'discord_uid': 12345, 'discord_username': 'testuser'},
            timestamp=time.time()
        )

        # Test UPDATE_MMR job
        mmr_job = WriteJob(
            job_type=WriteJobType.UPDATE_MMR,
            data={'discord_uid': 12345, 'race': 'bw_terran', 'new_mmr': 1500},
            timestamp=time.time()
        )

        # Process both jobs
        with patch('src.backend.services.data_access_service.os.makedirs'):
            with patch('src.backend.services.data_access_service.os.path.join'):
                with patch('builtins.open', create=True):
                    await data_service._process_write_job(player_job)
                    await data_service._process_write_job(mmr_job)

        # Verify both were retried the maximum number of times
        assert data_service._db_writer.create_player.call_count == 4  # 1 initial + 3 retries
        assert data_service._db_writer.update_mmr_after_match.call_count == 4  # 1 initial + 3 retries

    @pytest.mark.asyncio
    async def test_retry_count_tracking(self, data_service):
        """Test that retry count is properly tracked and incremented."""
        # Mock the database writer to fail twice then succeed
        call_count = 0
        def mock_failing_write(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception(f"Failure {call_count}")
            return True

        data_service._db_writer.create_player = mock_failing_write

        # Create a write job
        job = WriteJob(
            job_type=WriteJobType.CREATE_PLAYER,
            data={'discord_uid': 12345, 'discord_username': 'testuser'},
            timestamp=time.time()
        )

        # Process the job
        await data_service._process_write_job(job)

        # Verify retry count was tracked correctly
        assert hasattr(job, 'retry_count')
        assert job.retry_count == 2  # Should be 2 after 2 failures and 1 success

    def test_write_job_retry_count_initialization(self):
        """Test that WriteJob retry_count is properly initialized."""
        job = WriteJob(
            job_type=WriteJobType.CREATE_PLAYER,
            data={'discord_uid': 12345},
            timestamp=time.time()
        )

        # Initially, retry_count should not exist
        assert not hasattr(job, 'retry_count')

        # After first failure, it should be initialized to 0 and then incremented
        job.retry_count = 0
        job.retry_count += 1
        assert job.retry_count == 1


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
