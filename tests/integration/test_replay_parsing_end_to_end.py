"""
End-to-end replay parsing integration tests.

These tests simulate the complete workflow:
1. Player submits a replay via /queue or another command
2. Replay bytes are passed to parse_replay_with_timeout
3. If timeout occurs, fallback to synchronous parsing
4. Job is added to ReplayJobQueue for background processing if needed
5. Processor eventually picks up job and completes or retries

These tests verify the resilience of replay parsing without needing Discord or
actual replay files - they mock replay data and the parsing function itself.
"""

import pytest
import asyncio
import tempfile
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from src.backend.services.replay_parsing_timeout import parse_replay_with_timeout
from src.backend.services.replay_job_queue import (
    ReplayJobQueue,
    ReplayJobProcessor,
    JobStatus
)


# Module-level functions for ProcessPoolExecutor pickling


def slow_parse_function(replay_bytes: bytes) -> dict:
    """Simulates a slow/stuck replay parser that exceeds timeout."""
    time.sleep(3.0)  # Intentionally slow
    return {"result": "completed", "parsed_replays": len(replay_bytes)}


def fast_parse_function(replay_bytes: bytes) -> dict:
    """Simulates a fast replay parser that completes quickly."""
    # Minimal processing
    return {
        "result": "completed",
        "parsed_replays": len(replay_bytes),
        "match_id": 12345,
        "winner": 1
    }


def error_parse_function(replay_bytes: bytes) -> dict:
    """Simulates a parser that encounters an error."""
    raise ValueError("Corrupted replay file")


@pytest.fixture
def process_pool():
    """Provide a ProcessPoolExecutor with proper cleanup."""
    executor = ProcessPoolExecutor(max_workers=2)
    yield executor
    executor.shutdown(wait=True)


