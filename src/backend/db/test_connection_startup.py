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
import sys


def test_database_connection(db_type: str, db_url: str, sqlite_path: str):
    print("\n" + "="*70)
    print("DATABASE CONNECTION TEST")
    print("="*70)

    print(f"Database Type: {db_type}")

    if db_type == "postgresql":
        ok, msg = _test_postgresql_connection(db_url)
    elif db_type == "sqlite":
        ok, msg = _test_sqlite_connection(sqlite_path)
    else:
        ok, msg = False, "Invalid DATABASE_TYPE"

    if not ok:
        print(f"\n[FATAL] Database connection test failed: {msg}")
        sys.exit(1)
    else:
        print(f"\n[INFO] Database connection test passed: {msg}")

    print(f"{'='*70}\n")


def print_check(name: str, ok: bool, msg: str):
    status = "OK" if ok else "FAIL"
    print(f"- {name}: [{status}] {msg}")


def _test_postgresql_connection(db_url: str):
    print("Testing PostgreSQL connection...")
    conn = None
    try:
        import psycopg2
        
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # Test connection
        cur.execute("SELECT version();")
        version = cur.fetchone()
        msg = f"OK, Connected to PostgreSQL"
        ok = True
        print(f"  - Connection: {msg}")
        print_check("PostgreSQL Connection", ok, msg)
        
    except ImportError:
        msg = "X psycopg2 not installed"
        ok = False
        print(f"  - Connection: {msg}")
        print_check("PostgreSQL Connection", ok, msg)
    except Exception as e:
        msg = f"X Connection failed: {str(e)}"
        ok = False
        print(f"  - Connection: {msg}")
        print_check("PostgreSQL Connection", ok, msg)

    if not ok:
        return False, msg

    # Check for tables
    ok, msg = _check_tables(conn, ["players", "matches_1v1", "preferences_1v1"])
    print(f"  - Table check: {msg}")
    print_check("Table Check", ok, msg)

    return ok, msg


def _test_sqlite_connection(db_path: str):
    print("Testing SQLite connection...")
    conn = None
    try:
        # Extract path from sqlite:///path
        db_path = db_path.replace("sqlite:///", "")
        
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Check for tables
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' 
            AND name IN ('players', 'mmrs_1v1', 'matches_1v1', 'preferences_1v1')
            ORDER BY name;
        """)
        tables = [row[0] for row in cur.fetchall()]
        
        expected_tables = ['matches_1v1', 'mmrs_1v1', 'players', 'preferences_1v1']
        
        if not tables:
            msg = "X No tables found! Run create_table.py first."
            ok = False
        else:
            missing_tables = [t for t in expected_tables if t not in tables]
            if missing_tables:
                msg = f"X Missing tables: {', '.join(missing_tables)}"
                ok = False
            else:
                msg = "OK, All required tables exist"
                ok = True
        
    except Exception as e:
        msg = f"X Connection failed: {str(e)}"
        ok = False
        print(f"  - Connection: {msg}")
        print_check("SQLite3 Connection", ok, msg)

    if not ok:
        return False, msg

    # Check for tables
    ok, msg = _check_tables(conn, ["players", "matches", "player_preferences"])
    print(f"  - Table check: {msg}")
    print_check("Table Check", ok, msg)
    
    return ok, msg


def _check_tables(conn, required_tables):
    msg = ""
    ok = True
    try:
        cur = conn.cursor()
        # Get list of tables
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        tables = {row[0] for row in cur.fetchall()}
        cur.close()

        required_tables = set(required_tables)
        if required_tables.issubset(tables):
            msg = "OK, All required tables exist"
        else:
            missing_tables = required_tables - tables
            if not tables:
                msg = "X No tables found! Run schema SQL in Supabase SQL Editor."
                ok = False
            else:
                msg = f"X Missing tables: {', '.join(missing_tables)}"
                ok = False
        
    except Exception as e:
        msg = f"Error checking tables: {e}"
        ok = False

    return ok, msg


if __name__ == "__main__":
    db_type = get_database_type()
    db_url = get_database_connection_string()
    sqlite_path = db_url.replace("sqlite:///", "") if db_type == "sqlite" else ""

    test_database_connection(db_type, db_url, sqlite_path)

