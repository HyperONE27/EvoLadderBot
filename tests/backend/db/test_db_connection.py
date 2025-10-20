"""
Test script for database connection configuration.

This script tests your database connection setup for both SQLite and PostgreSQL.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.backend.db.db_connection import (
    get_database_connection_string,
    get_database_type,
    get_database_config,
    is_postgresql,
    is_sqlite
)


def test_connection():
    """Test the database connection."""
    print("\n" + "="*70)
    print("DATABASE CONNECTION TEST")
    print("="*70 + "\n")
    
    # Show configuration
    print("[Configuration]")
    config = get_database_config()
    for key, value in config.items():
        print(f"   {key}: {value}")
    
    print(f"\n[Connection String]")
    print(f"   {get_database_connection_string()}")
    
    print(f"\n[Database Type]")
    print(f"   Type: {get_database_type()}")
    print(f"   Is PostgreSQL: {is_postgresql()}")
    print(f"   Is SQLite: {is_sqlite()}")
    
    # Try to connect
    db_type = get_database_type()
    
    if db_type == "sqlite":
        print("\n[Testing SQLite connection...]")
        try:
            import sqlite3
            db_path = os.getenv("SQLITE_DB_PATH", "evoladder.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()[0]
            conn.close()
            print(f"   [OK] SQLite connection successful!")
            print(f"   Version: {version}")
        except Exception as e:
            print(f"   [ERROR] SQLite connection failed: {e}")
    
    elif db_type == "postgresql":
        print("\n[Testing PostgreSQL connection...]")
        try:
            import psycopg2
            
            # Get connection parameters
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                # Production mode - use DATABASE_URL
                # psycopg2 doesn't accept postgres:// scheme, only postgresql://
                if database_url.startswith("postgres://"):
                    database_url = database_url.replace("postgres://", "postgresql://", 1)
                conn = psycopg2.connect(database_url)
            else:
                # Local mode - use individual parameters
                conn = psycopg2.connect(
                    host=os.getenv("POSTGRES_HOST", "localhost"),
                    port=os.getenv("POSTGRES_PORT", "5432"),
                    database=os.getenv("POSTGRES_DB", "evoladder"),
                    user=os.getenv("POSTGRES_USER", "evoladder_user"),
                    password=os.getenv("POSTGRES_PASSWORD", "")
                )
            
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            print(f"   [OK] PostgreSQL connection successful!")
            print(f"   Version: {version.split(',')[0]}")  # First part only
            
        except ImportError:
            print(f"   [ERROR] psycopg2 not installed. Install with: pip install psycopg2-binary")
        except Exception as e:
            print(f"   [ERROR] PostgreSQL connection failed: {e}")
            print("\n   [Troubleshooting]")
            print("      1. Is PostgreSQL running?")
            print("      2. Are your credentials correct in .env?")
            print("      3. Does the database exist?")
            print("      4. Check firewall/port settings")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    test_connection()

