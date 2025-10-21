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
    Provide a managed connection from the pool.
    
    This function validates connections before use and handles stale connections
    by getting a fresh one from the pool. If a connection is closed/stale, it's
    discarded and a new one is obtained.
    
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
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            conn = _global_pool.getconn()
            
            # Validate the connection before using it
            if not _validate_connection(conn):
                print(f"[DB Pool] Connection validation failed (attempt {retry_count + 1}/{max_retries}), getting fresh connection...")
                # Close the stale connection and remove it from pool
                try:
                    conn.close()
                except Exception:
                    pass
                # Get a new connection on next iteration
                conn = None
                retry_count += 1
                continue
            
            # Connection is valid, use it
            yield conn
            
            # Only commit if connection is still open
            if conn and not conn.closed:
                conn.commit()
            break
            
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            # Connection errors - try to get a fresh connection
            print(f"[DB Pool] Connection error (attempt {retry_count + 1}/{max_retries}): {e}")
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
            retry_count += 1
            if retry_count >= max_retries:
                raise
            
        except Exception as e:
            # Other errors - rollback if connection is still open
            if conn and not conn.closed:
                try:
                    conn.rollback()
                except Exception:
                    # If rollback fails, connection is dead - close it
                    try:
                        conn.close()
                    except Exception:
                        pass
            raise
            
        finally:
            # Return connection to pool only if it's still valid
            if conn:
                try:
                    # Check if connection is still usable before returning to pool
                    if not conn.closed and _validate_connection(conn):
                        _global_pool.putconn(conn)
                    else:
                        # Connection is dead, close it and don't return to pool
                        try:
                            conn.close()
                        except Exception:
                            pass
                except Exception:
                    # If validation fails, try to close the connection
                    try:
                        conn.close()
                    except Exception:
                        pass


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

