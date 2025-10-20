"""
Database adapters for SQLite and PostgreSQL.

This module provides a unified interface for database operations,
allowing transparent switching between SQLite and PostgreSQL.
"""

from typing import Optional
from src.backend.db.adapters.base_adapter import DatabaseAdapter
from src.backend.db.adapters.sqlite_adapter import SQLiteAdapter
from src.backend.db.adapters.postgresql_adapter import PostgreSQLAdapter


def get_adapter(db_type: str) -> DatabaseAdapter:
    """
    Get the appropriate database adapter based on database type.
    
    Args:
        db_type: Either "sqlite" or "postgresql"
        
    Returns:
        DatabaseAdapter instance for the specified database type
        
    Raises:
        ValueError: If db_type is not recognized
    """
    db_type = db_type.lower()
    
    if db_type == "sqlite":
        return SQLiteAdapter()
    elif db_type == "postgresql":
        return PostgreSQLAdapter()
    else:
        raise ValueError(
            f"Unknown database type: '{db_type}'. "
            f"Must be 'sqlite' or 'postgresql'."
        )


__all__ = [
    "DatabaseAdapter",
    "SQLiteAdapter",
    "PostgreSQLAdapter",
    "get_adapter",
]

