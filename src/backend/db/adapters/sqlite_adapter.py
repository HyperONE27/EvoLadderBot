"""
SQLite database adapter implementation.
"""

import sqlite3
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from src.backend.db.adapters.base_adapter import DatabaseAdapter
from src.bot.config import SQLITE_DB_PATH


class SQLiteAdapter(DatabaseAdapter):
    """
    Database adapter for SQLite.

    Handles SQLite-specific connection management, query formatting,
    and result conversion.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SQLite adapter.

        Args:
            db_path: Path to SQLite database file (defaults to config value)
        """
        self.db_path = db_path or SQLITE_DB_PATH

    def get_connection_string(self) -> str:
        """Get connection string for logging."""
        return f"sqlite:///{self.db_path}"

    @contextmanager
    def get_connection(self):
        """
        Get a SQLite database connection.

        Yields:
            sqlite3.Connection with Row factory enabled
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Enable Write-Ahead Logging for better concurrency
        conn.execute("PRAGMA journal_mode=WAL;")

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute_query(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results as list of dicts."""
        if params is None:
            params = {}

        # SQLite uses :named placeholders natively, no conversion needed
        converted_query = self.convert_query(query)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(converted_query, params)
            rows = cursor.fetchall()

            # Convert Row objects to dicts
            return [self.dict_from_row(row) for row in rows]

    def execute_write(self, query: str, params: Optional[Dict[str, Any]] = None) -> int:
        """Execute an INSERT/UPDATE/DELETE query."""
        if params is None:
            params = {}

        converted_query = self.convert_query(query)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(converted_query, params)
            return cursor.rowcount

    def execute_insert(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> int:
        """Execute an INSERT query and return the new row's ID."""
        if params is None:
            params = {}

        converted_query = self.convert_query(query)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(converted_query, params)

            # SQLite uses lastrowid to get the inserted ID
            return cursor.lastrowid

    def convert_query(self, query: str) -> str:
        """
        Convert query placeholders to SQLite format.

        SQLite uses :named placeholders natively, so no conversion needed.
        """
        return query

    def dict_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        """
        Convert a SQLite Row to a dictionary.

        Args:
            row: sqlite3.Row object

        Returns:
            Dictionary with column names as keys
        """
        return dict(row)

    def execute_many(self, query: str, params_list: List[Dict[str, Any]]) -> int:
        """
        Execute a query multiple times with different parameters.

        Optimized for SQLite using executemany.
        """
        if not params_list:
            return 0

        converted_query = self.convert_query(query)

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # SQLite's executemany expects a list of tuples/dicts
            cursor.executemany(converted_query, params_list)

            return cursor.rowcount