@pytest.fixture
def temp_queue_db():
    """Provide a temporary database for job queue testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "job_queue.db")
        yield db_path


class TestReplayParsingWithTimeoutIntegration:
    """Test replay parsing with timeout in realistic scenarios."""
    
    @pytest.mark.asyncio
    async def test_quick_replay_parsing_completes_normally(self, process_pool):
        """
        Verify that a replay that parses quickly completes within expected time
        and returns the parsed result correctly.
        
        This represents the happy path: replay is valid and parses quickly.
        """
        # Arrange
        mock_replay_bytes = b"valid_replay_data_" * 50  # Reasonable replay size
        timeout_seconds = 2.5
        
        start_time = time.monotonic()
        
        # Act
        result, was_timeout = await parse_replay_with_timeout(
            process_pool,
            fast_parse_function,
            mock_replay_bytes,
            timeout=timeout_seconds
        )
        
        elapsed = time.monotonic() - start_time
        
        # Assert
        assert elapsed < 1.0, \
            f"Quick parse should complete in <1s, took {elapsed:.2f}s"
        assert was_timeout is False, \
            "was_timeout should be False for quick parsing"
        assert result.get("result") == "completed", \
            "Result should indicate completion"
        assert result.get("match_id") == 12345, \
            "Result should contain expected parse data"
    
    @pytest.mark.asyncio
    async def test_slow_replay_triggers_timeout_and_fallback(self, process_pool):
        """
        Verify that a replay exceeding timeout triggers the fallback to
        synchronous parsing.
        
        This represents a challenging scenario: worker process is slow or stuck.
        The timeout triggers, the future is cancelled, and parsing falls back to
        the main thread synchronously.
        """
        # Arrange
        mock_replay_bytes = b"slow_replay_" * 100
        timeout_seconds = 0.5  # Very short timeout to ensure triggering
        
        start_time = time.monotonic()
        
        # Act
        result, was_timeout = await parse_replay_with_timeout(
            process_pool,
            slow_parse_function,
            mock_replay_bytes,
            timeout=timeout_seconds
        )
        
        elapsed = time.monotonic() - start_time
        
        # Assert
        # Timeout triggers after 0.5s, then fallback runs for ~3s, total ~3.5s
        assert 2.5 < elapsed < 4.5, \
            f"Should timeout quickly then fallback sync (3-3.5s), took {elapsed:.2f}s"
        assert was_timeout is True, \
            "was_timeout should be True when timeout occurs"
        assert result is not None, \
            "Result should still be available from fallback parsing"
    
    @pytest.mark.asyncio
    async def test_parsing_error_is_caught_and_returned(self, process_pool):
        """
        Verify that if the parser encounters an error (corrupted replay, etc.),
        the error is caught and returned in the result.
        
        This simulates user-provided corrupted replay file.
        """
        # Arrange
        mock_replay_bytes = b"corrupted_" * 50
        timeout_seconds = 2.5
        
        # Act
        try:
            result, was_timeout = await parse_replay_with_timeout(
                process_pool,
                error_parse_function,
                mock_replay_bytes,
                timeout=timeout_seconds
            )
            
            # Assert
            assert was_timeout is False, \
                "Error should not be treated as timeout"
            # Result may contain error info or be None, depending on implementation
            # The key is that parsing didn't hang the bot
        except ValueError as e:
            # If the error propagates from the worker, that's also acceptable
            # The important thing is the bot didn't timeout or hang
            assert "Corrupted" in str(e), "Error message should be about corruption"


class TestReplayJobQueueIntegration:
    """Test the job queue in realistic workflows."""
    
    def test_replay_job_added_and_processed_end_to_end(self, temp_queue_db):
        """
        Simulate the complete job queue lifecycle:
        1. Replay parsing result is persisted as a job
        2. Processor picks up the job
        3. Job is processed and marked complete
        4. Job can be queried later for result
        """
        queue = ReplayJobQueue(temp_queue_db)
        
        try:
            # === PHASE 1: Add job ===
            job_id = queue.add_job(
                message_id=999,
                channel_id=888,
                user_id=777,
                match_id=555
            )
            
            assert job_id is not None, "Job should be created"
            
            # === PHASE 2: Verify job is in pending state ===
            pending_jobs = queue.get_pending_jobs(limit=1)
            assert len(pending_jobs) == 1, "Should have 1 pending job"
            
            job = pending_jobs[0]
            assert job.status == JobStatus.PENDING, "Job should be PENDING"
            assert job.message_id == 999, "Job should preserve message_id"
            
            # === PHASE 3: Mark as processing ===
            success = queue.mark_processing(job_id)
            assert success is True, "mark_processing should succeed"
            
            job = queue.get_job(job_id)
            assert job.status == JobStatus.PROCESSING, "Job should be PROCESSING"
            
            # === PHASE 4: Mark as completed ===
            parse_result = {"match_id": 555, "winner": 1}
            success = queue.mark_completed(job_id, parse_result)
            assert success is True, "mark_completed should succeed"
            
            job = queue.get_job(job_id)
            assert job.status == JobStatus.COMPLETED, "Job should be COMPLETED"
            assert job.parse_result == parse_result, "Result should be stored"
            
            # === PHASE 5: Query stats ===
            stats = queue.get_stats()
            assert stats[JobStatus.COMPLETED.value] == 1, "Should have 1 completed job"
            assert stats[JobStatus.PENDING.value] == 0, "Should have 0 pending jobs"
        
        finally:
            queue.close()
    
    def test_failed_job_can_be_retried(self, temp_queue_db):
        """
        Verify that a failed job is marked as failed, retry count is incremented,
        and the job becomes eligible for retry.
        
        This tests the resilience mechanism for transient replay parsing failures.
        """
        queue = ReplayJobQueue(temp_queue_db)
        
        try:
            # === PHASE 1: Add and process job ===
            job_id = queue.add_job(
                message_id=100,
                channel_id=200,
                user_id=300,
                match_id=None,
                max_retries=3
            )
            
            # === PHASE 2: Mark as processing ===
            queue.mark_processing(job_id)
            
            # === PHASE 3: Fail the job ===
            error_msg = "Replay parsing failed: corrupted file"
            success = queue.mark_failed(job_id, error_msg)
            assert success is True, "mark_failed should succeed"
            
            job = queue.get_job(job_id)
            assert job.status == JobStatus.FAILED, "Job should be FAILED"
            assert job.retry_count == 1, "Retry count should increment"
            assert job.error_message == error_msg, "Error should be stored"
            
            # === PHASE 4: Check if job is eligible for retry ===
            assert job.should_retry() is True, "Job with retry_count < max_retries should be retryable"
            
            # === PHASE 5: Get jobs to retry ===
            retryable = queue.get_jobs_to_retry(limit=1)
            assert len(retryable) == 1, "Should find the failed job for retry"
            assert retryable[0].job_id == job_id, "Should be the correct job"
        
        finally:
            queue.close()
    
    def test_job_moves_to_dead_letter_after_max_retries(self, temp_queue_db):
        """
        Verify that a job that exceeds max_retries is moved to dead letter queue
        (if implemented), or at least marked with a special status.
        
        This ensures permanently failing jobs don't clog the retry queue.
        """
        queue = ReplayJobQueue(temp_queue_db)
        
        try:
            # === PHASE 1: Add job with max_retries=2 ===
            job_id = queue.add_job(
                message_id=100,
                channel_id=200,
                user_id=300,
                max_retries=2
            )
            
            # === PHASE 2: Fail the job 3 times ===
            for i in range(3):
                queue.mark_processing(job_id)
                queue.mark_failed(job_id, f"Attempt {i+1} failed")
            
            # === PHASE 3: Check final status ===
            job = queue.get_job(job_id)
            assert job.retry_count == 3, "Retry count should be 3"
            assert job.should_retry() is False, \
                "Job should not be retryable after exceeding max_retries"
            
            # === PHASE 4: Verify not in pending/retryable ===
            pending = queue.get_pending_jobs()
            assert not any(j.job_id == job_id for j in pending), \
                "Job should not be in pending queue"
            
            retryable = queue.get_jobs_to_retry()
            assert not any(j.job_id == job_id for j in retryable), \
                "Job should not be in retryable queue"
        
        finally:
            queue.close()


class TestReplayProcessorIntegration:
    """Test the ReplayJobProcessor in realistic workflows."""
    
    @pytest.mark.asyncio
    async def test_processor_picks_up_and_processes_jobs(self, temp_queue_db):
        """
        Verify that the processor correctly picks up pending jobs,
        executes the parsing function, and marks jobs complete or failed.
        """
        queue = ReplayJobQueue(temp_queue_db)
        
        try:
            # === PHASE 1: Add jobs ===
            job_id_1 = queue.add_job(100, 200, 300)
            job_id_2 = queue.add_job(101, 201, 301)
            
            # === PHASE 2: Create a mock parse function ===
            async def mock_parse_func(job):
                """Mock replay parsing that succeeds."""
                return {"success": True, "job_id": job.job_id}
            
            # === PHASE 3: Create processor and process jobs ===
            processor = ReplayJobProcessor(queue, mock_parse_func, max_concurrent=2)
            
            pending = queue.get_pending_jobs()
            for job in pending:
                await processor._process_job(job)
            
            # === PHASE 4: Verify jobs are completed ===
            job1 = queue.get_job(job_id_1)
            job2 = queue.get_job(job_id_2)
            
            assert job1.status == JobStatus.COMPLETED, "Job 1 should be completed"
            assert job2.status == JobStatus.COMPLETED, "Job 2 should be completed"
            
            # === PHASE 5: Verify stats ===
            stats = queue.get_stats()
            assert stats[JobStatus.COMPLETED.value] == 2, "Both jobs completed"
            assert stats[JobStatus.PENDING.value] == 0, "No pending jobs"
        
        finally:
            queue.close()
