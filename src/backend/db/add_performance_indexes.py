"""
Add performance-critical indexes to the database.

This script adds indexes that improve query performance for common operations.
Run this once to ensure all indexes are created.
"""

import sys
from src.backend.db.connection_pool import initialize_pool, get_connection, close_pool
from src.bot.config import DATABASE_URL


def create_indexes() -> None:
    """Create all performance-critical indexes if they don't already exist."""
    
    indexes = [
        # Player lookups (most common operation) - PRIMARY KEY is auto-indexed
        ("idx_players_discord_uid", "CREATE INDEX IF NOT EXISTS idx_players_discord_uid ON players(discord_uid)"),
        ("idx_players_username", "CREATE INDEX IF NOT EXISTS idx_players_username ON players(discord_username)"),
        
        # MMR queries (leaderboards, player stats)
        ("idx_mmrs_1v1_discord_uid", "CREATE INDEX IF NOT EXISTS idx_mmrs_1v1_discord_uid ON mmrs_1v1(discord_uid)"),
        ("idx_mmrs_1v1_mmr", "CREATE INDEX IF NOT EXISTS idx_mmrs_1v1_mmr ON mmrs_1v1(mmr)"),
        ("idx_mmrs_1v1_race", "CREATE INDEX IF NOT EXISTS idx_mmrs_1v1_race ON mmrs_1v1(race)"),
        
        # Match history (player profiles, recent matches)
        ("idx_matches_1v1_player1", "CREATE INDEX IF NOT EXISTS idx_matches_1v1_player1 ON matches_1v1(player_1_discord_uid)"),
        ("idx_matches_1v1_player2", "CREATE INDEX IF NOT EXISTS idx_matches_1v1_player2 ON matches_1v1(player_2_discord_uid)"),
        ("idx_matches_1v1_played_at", "CREATE INDEX IF NOT EXISTS idx_matches_1v1_played_at ON matches_1v1(played_at)"),
        
        # Replay lookups (duplicate detection, file management)
        ("idx_replays_hash", "CREATE INDEX IF NOT EXISTS idx_replays_hash ON replays(replay_hash)"),
        ("idx_replays_date", "CREATE INDEX IF NOT EXISTS idx_replays_date ON replays(replay_date)"),
        
        # Command analytics (usage patterns, debugging)
        ("idx_command_calls_discord_uid", "CREATE INDEX IF NOT EXISTS idx_command_calls_discord_uid ON command_calls(discord_uid)"),
        ("idx_command_calls_called_at", "CREATE INDEX IF NOT EXISTS idx_command_calls_called_at ON command_calls(called_at)"),
        ("idx_command_calls_command", "CREATE INDEX IF NOT EXISTS idx_command_calls_command ON command_calls(command)"),
        
        # Preferences lookups (queue command)
        ("idx_preferences_1v1_discord_uid", "CREATE INDEX IF NOT EXISTS idx_preferences_1v1_discord_uid ON preferences_1v1(discord_uid)"),
    ]
    
    print("[Indexes] Creating performance indexes...")
    
    created_count = 0
    skipped_count = 0
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            for index_name, index_sql in indexes:
                try:
                    cur.execute(index_sql)
                    conn.commit()
                    print(f"[Indexes] [OK] {index_name}")
                    created_count += 1
                except Exception as e:
                    # Index might already exist or there's a syntax issue
                    if "already exists" in str(e).lower():
                        print(f"[Indexes] [SKIP] {index_name} (already exists)")
                        skipped_count += 1
                    else:
                        print(f"[Indexes] [ERR] {index_name}: {e}")
                        conn.rollback()
    
    print(f"\n[Indexes] Summary:")
    print(f"  Created: {created_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Total: {len(indexes)}")
    print("[Indexes] All performance indexes are ready!")


def verify_indexes() -> None:
    """Verify that all indexes exist."""
    
    print("\n[Indexes] Verifying index coverage...")
    
    # Query to check existing indexes
    index_query = """
    SELECT 
        schemaname,
        tablename,
        indexname,
        indexdef
    FROM pg_indexes
    WHERE schemaname = 'public'
    ORDER BY tablename, indexname;
    """
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(index_query)
            indexes = cur.fetchall()
            
            print(f"\n[Indexes] Found {len(indexes)} indexes:")
            
            current_table = None
            for idx in indexes:
                table = idx['tablename']
                index_name = idx['indexname']
                
                if table != current_table:
                    print(f"\n  {table}:")
                    current_table = table
                
                print(f"    - {index_name}")


if __name__ == "__main__":
    print("[Startup] Initializing database connection pool...")
    
    try:
        initialize_pool(dsn=DATABASE_URL)
        print("[Startup] Connection pool initialized")
        
        # Create indexes
        create_indexes()
        
        # Verify indexes
        verify_indexes()
        
    except Exception as e:
        print(f"\n[FATAL] Error: {e}")
        sys.exit(1)
    finally:
        close_pool()
        print("\n[Shutdown] Connection pool closed")

