"""
Manages a singleton PostgreSQL connection pool for the application.

This module provides connection pooling to significantly improve database
performance by reusing connections instead of creating new ones for each query.
"""

from typing import Optional
import psycopg2
import psycopg2.extras
from psycopg2 import pool
from contextlib import contextmanager


# This global variable will hold the single pool instance.
_global_pool: Optional[pool.SimpleConnectionPool] = None


def initialize_pool(dsn: str, min_conn: int = 2, max_conn: int = 15) -> None:
    """
    Initialize the global connection pool. Should be called once at startup.
    
    All connections in the pool will use RealDictCursor for returning rows as dictionaries.
    
    Args:
        dsn: PostgreSQL connection string
        min_conn: Minimum number of connections to maintain
        max_conn: Maximum number of connections allowed
        
    Raises:
        psycopg2.OperationalError: If connection pool cannot be initialized
    """
    global _global_pool
    if _global_pool is not None:
        print("[DB Pool] WARNING: Pool already initialized.")
        return

    try:
        print(f"[DB Pool] Initializing pool (min={min_conn}, max={max_conn})...")
        _global_pool = pool.SimpleConnectionPool(
            minconn=min_conn,
            maxconn=max_conn,
            dsn=dsn,
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        print("[DB Pool] Connection pool initialized successfully.")
    except psycopg2.OperationalError as e:
        print(f"[DB Pool] FATAL: Failed to initialize connection pool: {e}")
        _global_pool = None
        raise


@contextmanager
def get_connection():
    """
    Provide a managed connection from the pool.
    
    Usage:
        with get_connection() as conn:
            # use conn
            
    Yields:
        psycopg2 connection from the pool
        
    Raises:
        RuntimeError: If pool has not been initialized
    """
    if _global_pool is None:
        raise RuntimeError("Database connection pool has not been initialized.")
    
    conn = None
    try:
        conn = _global_pool.getconn()
        yield conn
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            _global_pool.putconn(conn)


def close_pool() -> None:
    """
    Close all connections in the pool. Should be called at shutdown.
    """
    global _global_pool
    if _global_pool:
        print("[DB Pool] Closing all connections in the pool...")
        _global_pool.closeall()
        _global_pool = None
        print("[DB Pool] Connection pool closed.")

