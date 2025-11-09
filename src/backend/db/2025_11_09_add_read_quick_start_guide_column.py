"""
Add read_quick_start_guide column to players table.

This migration adds a boolean column to track whether a player has confirmed
they have read the quick start guide. New players must read and confirm before
they can join the matchmaking queue.

Run this once to add the column to both PostgreSQL and SQLite databases.
"""

import sys
from src.backend.db.connection_pool import initialize_pool, get_connection, close_pool
from src.backend.db.db_connection import get_database_type, is_postgresql, is_sqlite
from src.bot.config import DATABASE_URL, SQLITE_DB_PATH


def add_read_quick_start_guide_column() -> None:
    """Add read_quick_start_guide column to players table if it doesn't exist."""
    
    db_type = get_database_type()
    print(f"[Migration] Database type: {db_type}")
    print("[Migration] Adding read_quick_start_guide column to players table...")
    
    if is_postgresql():
        sql = """
        ALTER TABLE players 
        ADD COLUMN IF NOT EXISTS read_quick_start_guide BOOLEAN NOT NULL DEFAULT FALSE;
        """
    elif is_sqlite():
        import sqlite3
        conn = sqlite3.connect(SQLITE_DB_PATH)
        cursor = conn.cursor()
        
        try:
            cursor.execute("PRAGMA table_info(players)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'read_quick_start_guide' in columns:
                print("[Migration] [SKIP] Column 'read_quick_start_guide' already exists")
                conn.close()
                return
            
            sql = """
            ALTER TABLE players 
            ADD COLUMN read_quick_start_guide INTEGER NOT NULL DEFAULT 0;
            """
            cursor.execute(sql)
            conn.commit()
            conn.close()
            print("[Migration] [OK] Column 'read_quick_start_guide' added successfully")
            return
            
        except Exception as e:
            print(f"[Migration] [ERR] Failed to add column: {e}")
            conn.rollback()
            conn.close()
            raise
    else:
        raise ValueError(f"Unsupported database type: {db_type}")
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql)
                conn.commit()
                print("[Migration] [OK] Column 'read_quick_start_guide' added successfully")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print("[Migration] [SKIP] Column 'read_quick_start_guide' already exists")
                else:
                    print(f"[Migration] [ERR] Failed to add column: {e}")
                    conn.rollback()
                    raise


def verify_column() -> None:
    """Verify that the column was added successfully."""
    
    print("\n[Migration] Verifying column addition...")
    
    if is_sqlite():
        import sqlite3
        conn = sqlite3.connect(SQLITE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(players)")
        columns = cursor.fetchall()
        conn.close()
        
        column_names = [col[1] for col in columns]
        if 'read_quick_start_guide' in column_names:
            print("[Migration] [VERIFY OK] Column exists in players table")
        else:
            print("[Migration] [VERIFY FAILED] Column not found in players table")
        return
    
    query = """
    SELECT column_name, data_type, column_default
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'players'
      AND column_name = 'read_quick_start_guide';
    """
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            result = cur.fetchone()
            
            if result:
                print(f"[Migration] [VERIFY OK] Column exists:")
                print(f"  Name: {result['column_name']}")
                print(f"  Type: {result['data_type']}")
                print(f"  Default: {result['column_default']}")
            else:
                print("[Migration] [VERIFY FAILED] Column not found in players table")


if __name__ == "__main__":
    print("[Startup] Initializing database connection...")
    
    try:
        if is_postgresql():
            initialize_pool(dsn=DATABASE_URL)
            print("[Startup] Connection pool initialized")
        
        add_read_quick_start_guide_column()
        verify_column()
        
        print("\n[Migration] Migration completed successfully!")
        
    except Exception as e:
        print(f"\n[FATAL] Error: {e}")
        sys.exit(1)
    finally:
        if is_postgresql():
            close_pool()
            print("\n[Shutdown] Connection pool closed")

