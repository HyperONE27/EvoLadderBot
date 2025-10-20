"""
Abstract base class for database adapters.

Defines the interface that all database adapters must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager


class DatabaseAdapter(ABC):
    """
    Abstract base class for database adapters.

    Provides a unified interface for database operations across
    different database backends (SQLite, PostgreSQL, etc.).
    """

    @abstractmethod
    def get_connection_string(self) -> str:
        """
        Get the connection string for this database.

        Returns:
            Connection string (for logging/debugging)
        """
        pass

    @abstractmethod
    @contextmanager
    def get_connection(self):
        """
        Get a database connection as a context manager.

        Yields:
            Database connection object

        Example:
            with adapter.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM players")
        """
        pass

    @abstractmethod
    def execute_query(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query and return results as list of dicts.

        Args:
            query: SQL query with :named placeholders
            params: Dictionary of parameter values

        Returns:
            List of dictionaries (one per row)

        Example:
            results = adapter.execute_query(
                "SELECT * FROM players WHERE discord_uid = :uid",
                {"uid": 12345}
            )
        """
        pass

    @abstractmethod
    def execute_write(self, query: str, params: Optional[Dict[str, Any]] = None) -> int:
        """
        Execute an INSERT/UPDATE/DELETE query.

        Args:
            query: SQL query with :named placeholders
            params: Dictionary of parameter values

        Returns:
            Number of rows affected

        Example:
            rows = adapter.execute_write(
                "UPDATE players SET player_name = :name WHERE discord_uid = :uid",
                {"name": "NewName", "uid": 12345}
            )
        """
        pass

    @abstractmethod
    def execute_insert(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Execute an INSERT query and return the new row's ID.

        Args:
            query: SQL INSERT query with :named placeholders
            params: Dictionary of parameter values

        Returns:
            ID of the newly inserted row

        Example:
            new_id = adapter.execute_insert(
                "INSERT INTO players (discord_uid, discord_username) "
                "VALUES (:uid, :username)",
                {"uid": 12345, "username": "Player1"}
            )
        """
        pass

    @abstractmethod
    def convert_query(self, query: str) -> str:
        """
        Convert query with :named placeholders to database-specific format.

        Args:
            query: SQL query with :named placeholders

        Returns:
            Query with database-specific placeholders

        Example:
            SQLite: "WHERE id = :id" → "WHERE id = :id" (no change)
            PostgreSQL: "WHERE id = :id" → "WHERE id = %(id)s"
        """
        pass

    @abstractmethod
    def dict_from_row(self, row: Any) -> Dict[str, Any]:
        """
        Convert a database row to a dictionary.

        Args:
            row: Database row object (varies by backend)

        Returns:
            Dictionary with column names as keys
        """
        pass

    def execute_many(self, query: str, params_list: List[Dict[str, Any]]) -> int:
        """
        Execute a query multiple times with different parameters.

        Args:
            query: SQL query with :named placeholders
            params_list: List of parameter dictionaries

        Returns:
            Total number of rows affected

        Example:
            adapter.execute_many(
                "INSERT INTO players (discord_uid, discord_username) "
                "VALUES (:uid, :username)",
                [
                    {"uid": 1, "username": "Player1"},
                    {"uid": 2, "username": "Player2"},
                ]
            )
        """
        total_affected = 0
        for params in params_list:
            total_affected += self.execute_write(query, params)
        return total_affected
