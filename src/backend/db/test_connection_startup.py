"""
Test database connection at startup.

This module verifies the database connection is working and tables exist.
"""

import sqlite3
from typing import List, Tuple
from src.backend.db.db_connection import (
    get_database_type,
    get_database_connection_string,
    is_postgresql
)
from src.backend.db.adapters import get_adapter
from src.bot.config import DATABASE_TYPE


def test_database_connection() -> tuple[bool, str]:
    """
    Tests the database connection and checks for essential tables.
    For PostgreSQL, this will test getting a connection from the pool.
    """
    if not DATABASE_TYPE:
        return False, "DATABASE_TYPE environment variable is not set."

    try:
        adapter = get_adapter(DATABASE_TYPE)
        
        print(f"[DB Test] Testing connection to {DATABASE_TYPE.capitalize()} database...")
        with adapter.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check for players table as a basic schema validation
            if DATABASE_TYPE.lower() == "postgresql":
                cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'players');")
            else: # SQLite
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='players';")
            
            table_exists = cursor.fetchone()[0]

            if not table_exists:
                return False, "Connection successful, but 'players' table not found. Schema may not be initialized."
        
        print("[DB Test] Database connection and schema check successful.")
        return True, "Connection successful."

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Connection failed: {e}"


if __name__ == "__main__":
    success, message = test_database_connection()
    exit(0 if success else 1)

