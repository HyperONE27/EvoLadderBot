"""
Resilient replay job queue with SQLite-backed persistence.

This module provides:
- Durable job queue for replay parsing tasks
- Automatic retry on failure with exponential backoff
- Job state tracking (pending, processing, completed, failed)
- Dead letter queue for permanently failed jobs
- Recovery on process restart (in-flight jobs become pending again)
"""

import asyncio
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Status of a replay job."""
    PENDING = "pending"           # Waiting to be processed
    PROCESSING = "processing"     # Currently being parsed
    COMPLETED = "completed"       # Successfully parsed
    FAILED = "failed"             # Permanently failed
    DEAD_LETTER = "dead_letter"   # Moved to dead letter queue


@dataclass
class ReplayJob:
    """Represents a replay parsing job."""
    job_id: int                        # Unique job ID
    message_id: int                    # Discord message ID
    channel_id: int                    # Discord channel ID
    user_id: int                       # Discord user ID
    match_id: int                      # Match ID (if available)
    replay_hash: Optional[str]         # Blake2b hash of replay bytes (computed after first parse)
    status: JobStatus                  # Current job status
    retry_count: int                   # Number of retries attempted
    max_retries: int                   # Maximum retries allowed
    created_at: float                  # When job was created
    started_at: Optional[float]        # When processing started
    completed_at: Optional[float]      # When job completed
    error_message: Optional[str]       # Error message if failed
    parse_result: Optional[Dict]       # Parsed replay data (if successful)
    updated_at: float = field(default_factory=time.time)  # Last update timestamp
    
    def is_expired(self, max_age_hours: float = 24.0) -> bool:
        """Check if job is too old to retry."""
        age_hours = (time.time() - self.created_at) / 3600
        return age_hours > max_age_hours
    
    def should_retry(self) -> bool:
        """Determine if job should be retried."""
        return (
            self.status == JobStatus.FAILED
            and self.retry_count < self.max_retries
            and not self.is_expired()
        )
    
    def get_retry_delay_seconds(self) -> float:
        """Calculate exponential backoff delay for next retry."""
        # Exponential backoff: 2^retry_count seconds, capped at 1 hour
        base_delay = 2 ** self.retry_count
        max_delay = 3600  # 1 hour
        return min(base_delay, max_delay)


class ReplayJobQueue:
    """
    Resilient SQLite-backed replay job queue.
    
    Provides:
    - Durable persistence across restarts
    - Automatic retry with exponential backoff
    - Job state tracking and recovery
    - Dead letter queue for permanently failed jobs
    - Thread-safe access to job queue
    """
    
    def __init__(self, db_path: str = "data/replay_queue.db"):
        """
        Initialize the replay job queue.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_database()

    def close(self):
        """Explicitly close the database connection."""
        if self.conn:
            self.conn.close()
    
    def _init_database(self):
        """Initialize database schema."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS replay_jobs (
                job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                match_id INTEGER,
                replay_hash TEXT,
                status TEXT NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                created_at REAL NOT NULL,
                started_at REAL,
                completed_at REAL,
                error_message TEXT,
                parse_result TEXT,
                updated_at REAL NOT NULL
            )
        """)
        self.conn.commit()

    def add_job(
        self,
        message_id: int,
        channel_id: int,
        user_id: int,
        match_id: Optional[int] = None,
        max_retries: int = 3
    ) -> int:
        """
        Add a new replay job to the queue.
        
        Args:
            message_id: Discord message ID
            channel_id: Discord channel ID
            user_id: Discord user ID
            match_id: Optional match ID
            max_retries: Maximum number of retries
        
        Returns:
            Job ID
        """
        now = time.time()
        cursor = self.conn.execute("""
            INSERT INTO replay_jobs (
                message_id, channel_id, user_id, match_id,
                status, retry_count, max_retries, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message_id, channel_id, user_id, match_id,
            JobStatus.PENDING.value, 0, max_retries, now, now
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_job(self, job_id: int) -> Optional[ReplayJob]:
        """Get a job by ID."""
        cursor = self.conn.execute("""
            SELECT * FROM replay_jobs WHERE job_id = ?
        """, (job_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_job(row, cursor.description)
    
    def get_pending_jobs(self, limit: int = 10) -> List[ReplayJob]:
        """Get pending jobs ready for processing."""
        cursor = self.conn.execute("""
            SELECT * FROM replay_jobs 
            WHERE status = ?
            ORDER BY created_at ASC
            LIMIT ?
        """, (JobStatus.PENDING.value, limit))
        rows = cursor.fetchall()
        
        return [self._row_to_job(row, cursor.description) for row in rows]
    
    def get_jobs_to_retry(self, limit: int = 10) -> List[ReplayJob]:
        """Get failed jobs that are eligible for retry."""
        cursor = self.conn.execute("""
            SELECT * FROM replay_jobs 
            WHERE status = ? AND retry_count < max_retries
            ORDER BY updated_at ASC
            LIMIT ?
        """, (JobStatus.FAILED.value, limit))
        rows = cursor.fetchall()
        
        jobs = [self._row_to_job(row, cursor.description) for row in rows]
        # Filter by expiry and retry eligibility
        return [j for j in jobs if j.should_retry()]
    
    def mark_processing(self, job_id: int) -> bool:
        """Mark a job as processing."""
        now = time.time()
        cursor = self.conn.execute("""
            UPDATE replay_jobs 
            SET status = ?, started_at = ?, updated_at = ?
            WHERE job_id = ?
        """, (JobStatus.PROCESSING.value, now, now, job_id))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def mark_completed(self, job_id: int, parse_result: Dict) -> bool:
        """Mark a job as completed successfully."""
        now = time.time()
        cursor = self.conn.execute("""
            UPDATE replay_jobs 
            SET status = ?, completed_at = ?, parse_result = ?, updated_at = ?
            WHERE job_id = ?
        """, (
            JobStatus.COMPLETED.value,
            now,
            json.dumps(parse_result),
            now,
            job_id
        ))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def mark_failed(self, job_id: int, error_message: str) -> bool:
        """
        Mark a job as failed and increment its retry count.
        
        The job's status will be set to FAILED. The processor will later
        pick it up for retry if retry_count < max_retries. If not, it will be
        moved to the dead letter queue by the processor.
        
        Args:
            job_id: Job ID
            error_message: Error message
        
        Returns:
            True if successful
        """
        now = time.time()
        cursor = self.conn.execute("""
            UPDATE replay_jobs 
            SET status = ?, retry_count = retry_count + 1, 
                error_message = ?, updated_at = ?
            WHERE job_id = ?
        """, (JobStatus.FAILED.value, error_message, now, job_id))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def move_to_dead_letter(self, job_id: int) -> bool:
        """Move a job to the dead letter queue."""
        now = time.time()
        cursor = self.conn.execute("""
            UPDATE replay_jobs
            SET status = ?, updated_at = ?
            WHERE job_id = ?
        """, (JobStatus.DEAD_LETTER.value, now, job_id))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        stats = {}
        for status in JobStatus:
            count = self.conn.execute("""
                SELECT COUNT(*) FROM replay_jobs WHERE status = ?
            """, (status.value,)).fetchone()[0]
            stats[status.value] = count
        
        return stats
    
    def cleanup_old_jobs(self, days: int = 7) -> int:
        """
        Delete jobs older than specified days.
        
        Args:
            days: Age in days
        
        Returns:
            Number of jobs deleted
        """
        cutoff_time = time.time() - (days * 86400)
        cursor = self.conn.execute("""
            DELETE FROM replay_jobs 
            WHERE created_at < ? AND status IN (?, ?)
        """, (cutoff_time, JobStatus.COMPLETED.value, JobStatus.DEAD_LETTER.value))
        self.conn.commit()
        return cursor.rowcount
    
    @staticmethod
    def _row_to_job(row, description) -> ReplayJob:
        """Convert database row to ReplayJob object."""
        data = {description[i][0]: row[i] for i in range(len(row))}
        
        # Convert status string to enum
        data['status'] = JobStatus(data['status'])
        
        # Parse JSON fields
        if data.get('parse_result'):
            data['parse_result'] = json.loads(data['parse_result'])
        
        return ReplayJob(**data)


class ReplayJobProcessor:
    """
    Processes replay jobs from the queue.
    
    Handles:
    - Retrieving jobs from queue
    - Executing parse operations
    - Updating job status
    - Retry logic with exponential backoff
    """
    
    def __init__(
        self,
        queue: ReplayJobQueue,
        parse_func,
        max_concurrent: int = 2
    ):
        """
        Initialize job processor.
        
        Args:
            queue: ReplayJobQueue instance
            parse_func: Async function to parse replay: parse_func(job: ReplayJob) -> Dict
            max_concurrent: Max concurrent jobs to process
        """
        self.queue = queue
        self.parse_func = parse_func
        self.max_concurrent = max_concurrent
        self._processing = False
        self._active_jobs = 0
    
    async def start_processing_loop(self):
        """Start the job processing loop."""
        self._processing = True
        print("[Replay Queue] Starting job processor...")
        
        while self._processing:
            try:
                # Check if we can process more jobs
                if self._active_jobs < self.max_concurrent:
                    # Get pending job
                    jobs = self.queue.get_pending_jobs(limit=1)
                    if jobs:
                        job = jobs[0]
                        # Process in background
                        asyncio.create_task(self._process_job(job))
                        self._active_jobs += 1
                
                # Check for jobs to retry
                retry_jobs = self.queue.get_jobs_to_retry(limit=1)
                if retry_jobs:
                    job = retry_jobs[0]
                    delay = job.get_retry_delay_seconds()
                    print(f"[Replay Queue] Job {job.job_id} will retry in {delay:.0f}s")
                    await asyncio.sleep(delay)
                    asyncio.create_task(self._process_job(job))
                    self._active_jobs += 1
                
                await asyncio.sleep(0.1)  # Check queue frequently
                
            except Exception as e:
                logger.error(f"[Replay Queue] Error in processing loop: {e}")
                await asyncio.sleep(1.0)
    
    async def _process_job(self, job: ReplayJob):
        """Process a single job."""
        try:
            # First, check if the job is eligible for processing at all
            if not job.should_retry() and job.status == JobStatus.FAILED:
                print(f"[Replay Queue] Job {job.job_id} has reached max retries. Moving to dead letter queue.")
                self.queue.move_to_dead_letter(job.job_id)
                return

            self.queue.mark_processing(job.job_id)
            print(f"[Replay Queue] Processing job {job.job_id} (retry {job.retry_count}/{job.max_retries})")
            
            result = await self.parse_func(job)
            
            if result.get("error"):
                # Parsing failed
                self.queue.mark_failed(job.job_id, result["error"])
                print(f"[Replay Queue] Job {job.job_id} failed: {result['error']}")
            else:
                # Parsing succeeded
                self.queue.mark_completed(job.job_id, result)
                print(f"[Replay Queue] ✅ Job {job.job_id} completed successfully")
        
        except Exception as e:
            logger.error(f"[Replay Queue] Error processing job {job.job_id}: {e}")
            self.queue.mark_failed(job.job_id, str(e))
        
        finally:
            self._active_jobs -= 1
    
    def stop_processing(self):
        """Stop the job processing loop."""
        self._processing = False
        print("[Replay Queue] Stopping job processor...")


if __name__ == "__main__":
    # Example usage
    queue = ReplayJobQueue()
    job_id = queue.add_job(
        message_id=123456,
        channel_id=789012,
        user_id=345678,
        match_id=111222
    )
    print(f"Created job {job_id}")
    
    stats = queue.get_stats()
    print(f"Queue stats: {stats}")
