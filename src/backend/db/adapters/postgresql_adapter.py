"""
PostgreSQL database adapter implementation with connection pooling.
"""

import re
from typing import Any, Dict, List, Optional
from contextlib import contextmanager
import psycopg2
import psycopg2.extras

from src.backend.db.adapters.base_adapter import DatabaseAdapter
from src.backend.db.connection_pool import ConnectionPool


class PostgreSQLAdapter(DatabaseAdapter):
    """
    Database adapter for PostgreSQL with connection pooling.

    Uses a connection pool to eliminate connection overhead.
    Handles PostgreSQL-specific query formatting and result conversion.
    """

    def __init__(self, pool: ConnectionPool):
        """
        Initialize PostgreSQL adapter.

        Args:
            pool: An initialized ConnectionPool instance.
        """
        self.pool = pool

    def get_connection_string(self) -> str:
        """Get connection string for logging (with masked password)."""
        return self._mask_password(self.pool.connection_string)

    @contextmanager
    def get_connection(self):
        """
        Get a PostgreSQL database connection from the pool.

        Yields:
            psycopg2 connection with RealDictCursor
        """
        conn = None
        try:
            # self.pool is the ConnectionPool instance from AppContext
            with self.pool.get_connection() as conn:
                # Set cursor factory for this transaction
                conn.cursor_factory = psycopg2.extras.RealDictCursor
                yield conn
                conn.commit()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            # The pool's context manager handles returning the connection
            pass

    def execute_query(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results as list of dicts."""
        if params is None:
            params = {}

        # Convert :named to %(named)s placeholders
        converted_query = self.convert_query(query)

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(converted_query, params)
                rows = cursor.fetchall()
                # RealDictCursor returns RealDictRow objects, convert to plain dicts
                return [dict(row) for row in rows]

    def execute_write(self, query: str, params: Optional[Dict[str, Any]] = None) -> int:
        """Execute an INSERT/UPDATE/DELETE query."""
        if params is None:
            params = {}

        converted_query = self.convert_query(query)

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(converted_query, params)
                return cursor.rowcount

    def execute_insert(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> int:
        """Execute an INSERT query and return the new row's ID."""
        if params is None:
            params = {}

        converted_query = self.convert_query(query)

        # Add RETURNING id clause if not present
        if "RETURNING" not in converted_query.upper():
            converted_query = converted_query.rstrip(";") + " RETURNING id"

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(converted_query, params)
                result = cursor.fetchone()

                if result and "id" in result:
                    return result["id"]

                # Fallback if no id is returned
                return 0

    def convert_query(self, query: str) -> str:
        """
        Convert query with :named placeholders to PostgreSQL format.

        Converts :name to %(name)s for psycopg2 compatibility.

        Args:
            query: SQL query with :named placeholders

        Returns:
            Query with %(named)s placeholders

        Example:
            Input:  "SELECT * FROM players WHERE discord_uid = :uid"
            Output: "SELECT * FROM players WHERE discord_uid = %(uid)s"
        """
        # Convert :name to %(name)s
        # Use regex to match :word_boundary
        converted = re.sub(r":(\w+)", r"%(\1)s", query)
        return converted

    def execute_many(self, query: str, params_list: List[Dict[str, Any]]) -> int:
        """
        Execute a query multiple times with different parameters.

        Optimized for PostgreSQL using execute_batch.
        """
        if not params_list:
            return 0

        converted_query = self.convert_query(query)

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Use execute_batch for better performance
                psycopg2.extras.execute_batch(cursor, converted_query, params_list)
                return cursor.rowcount

    def _mask_password(self, connection_string: str) -> str:
        """
        Mask the password in a connection string for safe logging.

        Args:
            connection_string: Database connection string

        Returns:
            Connection string with password masked
        """
        if not connection_string:
            return connection_string

        # Pattern: postgresql://user:password@host:port/db
        # Replace everything between : and @ with ***
        pattern = r"://([^:]+):([^@]+)@"
        masked = re.sub(pattern, r"://\1:***@", connection_string)
        return masked
