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


def initialize_pool(dsn: str, min_conn: int = 2, max_conn: int = 15, force: bool = False) -> None:
    """
    Initialize the global connection pool. Should be called once at startup.
    
    All connections in the pool will use RealDictCursor for returning rows as dictionaries.
    
    Args:
        dsn: PostgreSQL connection string
        min_conn: Minimum number of connections to maintain
        max_conn: Maximum number of connections allowed
        force: If True, close existing pool and reinitialize (for worker processes)
        
    Raises:
        psycopg2.OperationalError: If connection pool cannot be initialized
    """
    global _global_pool
    if _global_pool is not None:
        if not force:
            print("[DB Pool] WARNING: Pool already initialized.")
            return
        else:
            # Close existing pool and reinitialize (worker process scenario)
            print("[DB Pool] Force reinitialization - closing existing pool...")
            try:
                _global_pool.closeall()
            except Exception:
                pass
            _global_pool = None

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


def _validate_connection(conn) -> bool:
    """
    Check if a connection is still alive and usable.
    
    Args:
        conn: PostgreSQL connection to validate
        
    Returns:
        True if connection is valid, False otherwise
    """
    try:
        # Use a simple query to check connection health
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        return True
    except Exception:
        return False


@contextmanager
def get_connection():
    """
    Provide a managed connection from the pool with deterministic cleanup.
    
    This context manager ensures connections are always properly returned to the pool
    or explicitly closed if invalid. The cleanup logic is simplified to prevent
    connection leaks from swallowed exceptions.
    
    Usage:
        with get_connection() as conn:
            # use conn
            
    Yields:
        psycopg2 connection from the pool
        
    Raises:
        RuntimeError: If pool has not been initialized
        psycopg2.OperationalError: If connection cannot be obtained after retries
    """
    if _global_pool is None:
        raise RuntimeError("Database connection pool has not been initialized.")
    
    conn = None
    connection_is_bad = False
    
    try:
        conn = _global_pool.getconn()
        yield conn
        conn.commit()
        print("[DB Pool] Transaction committed successfully")
        
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        # Connection-level errors indicate the connection is dead
        connection_is_bad = True
        print(f"[DB Pool] Connection error detected: {e}. Marking connection as bad.")
        if conn:
            try:
                conn.close()
                print("[DB Pool] Bad connection closed successfully")
            except Exception as close_exc:
                print(f"[DB Pool] Error closing bad connection: {close_exc}")
        conn = None  # Prevent returning to pool
        raise
        
    except Exception:
        # Application-level errors - rollback transaction
        if conn:
            try:
                conn.rollback()
                print("[DB Pool] Transaction rolled back due to error")
            except Exception as rollback_exc:
                # If rollback fails, connection is probably dead
                connection_is_bad = True
                print(f"[DB Pool] Rollback failed: {rollback_exc}. Marking connection as bad.")
        raise
        
    finally:
        # Deterministic cleanup: always return to pool unless explicitly marked bad
        if conn and not connection_is_bad:
            _global_pool.putconn(conn)
            print("[DB Pool] Connection returned to pool")
        elif conn:
            # Connection is bad but wasn't closed yet
            try:
                conn.close()
                print("[DB Pool] Bad connection closed in finally block")
            except Exception as final_close_exc:
                print(f"[DB Pool] Failed to close bad connection in finally: {final_close_exc}")


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

