"""
Test database connection at startup.

This module verifies the database connection is working and tables exist.
"""

import sqlite3
from typing import List, Tuple
from src.backend.db.db_connection import (
    get_database_type,
    get_database_connection_string,
    is_postgresql,
)


def test_database_connection() -> Tuple[bool, str]:
    """
    Test database connection and verify tables exist.

    Returns:
        Tuple of (success: bool, message: str)
    """
    db_type = get_database_type()
    conn_str = get_database_connection_string()

    print(f"\n{'='*70}")
    print(f"DATABASE CONNECTION TEST")
    print(f"{'='*70}")
    print(f"Database Type: {db_type}")

    if db_type == "postgresql":
        return _test_postgresql_connection(conn_str)
    else:
        return _test_sqlite_connection(conn_str)


def _test_postgresql_connection(conn_str: str) -> Tuple[bool, str]:
    """Test PostgreSQL connection."""
    try:
        import psycopg2

        print("Testing PostgreSQL connection...")
        conn = psycopg2.connect(conn_str)
        cur = conn.cursor()

        # Test connection
        cur.execute("SELECT version();")
        version = cur.fetchone()
        print(f"✓ Connected to PostgreSQL")
        print(f"  Version: {version[0][:80]}...")

        # Check for tables
        cur.execute(
            """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('players', 'mmrs_1v1', 'matches_1v1', 'preferences_1v1')
            ORDER BY table_name;
        """
        )
        tables = [row[0] for row in cur.fetchall()]

        expected_tables = ["matches_1v1", "mmrs_1v1", "players", "preferences_1v1"]

        if not tables:
            msg = "✗ No tables found! Run schema SQL in Supabase SQL Editor."
            print(f"\n{msg}")
            print(f"  Expected tables: {', '.join(expected_tables)}")
            cur.close()
            conn.close()
            print(f"{'='*70}\n")
            return False, msg

        missing_tables = [t for t in expected_tables if t not in tables]
        if missing_tables:
            msg = f"✗ Missing tables: {', '.join(missing_tables)}"
            print(f"\n{msg}")
            print(f"  Found: {', '.join(tables)}")
            cur.close()
            conn.close()
            print(f"{'='*70}\n")
            return False, msg

        print(f"✓ All required tables exist: {', '.join(tables)}")

        # Test a simple query
        cur.execute("SELECT COUNT(*) FROM players;")
        player_count = cur.fetchone()[0]
        print(f"✓ Database query successful")
        print(f"  Players in database: {player_count}")

        cur.close()
        conn.close()

        print(f"\n✓ PostgreSQL connection test PASSED")
        print(f"{'='*70}\n")
        return True, "PostgreSQL connection successful"

    except ImportError:
        msg = "✗ psycopg2 not installed"
        print(f"\n{msg}")
        print(f"{'='*70}\n")
        return False, msg
    except Exception as e:
        msg = f"✗ Connection failed: {str(e)}"
        print(f"\n{msg}")
        print(f"{'='*70}\n")
        return False, msg


def _test_sqlite_connection(conn_str: str) -> Tuple[bool, str]:
    """Test SQLite connection."""
    try:
        # Extract path from sqlite:///path
        db_path = conn_str.replace("sqlite:///", "")

        print(f"Testing SQLite connection...")
        print(f"  Path: {db_path}")

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Check for tables
        cur.execute(
            """
            SELECT name FROM sqlite_master 
            WHERE type='table' 
            AND name IN ('players', 'mmrs_1v1', 'matches_1v1', 'preferences_1v1')
            ORDER BY name;
        """
        )
        tables = [row[0] for row in cur.fetchall()]

        expected_tables = ["matches_1v1", "mmrs_1v1", "players", "preferences_1v1"]

        if not tables:
            msg = "✗ No tables found! Run create_table.py first."
            print(f"\n{msg}")
            cur.close()
            conn.close()
            print(f"{'='*70}\n")
            return False, msg

        missing_tables = [t for t in expected_tables if t not in tables]
        if missing_tables:
            msg = f"✗ Missing tables: {', '.join(missing_tables)}"
            print(f"\n{msg}")
            print(f"  Found: {', '.join(tables)}")
            cur.close()
            conn.close()
            print(f"{'='*70}\n")
            return False, msg

        print(f"✓ All required tables exist: {', '.join(tables)}")

        # Test a simple query
        cur.execute("SELECT COUNT(*) FROM players;")
        player_count = cur.fetchone()[0]
        print(f"✓ Database query successful")
        print(f"  Players in database: {player_count}")

        cur.close()
        conn.close()

        print(f"\n✓ SQLite connection test PASSED")
        print(f"{'='*70}\n")
        return True, "SQLite connection successful"

    except Exception as e:
        msg = f"✗ Connection failed: {str(e)}"
        print(f"\n{msg}")
        print(f"{'='*70}\n")
        return False, msg


if __name__ == "__main__":
    success, message = test_database_connection()
    exit(0 if success else 1)
