"""
Database adapters for SQLite and PostgreSQL.

This module provides a unified interface for database operations,
allowing transparent switching between SQLite and PostgreSQL.
"""

from src.backend.db.adapters.base_adapter import DatabaseAdapter
from src.backend.db.adapters.sqlite_adapter import SQLiteAdapter
from src.backend.db.adapters.postgresql_adapter import PostgreSQLAdapter
from src.backend.db.connection_pool import ConnectionPool
from typing import Optional


def get_adapter(db_type: str, pool: Optional[ConnectionPool] = None) -> DatabaseAdapter:
    """
    Factory function to get the appropriate database adapter.
    """
    if db_type.lower() == "sqlite":
        return SQLiteAdapter()
    elif db_type.lower() == "postgresql":
        if not pool:
            raise ValueError("ConnectionPool is required for PostgreSQLAdapter")
        return PostgreSQLAdapter(pool=pool)
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


__all__ = [
    "DatabaseAdapter",
    "SQLiteAdapter",
    "PostgreSQLAdapter",
    "get_adapter",
]
