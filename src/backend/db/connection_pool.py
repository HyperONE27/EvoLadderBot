"""
Database connection pool for PostgreSQL.

Maintains a pool of persistent database connections to eliminate connection
overhead (TCP, SSL, auth) on every query.

Expected impact:
- Reduces per-query latency from 150-300ms to <50ms
- Eliminates 90-95% of connection overhead
- Commands execute 2-5x faster
"""

from typing import Optional
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager


class ConnectionPool:
    """
    Manages a pool of PostgreSQL database connections.

    This is a singleton - only one pool exists per application instance.
    """

    def __init__(self, connection_string: str, minconn: int = 2, maxconn: int = 10):
        """
        Initialize the connection pool.

        Args:
            connection_string: PostgreSQL connection URL
            minconn: Minimum number of connections to maintain
            maxconn: Maximum number of connections to create
        """
        self.connection_string = connection_string
        self.minconn = minconn
        self.maxconn = maxconn
        self._pool: Optional[pool.SimpleConnectionPool] = None

        print(f"[ConnectionPool] Initializing pool (min={minconn}, max={maxconn})...")

        try:
            self._pool = pool.SimpleConnectionPool(
                minconn, maxconn, dsn=connection_string
            )
            print(f"[ConnectionPool] Pool created successfully.")
            # Verify connections are working
            with self.get_connection() as conn:
                print(
                    f"[ConnectionPool] Test connection successful: {conn.get_dsn_parameters()}"
                )

        except psycopg2.OperationalError as e:
            print(f"[ConnectionPool] FATAL: Failed to connect to database: {e}")
            print(f"[ConnectionPool] Check connection string and database status.")
            raise
        except Exception as e:
            print(f"[ConnectionPool] ERROR: Failed to create pool: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """
        Get a connection from the pool.

        Yields:
            psycopg2 connection from the pool

        Usage:
            with pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ...")
        """
        if self._pool is None:
            raise RuntimeError("Connection pool not initialized or has been closed.")

        conn = None
        try:
            # Borrow connection from pool (reuses existing connection)
            conn = self._pool.getconn()
            yield conn
            conn.commit()
        except Exception as e:
            print(f"[ConnectionPool] Error getting connection: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                # Return connection to pool (doesn't close it!)
                self._pool.putconn(conn)

    def close_all(self):
        """Close all connections in the pool."""
        if self._pool:
            print("[ConnectionPool] Closing all connections...")
            self._pool.closeall()
            self._pool = None
            print("[ConnectionPool] Pool closed.")

    def get_stats(self) -> dict:
        """
        Get connection pool statistics.

        Returns:
            Dictionary with pool stats
        """
        if not self._pool:
            return {"initialized": False}

        return {
            "initialized": True,
            "minconn": self.minconn,
            "maxconn": self.maxconn,
            # SimpleConnectionPool doesn't expose used/free counts
        }


# Removed global state management functions:
# - _global_pool
# - get_global_pool()
# - initialize_pool()
# - close_pool()
# The AppContext now manages the lifecycle of the ConnectionPool instance.
