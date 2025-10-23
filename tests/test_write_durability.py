"""
Test write durability across service restarts.

This test verifies that the persistent write log ensures no data loss
when the DataAccessService is restarted before pending writes complete.
"""

import asyncio
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from src.backend.services.data_access_service import DataAccessService, WriteJob, WriteJobType
from src.backend.services.write_log import WriteLog


class TestWriteDurability:
    """Test suite for write durability across restarts."""
    
    @pytest.fixture
    def temp_write_log_path(self):
        """Create a temporary directory for write log testing."""
        temp_dir = tempfile.mkdtemp()
        write_log_path = Path(temp_dir) / "write_log.sqlite"
        yield str(write_log_path)
        # Cleanup - retry on Windows if file is locked
        if Path(temp_dir).exists():
            import gc
            gc.collect()
            try:
                shutil.rmtree(temp_dir)
            except PermissionError:
                # On Windows, SQLite may still have the file open
                # Wait a bit and try again
                import time as time_module
                time_module.sleep(0.1)
                try:
                    shutil.rmtree(temp_dir)
                except PermissionError:
                    # Give up and leave it for OS cleanup
                    pass
    
    def test_write_log_persistence(self, temp_write_log_path):
        """Test that write log persists jobs to SQLite correctly."""
        write_log = WriteLog(db_path=temp_write_log_path)
        
        # Create test job
        job = WriteJob(
            job_type=WriteJobType.UPDATE_PLAYER,
            data={"player_id": 123, "mmr": 2500},
            timestamp=time.time()
        )
        
        # Enqueue job
        job_id = write_log.enqueue(job)
        assert job_id is not None
        
        # Verify job is persisted
        pending_jobs = write_log.get_pending_jobs()
        assert len(pending_jobs) == 1
        assert pending_jobs[0][0] == job_id
        
        # Verify job data
        retrieved_job = pending_jobs[0][1]
        assert retrieved_job.job_type == WriteJobType.UPDATE_PLAYER
        assert retrieved_job.data["player_id"] == 123
        assert retrieved_job.data["mmr"] == 2500
        
        print("[TEST] Write log persistence: PASS")
    
    def test_write_log_completion(self, temp_write_log_path):
        """Test that completed jobs are marked correctly."""
        write_log = WriteLog(db_path=temp_write_log_path)
        
        job = WriteJob(
            job_type=WriteJobType.UPDATE_MMR,
            data={"player_id": 456, "new_mmr": 2600},
            timestamp=time.time()
        )
        
        job_id = write_log.enqueue(job)
        
        # Mark as completed
        write_log.mark_completed(job_id)
        
        # Verify no longer in pending
        pending_jobs = write_log.get_pending_jobs()
        assert len(pending_jobs) == 0
        
        # Verify statistics
        stats = write_log.get_statistics()
        assert stats['COMPLETED'] == 1
        assert stats['PENDING'] == 0
        
        print("[TEST] Write log completion: PASS")
    
    def test_write_log_failure_handling(self, temp_write_log_path):
        """Test that failed jobs are marked and tracked correctly."""
        write_log = WriteLog(db_path=temp_write_log_path)
        
        job = WriteJob(
            job_type=WriteJobType.CREATE_MATCH,
            data={"match_id": 789},
            timestamp=time.time()
        )
        
        job_id = write_log.enqueue(job)
        
        # Simulate retry attempts
        retry_count = write_log.increment_retry_count(job_id)
        assert retry_count == 1
        
        retry_count = write_log.increment_retry_count(job_id)
        assert retry_count == 2
        
        # Mark as failed after retries
        write_log.mark_failed(job_id, "Connection timeout after 3 attempts")
        
        # Verify no longer in pending
        pending_jobs = write_log.get_pending_jobs()
        assert len(pending_jobs) == 0
        
        # Verify statistics
        stats = write_log.get_statistics()
        assert stats['FAILED'] == 1
        
        print("[TEST] Write log failure handling: PASS")
    
    def test_write_log_survives_restart(self, temp_write_log_path):
        """Test that write log survives across WriteLog instance restarts."""
        # First instance: enqueue jobs
        write_log_1 = WriteLog(db_path=temp_write_log_path)
        
        job1 = WriteJob(
            job_type=WriteJobType.UPDATE_PLAYER,
            data={"player_id": 100},
            timestamp=time.time()
        )
        job2 = WriteJob(
            job_type=WriteJobType.UPDATE_MMR,
            data={"player_id": 200},
            timestamp=time.time()
        )
        
        job_id_1 = write_log_1.enqueue(job1)
        job_id_2 = write_log_1.enqueue(job2)
        
        del write_log_1
        
        # Second instance: verify jobs are still there
        write_log_2 = WriteLog(db_path=temp_write_log_path)
        pending_jobs = write_log_2.get_pending_jobs()
        
        assert len(pending_jobs) == 2
        job_ids = [job_id for job_id, _ in pending_jobs]
        assert job_id_1 in job_ids
        assert job_id_2 in job_ids
        
        print("[TEST] Write log survives restart: PASS")
    
    def test_write_log_multiple_jobs(self, temp_write_log_path):
        """Test that multiple jobs can be enqueued and retrieved in order."""
        write_log = WriteLog(db_path=temp_write_log_path)
        
        # Enqueue multiple jobs
        jobs_data = [
            (WriteJobType.UPDATE_PLAYER, {"player_id": 1}),
            (WriteJobType.UPDATE_MMR, {"player_id": 2}),
            (WriteJobType.CREATE_MATCH, {"match_id": 3}),
            (WriteJobType.INSERT_REPLAY, {"replay_id": 4}),
        ]
        
        job_ids = []
        for job_type, data in jobs_data:
            job = WriteJob(
                job_type=job_type,
                data=data,
                timestamp=time.time()
            )
            job_id = write_log.enqueue(job)
            job_ids.append(job_id)
        
        # Retrieve all pending jobs
        pending_jobs = write_log.get_pending_jobs(limit=100)
        assert len(pending_jobs) == 4
        
        # Verify order (should be FIFO by created_at)
        retrieved_job_ids = [job_id for job_id, _ in pending_jobs]
        assert retrieved_job_ids == job_ids
        
        # Mark first two as completed
        write_log.mark_completed(job_ids[0])
        write_log.mark_completed(job_ids[1])
        
        # Mark third as failed
        write_log.mark_failed(job_ids[2], "Test failure")
        
        # Only fourth should still be pending
        pending_jobs = write_log.get_pending_jobs()
        assert len(pending_jobs) == 1
        assert pending_jobs[0][0] == job_ids[3]
        
        print("[TEST] Write log multiple jobs: PASS")
    
    def test_simulated_crash_recovery(self, temp_write_log_path):
        """
        Test that data is not lost if service crashes before processing writes.
        
        This simulates the critical failure scenario from big_plan.md section 2.2.
        """
        # Simulate first run: Enqueue critical writes
        write_log_1 = WriteLog(db_path=temp_write_log_path)
        
        # Queue writes that represent a match completion
        match_job = WriteJob(
            job_type=WriteJobType.CREATE_MATCH,
            data={"player_1_id": 1, "player_2_id": 2, "winner_id": 1},
            timestamp=time.time()
        )
        
        mmr_job_1 = WriteJob(
            job_type=WriteJobType.UPDATE_MMR,
            data={"player_id": 1, "new_mmr": 2550},
            timestamp=time.time()
        )
        
        mmr_job_2 = WriteJob(
            job_type=WriteJobType.UPDATE_MMR,
            data={"player_id": 2, "new_mmr": 2450},
            timestamp=time.time()
        )
        
        write_log_1.enqueue(match_job)
        write_log_1.enqueue(mmr_job_1)
        write_log_1.enqueue(mmr_job_2)
        
        # Verify all 3 jobs are pending
        stats_before = write_log_1.get_statistics()
        assert stats_before['PENDING'] == 3
        assert stats_before['COMPLETED'] == 0
        
        # Simulate crash: delete the write_log object without processing
        del write_log_1
        
        # Simulate restart: create new write log instance
        write_log_2 = WriteLog(db_path=temp_write_log_path)
        
        # Verify all jobs survived the "crash"
        pending_jobs = write_log_2.get_pending_jobs()
        assert len(pending_jobs) == 3
        
        # Simulate recovery processing
        for job_id, job in pending_jobs:
            # In real system, these would be processed by _process_write_job
            # Here we just mark them as completed to simulate successful processing
            write_log_2.mark_completed(job_id)
        
        # Verify recovery was successful
        stats_after = write_log_2.get_statistics()
        assert stats_after['COMPLETED'] == 3
        assert stats_after['PENDING'] == 0
        
        print("[TEST] Simulated crash recovery: PASS")


def run_tests():
    """Run all write durability tests."""
    import sys
    
    # Run pytest with this file
    exit_code = pytest.main([__file__, "-v", "--tb=short"])
    sys.exit(exit_code)


if __name__ == "__main__":
    run_tests()

