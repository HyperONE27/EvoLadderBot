"""
Integration tests for replay job queue resilience and crash recovery.

These tests verify the end-to-end "crash and recover" workflow, proving that
jobs persisted in the SQLite database are successfully recovered and processed
after an application restart (simulated by creating separate queue instances).
"""

import pytest
import asyncio
import tempfile
from pathlib import Path

from src.backend.services.replay_job_queue import (
    ReplayJobQueue,
    ReplayJobProcessor,
    JobStatus
)


class TestJobQueueResilience:
    """Test that jobs survive crashes and restarts."""
    
    def test_job_survives_restart_and_is_processed(self):
        """
        Verify that a job persisted to disk is recovered and processed
        successfully after a simulated bot restart.
        
        This test simulates:
        1. Bot adds a job to the queue (job is saved to SQLite)
        2. Bot crashes (queue instance is destroyed)
        3. Bot restarts (new queue instance connects to same database)
        4. Processor recovers and processes the job
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_queue.db")
            
            # === PHASE 1: Before Crash ===
            queue_before = ReplayJobQueue(db_path)
            
            # Add a job
            job_id = queue_before.add_job(
                message_id=100,
                channel_id=200,
                user_id=300,
                match_id=400
            )
            assert job_id == 1, "First job should have ID 1"
            
            # Verify the job was persisted
            stats_before = queue_before.get_stats()
            assert stats_before[JobStatus.PENDING.value] == 1, \
                "Should have 1 pending job before crash"
            
            # Simulate crash: release the connection
            queue_before.close()
            
            # === PHASE 2: After Restart ===
            queue_after = ReplayJobQueue(db_path)
            
            # Verify the job was recovered from disk
            stats_after = queue_after.get_stats()
            assert stats_after[JobStatus.PENDING.value] == 1, \
                "Should recover 1 pending job after restart"
            
            # Retrieve the pending job
            pending_jobs = queue_after.get_pending_jobs()
            assert len(pending_jobs) == 1, "Should have 1 pending job to process"
            
            job_to_process = pending_jobs[0]
            assert job_to_process.job_id == job_id, "Job ID should match"
            assert job_to_process.status == JobStatus.PENDING, "Job should still be PENDING"
            
            # === PHASE 3: Process the Recovered Job ===
            async def test_processing():
                # Define a mock parse function that succeeds
                async def mock_parse_func(job):
                    return {"success": True, "replay_id": 999}
                
                # Create processor and process the job
                processor = ReplayJobProcessor(queue_after, mock_parse_func)
                await processor._process_job(job_to_process)
            
            # Run the async processing
            asyncio.run(test_processing())
            
            # === PHASE 4: Verify Final State ===
            final_stats = queue_after.get_stats()
            assert final_stats[JobStatus.COMPLETED.value] == 1, \
                "Job should be marked as COMPLETED after processing"
            assert final_stats[JobStatus.PENDING.value] == 0, \
                "No pending jobs should remain"
            
            # Verify the job was actually updated in the database
            completed_job = queue_after.get_job(job_id)
            assert completed_job.status == JobStatus.COMPLETED, \
                "Job status in database should be COMPLETED"
            assert completed_job.parse_result == {"success": True, "replay_id": 999}, \
                "Job should contain the parse result"
            
            queue_after.close()
    
    def test_multiple_jobs_survive_restart(self):
        """
        Verify that multiple jobs all survive a crash and restart,
        and can be processed in batch.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_queue_multi.db")
            
            # === PHASE 1: Before Crash ===
            queue_before = ReplayJobQueue(db_path)
            
            # Add multiple jobs
            job_ids = []
            for i in range(3):
                job_id = queue_before.add_job(
                    message_id=100 + i,
                    channel_id=200 + i,
                    user_id=300 + i
                )
                job_ids.append(job_id)
            
            stats_before = queue_before.get_stats()
            assert stats_before[JobStatus.PENDING.value] == 3, \
                "Should have 3 pending jobs before crash"
            
            queue_before.close()
            
            # === PHASE 2: After Restart ===
            queue_after = ReplayJobQueue(db_path)
            
            stats_after = queue_after.get_stats()
            assert stats_after[JobStatus.PENDING.value] == 3, \
                "Should recover 3 pending jobs after restart"
            
            pending_jobs = queue_after.get_pending_jobs(limit=10)
            assert len(pending_jobs) == 3, "Should retrieve all 3 pending jobs"
            
            # === PHASE 3: Process all jobs ===
            async def process_all():
                async def mock_parse_func(job):
                    return {"processed": True, "job_id": job.job_id}
                
                processor = ReplayJobProcessor(queue_after, mock_parse_func, max_concurrent=3)
                
                for job in pending_jobs:
                    await processor._process_job(job)
            
            asyncio.run(process_all())
            
            # === PHASE 4: Verify All Jobs Completed ===
            final_stats = queue_after.get_stats()
            assert final_stats[JobStatus.COMPLETED.value] == 3, \
                "All 3 jobs should be completed"
            assert final_stats[JobStatus.PENDING.value] == 0, \
                "No pending jobs should remain"
            
            queue_after.close()
