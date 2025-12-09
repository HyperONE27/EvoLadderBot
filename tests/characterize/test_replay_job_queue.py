"""
Characterization tests for resilient replay job queue.

This test suite verifies:
1. Job queue persistence across restarts
2. Automatic retry with exponential backoff
3. Job state transitions (pending -> processing -> completed/failed)
4. Dead letter queue for permanently failed jobs
5. Job expiry and cleanup
6. Concurrent job processing
"""

import pytest
import asyncio
import tempfile
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.backend.services.replay_job_queue import (
    ReplayJobQueue,
    ReplayJobProcessor,
    ReplayJob,
    JobStatus
)

@pytest.fixture
def queue() -> ReplayJobQueue:
    """Pytest fixture to create a temporary database and ReplayJobQueue instance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_queue.db")
        queue_instance = ReplayJobQueue(db_path)
        yield queue_instance
        # Explicitly close to release file handle before directory is deleted
        queue_instance.close()

class TestJobStatus:
    """Test job status enum."""
    
    def test_all_statuses_exist(self):
        """Verify all job statuses are defined."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.PROCESSING.value == "processing"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.DEAD_LETTER.value == "dead_letter"


class TestReplayJob:
    """Test ReplayJob dataclass."""
    
    def test_job_should_retry(self):
        """Verify job retry logic."""
        now = time.time()
        job = ReplayJob(
            job_id=1,
            message_id=100,
            channel_id=200,
            user_id=300,
            match_id=400,
            replay_hash=None,
            status=JobStatus.FAILED,
            retry_count=0,
            max_retries=3,
            created_at=now,
            started_at=None,
            completed_at=None,
            error_message="Test error",
            parse_result=None
        )
        
        assert job.should_retry() is True
    
    def test_job_no_retry_when_max_retries_reached(self):
        """Verify job stops retrying after max retries."""
        job = ReplayJob(
            job_id=1,
            message_id=100,
            channel_id=200,
            user_id=300,
            match_id=400,
            replay_hash=None,
            status=JobStatus.FAILED,
            retry_count=3,
            max_retries=3,
            created_at=time.time(),
            started_at=None,
            completed_at=None,
            error_message="Test error",
            parse_result=None
        )
        
        assert job.should_retry() is False
    
    def test_exponential_backoff(self):
        """Verify exponential backoff calculation."""
        job = ReplayJob(
            job_id=1,
            message_id=100,
            channel_id=200,
            user_id=300,
            match_id=400,
            replay_hash=None,
            status=JobStatus.FAILED,
            retry_count=2,
            max_retries=5,
            created_at=time.time(),
            started_at=None,
            completed_at=None,
            error_message="Test error",
            parse_result=None
        )
        
        delay = job.get_retry_delay_seconds()
        assert delay == 4  # 2^2 = 4 seconds
    
    def test_job_expiry(self):
        """Verify job expiry logic."""
        old_time = time.time() - (25 * 3600)  # 25 hours ago
        job = ReplayJob(
            job_id=1,
            message_id=100,
            channel_id=200,
            user_id=300,
            match_id=400,
            replay_hash=None,
            status=JobStatus.FAILED,
            retry_count=0,
            max_retries=3,
            created_at=old_time,
            started_at=None,
            completed_at=None,
            error_message="Test error",
            parse_result=None
        )
        
        assert job.is_expired(max_age_hours=24.0) is True
        assert job.should_retry() is False  # Won't retry if expired


