"""
Manages a singleton PostgreSQL connection pool for the application.

This module provides connection pooling to significantly improve database
performance by reusing connections instead of creating new ones for each query.
"""

import logging
from typing import Optional
import psycopg2
import psycopg2.extras
from psycopg2 import pool
from contextlib import contextmanager

logger = logging.getLogger(__name__)

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
            logger.warning("Pool already initialized")
            return
        else:
            # Close existing pool and reinitialize (worker process scenario)
            logger.warning("Force reinitialization - closing existing pool")
            try:
                _global_pool.closeall()
            except Exception:
                pass
            _global_pool = None

    try:
        logger.info("Initializing connection pool", extra={"min_conn": min_conn, "max_conn": max_conn})
        _global_pool = pool.SimpleConnectionPool(
            minconn=min_conn,
            maxconn=max_conn,
            dsn=dsn,
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        logger.info("Connection pool initialized successfully")
    except psycopg2.OperationalError as e:
        logger.fatal("Failed to initialize connection pool", exc_info=True)
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
        logger.debug("Transaction committed successfully")
        
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        # Connection-level errors indicate the connection is dead
        connection_is_bad = True
        logger.warning("Connection error detected, marking connection as bad", extra={"error": str(e)})
        if conn:
            try:
                conn.close()
                logger.debug("Bad connection closed successfully")
            except Exception as close_exc:
                logger.error("Error closing bad connection", extra={"error": str(close_exc)})
        conn = None  # Prevent returning to pool
        raise
        
    except Exception:
        # Application-level errors - rollback transaction
        if conn:
            try:
                conn.rollback()
                logger.debug("Transaction rolled back due to error")
            except Exception as rollback_exc:
                # If rollback fails, connection is probably dead
                connection_is_bad = True
                logger.error("Rollback failed, marking connection as bad", extra={"error": str(rollback_exc)})
        raise
        
    finally:
        # Deterministic cleanup: always return to pool unless explicitly marked bad
        if conn and not connection_is_bad:
            _global_pool.putconn(conn)
            logger.debug("Connection returned to pool")
        elif conn:
            # Connection is bad but wasn't closed yet
            try:
                conn.close()
                logger.debug("Bad connection closed in finally block")
            except Exception as final_close_exc:
                logger.error("Failed to close bad connection in finally block", extra={"error": str(final_close_exc)})


def close_pool() -> None:
    """
    Close all connections in the pool. Should be called at shutdown.
    """
    global _global_pool
    if _global_pool:
        logger.info("Closing all connections in the pool")
        _global_pool.closeall()
        _global_pool = None
        logger.info("Connection pool closed")

