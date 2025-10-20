"""
Timed database adapter wrapper for performance monitoring.

Wraps database operations to automatically measure and log query times.
"""

import time
import logging
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from src.backend.db.adapters.database_adapter import DatabaseAdapter

logger = logging.getLogger(__name__)


class TimedDatabaseAdapter:
    """
    Wrapper around DatabaseAdapter that measures query performance.
    
    Automatically logs slow queries and tracks database operation times.
    """
    
    # Query performance thresholds (milliseconds)
    SLOW_QUERY_THRESHOLD = 100
    VERY_SLOW_QUERY_THRESHOLD = 500
    
    def __init__(self, adapter: DatabaseAdapter):
        """
        Initialize timed adapter.
        
        Args:
            adapter: The database adapter to wrap
        """
        self.adapter = adapter
        self._query_count = 0
        self._total_time_ms = 0.0
        
    @contextmanager
    def get_connection(self):
        """Get database connection (pass-through)."""
        with self.adapter.get_connection() as conn:
            yield conn
    
    def _measure_query(self, operation_name: str, query_snippet: str = ""):
        """
        Context manager to measure query time.
        
        Args:
            operation_name: Name of the database operation
            query_snippet: First 100 chars of query for logging
        """
        return _QueryTimer(self, operation_name, query_snippet)
    
    def _log_query_time(
        self, 
        operation_name: str, 
        duration_ms: float, 
        query_snippet: str = ""
    ) -> None:
        """Log query performance."""
        self._query_count += 1
        self._total_time_ms += duration_ms
        
        # Log based on duration
        if duration_ms > self.VERY_SLOW_QUERY_THRESHOLD:
            logger.error(
                f"🔴 VERY SLOW QUERY: {operation_name} took {duration_ms:.2f}ms - {query_snippet}"
            )
        elif duration_ms > self.SLOW_QUERY_THRESHOLD:
            logger.warning(
                f"🟡 SLOW QUERY: {operation_name} took {duration_ms:.2f}ms - {query_snippet}"
            )
        elif duration_ms > 10:
            logger.debug(
                f"[DB] {operation_name}: {duration_ms:.2f}ms"
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get query statistics."""
        avg_time = self._total_time_ms / self._query_count if self._query_count > 0 else 0
        return {
            "query_count": self._query_count,
            "total_time_ms": self._total_time_ms,
            "avg_time_ms": avg_time
        }
    
    def reset_stats(self) -> None:
        """Reset query statistics."""
        self._query_count = 0
        self._total_time_ms = 0.0
    
    # Pass-through methods with timing
    
    def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute a query with timing."""
        query_snippet = query[:100].replace('\n', ' ')
        with self._measure_query("execute", query_snippet):
            return self.adapter.execute(query, params)
    
    def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict]:
        """Fetch one row with timing."""
        query_snippet = query[:100].replace('\n', ' ')
        with self._measure_query("fetch_one", query_snippet):
            return self.adapter.fetch_one(query, params)
    
    def fetch_all(self, query: str, params: tuple = ()) -> List[Dict]:
        """Fetch all rows with timing."""
        query_snippet = query[:100].replace('\n', ' ')
        with self._measure_query("fetch_all", query_snippet):
            return self.adapter.fetch_all(query, params)


class _QueryTimer:
    """Internal context manager for timing queries."""
    
    def __init__(self, timed_adapter: TimedDatabaseAdapter, operation_name: str, query_snippet: str):
        self.timed_adapter = timed_adapter
        self.operation_name = operation_name
        self.query_snippet = query_snippet
        self.start_time = None
        
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        self.timed_adapter._log_query_time(
            self.operation_name, 
            duration_ms, 
            self.query_snippet
        )
        return False

