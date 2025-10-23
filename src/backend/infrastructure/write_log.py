"""
Persistent write-ahead log using SQLite.

This module provides a durable queue for database write operations, ensuring
that writes are not lost during service restarts or crashes. All pending writes
are persisted to disk before being acknowledged.
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import asdict

from src.backend.types.write_job import WriteJob, WriteJobType


class WriteLog:
    """
    SQLite-backed persistent write-ahead log.
    
    This ensures that write operations are durably stored before being processed,
    preventing data loss during service restarts.
    """
    
    def __init__(self, db_path: str):
        """
        Initialize the write log.
        
        Args:
            db_path: Full path to SQLite database file (including filename)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def close(self) -> None:
        """
        Close any open database connections.
        
        This is primarily needed for cleanup in tests on Windows.
        """
        # SQLite connections are opened and closed within context managers,
        # so there's nothing persistent to close. This method exists for
        # completeness and future extension.
        pass
    
    def _init_database(self) -> None:
        """Create the write_log table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS write_log (
                    job_id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    data TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0
                )
            """)
            
            # Create index for efficient querying of pending jobs
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status_created 
                ON write_log(status, created_at)
            """)
            
            conn.commit()
            print(f"[Write Log] Initialized at {self.db_path}")
    
    def enqueue(self, job: WriteJob) -> str:
        """
        Add a write job to the persistent queue.
        
        Args:
            job: WriteJob to persist
            
        Returns:
            job_id: Unique identifier for the job
        """
        job_id = str(uuid.uuid4())
        job_data = {
            'job_type': job.job_type.value,
            'data': job.data,
            'timestamp': job.timestamp
        }
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO write_log 
                (job_id, job_type, data, status, created_at)
                VALUES (?, ?, ?, 'PENDING', ?)
            """, (
                job_id,
                job.job_type.value,
                json.dumps(job_data),
                datetime.now().isoformat()
            ))
            conn.commit()
        
        return job_id
    
    def get_pending_jobs(self, limit: int = 100) -> List[tuple[str, WriteJob]]:
        """
        Retrieve pending jobs from the log.
        
        Args:
            limit: Maximum number of jobs to retrieve
            
        Returns:
            List of (job_id, WriteJob) tuples
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT job_id, data, retry_count
                FROM write_log
                WHERE status = 'PENDING'
                ORDER BY created_at ASC
                LIMIT ?
            """, (limit,))
            
            results = []
            for job_id, data_json, retry_count in cursor.fetchall():
                try:
                    job_data = json.loads(data_json)
                    job = WriteJob(
                        job_type=WriteJobType(job_data['job_type']),
                        data=job_data['data'],
                        timestamp=job_data['timestamp']
                    )
                    # Restore retry count if it exists
                    if retry_count > 0:
                        job.retry_count = retry_count
                    results.append((job_id, job))
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    print(f"[Write Log] Error deserializing job {job_id}: {e}")
                    # Mark as failed so we don't keep retrying
                    self.mark_failed(job_id, f"Deserialization error: {e}")
            
            return results
    
    def mark_completed(self, job_id: str) -> None:
        """
        Mark a job as successfully completed.
        
        Args:
            job_id: ID of the job to mark
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE write_log
                SET status = 'COMPLETED',
                    completed_at = ?
                WHERE job_id = ?
            """, (datetime.now().isoformat(), job_id))
            conn.commit()
    
    def mark_failed(self, job_id: str, error_message: str) -> None:
        """
        Mark a job as permanently failed.
        
        Args:
            job_id: ID of the job to mark
            error_message: Description of the failure
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE write_log
                SET status = 'FAILED',
                    completed_at = ?,
                    error_message = ?
                WHERE job_id = ?
            """, (datetime.now().isoformat(), error_message, job_id))
            conn.commit()
    
    def increment_retry_count(self, job_id: str) -> int:
        """
        Increment the retry counter for a job.
        
        Args:
            job_id: ID of the job
            
        Returns:
            New retry count
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE write_log
                SET retry_count = retry_count + 1
                WHERE job_id = ?
                RETURNING retry_count
            """, (job_id,))
            result = cursor.fetchone()
            conn.commit()
            return result[0] if result else 0
    
    def get_statistics(self) -> Dict[str, int]:
        """
        Get statistics about the write log.
        
        Returns:
            Dictionary with counts by status
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM write_log
                GROUP BY status
            """)
            
            stats = {row[0]: row[1] for row in cursor.fetchall()}
            stats.setdefault('PENDING', 0)
            stats.setdefault('COMPLETED', 0)
            stats.setdefault('FAILED', 0)
            
            return stats
    
    def cleanup_old_completed(self, days: int = 7) -> int:
        """
        Remove completed jobs older than specified days.
        
        Args:
            days: Number of days to retain completed jobs
            
        Returns:
            Number of jobs deleted
        """
        cutoff = datetime.now().timestamp() - (days * 24 * 3600)
        cutoff_iso = datetime.fromtimestamp(cutoff).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM write_log
                WHERE status = 'COMPLETED'
                AND completed_at < ?
            """, (cutoff_iso,))
            conn.commit()
            return cursor.rowcount