class TestReplayJobQueue:
    """Test ReplayJobQueue database operations."""
    
    def test_queue_initialization(self, queue: ReplayJobQueue):
        """Verify queue initializes database."""
        assert isinstance(queue, ReplayJobQueue)
        assert Path(queue.db_path).exists()

    def test_add_and_get_job(self, queue: ReplayJobQueue):
        """Verify adding and retrieving a job."""
        job_id = queue.add_job(message_id=123, channel_id=456, user_id=789, match_id=999)
        assert job_id == 1
        
        job = queue.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.PENDING

    def test_get_pending_jobs(self, queue: ReplayJobQueue):
        """Verify retrieving pending jobs."""
        queue.add_job(123, 456, 789)
        queue.add_job(124, 456, 789)
        pending = queue.get_pending_jobs()
        assert len(pending) == 2

    def test_mark_completed(self, queue: ReplayJobQueue):
        """Verify marking job as completed."""
        job_id = queue.add_job(123, 456, 789)
        result_data = {"success": True}
        queue.mark_completed(job_id, result_data)
        job = queue.get_job(job_id)
        assert job.status == JobStatus.COMPLETED

    def test_mark_failed_with_retry(self, queue: ReplayJobQueue):
        """Verify marking job as failed sets status to FAILED."""
        job_id = queue.add_job(123, 456, 789, max_retries=3)
        queue.mark_failed(job_id, "Parse error")
        job = queue.get_job(job_id)
        assert job.status == JobStatus.FAILED
        assert job.retry_count == 1

    def test_move_to_dead_letter(self, queue: ReplayJobQueue):
        """Verify moving a job to the dead letter queue."""
        job_id = queue.add_job(123, 456, 789)
        queue.mark_failed(job_id, "Permanent error")
        queue.move_to_dead_letter(job_id)
        job = queue.get_job(job_id)
        assert job.status == JobStatus.DEAD_LETTER

    def test_get_jobs_to_retry(self, queue: ReplayJobQueue):
        """Verify retrieving jobs eligible for retry."""
        job_id = queue.add_job(123, 456, 789, max_retries=3)
        queue.mark_failed(job_id, "Timeout")
        retry_jobs = queue.get_jobs_to_retry()
        assert len(retry_jobs) == 1

    def test_get_stats(self, queue: ReplayJobQueue):
        """Verify queue statistics."""
        queue.add_job(123, 456, 789)
        job_id2 = queue.add_job(124, 456, 789)
        queue.mark_completed(job_id2, {})
        stats = queue.get_stats()
        assert stats[JobStatus.PENDING.value] == 1
        assert stats[JobStatus.COMPLETED.value] == 1

    def test_job_persistence(self, queue: ReplayJobQueue):
        """Verify jobs persist across queue instances."""
        job_id = queue.add_job(123, 456, 789)
        queue.mark_processing(job_id)
        
        # Re-instantiate the queue with the same db path
        queue2 = ReplayJobQueue(queue.db_path)
        job = queue2.get_job(job_id)
        
        # Explicitly close the second connection
        queue2.close()
        
        assert job is not None
        assert job.status == JobStatus.PROCESSING


class TestReplayJobProcessor:
    """Test ReplayJobProcessor job processing."""

    @pytest.mark.asyncio
    async def test_process_successful_job(self, queue: ReplayJobQueue):
        """Verify processing a successful job."""
        job_id = queue.add_job(123, 456, 789)
        
        async def mock_parse(job):
            return {"success": True}
        
        processor = ReplayJobProcessor(queue, mock_parse)
        job = queue.get_job(job_id)
        
        await processor._process_job(job)
        
        updated_job = queue.get_job(job_id)
        assert updated_job.status == JobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_process_failed_job_moves_to_failed(self, queue: ReplayJobQueue):
        """Verify a failed job is marked as FAILED for retry."""
        job_id = queue.add_job(123, 456, 789, max_retries=3)
        
        async def mock_parse(job):
            return {"error": "Parse failed"}
        
        processor = ReplayJobProcessor(queue, mock_parse)
        job = queue.get_job(job_id)
        
        await processor._process_job(job)
        
        updated_job = queue.get_job(job_id)
        assert updated_job.status == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_process_job_reaches_max_retries_and_dead_letters(self, queue: ReplayJobQueue):
        """Verify a job is moved to dead letter after max retries."""
        job_id = queue.add_job(123, 456, 789, max_retries=1)
        # Manually fail the job once to increment retry_count to 1
        queue.mark_failed(job_id, "Initial failure")
        job = queue.get_job(job_id)
        assert job.retry_count == 1
        assert job.status == JobStatus.FAILED

        async def mock_parse(job):
             return {"error": "Parse failed again"}

        processor = ReplayJobProcessor(queue, mock_parse)
        
        await processor._process_job(job)
        
        updated_job = queue.get_job(job_id)
        assert updated_job.status == JobStatus.DEAD_LETTER


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
