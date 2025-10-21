"""
Script to populate Supabase with mock player data remotely.

This script:
1. Loads mock data from mock_data.json
2. Connects to Supabase using environment variables
3. Inserts players, MMR records, and preferences
4. Handles duplicate entries gracefully
"""

import json
import os
import sys
import io
from datetime import datetime
from dotenv import load_dotenv

# Fix Windows console encoding for Unicode emojis
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment variables from .env file
load_dotenv()

from src.backend.db.connection_pool import get_connection, initialize_pool, close_pool


def load_mock_data():
    """Load mock data from JSON file"""
    mock_data_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'backend', 'db', 'mock_data.json')
    
    with open(mock_data_path, 'r') as f:
        data = json.load(f)
    
    print(f"✅ Loaded mock data: {len(data['players'])} players, {len(data['mmrs'])} MMR records, {len(data['preferences'])} preferences", flush=True)
    return data


def insert_players(cursor, players):
    """Insert player records in batch"""
    print(f"\n🎮 Inserting {len(players)} players...", flush=True)
    
    if not players:
        return 0, 0
    
    # Prepare batch insert
    batch_size = 50
    inserted = 0
    
    for i in range(0, len(players), batch_size):
        batch = players[i:i + batch_size]
        try:
            # Use executemany for faster insertion
            cursor.executemany("""
                INSERT INTO players (
                    discord_uid, discord_username, player_name, battletag,
                    country, region, accepted_tos, completed_setup, activation_code
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (discord_uid) DO NOTHING
            """, [
                (
                    p['discord_uid'],
                    p['discord_username'],
                    p['player_name'],
                    p['battletag'],
                    p['country'],
                    p['region'],
                    p['accepted_tos'],
                    p['completed_setup'],
                    f"MOCK{p['discord_uid']}"
                )
                for p in batch
            ])
            
            inserted += len(batch)
            print(f"  ✅ Batch {i//batch_size + 1}: {len(batch)} players ({inserted}/{len(players)})", flush=True)
            
        except Exception as e:
            print(f"  ⚠️  Batch error (continuing): {e}", flush=True)
    
    print(f"✅ Players: {inserted} inserted/updated", flush=True)
    return inserted, 0


def insert_mmrs(cursor, mmrs):
    """Insert MMR records in batch"""
    print(f"\n📊 Inserting {len(mmrs)} MMR records...", flush=True)
    
    if not mmrs:
        return 0, 0
    
    # Prepare batch insert
    batch_size = 100
    inserted = 0
    
    for i in range(0, len(mmrs), batch_size):
        batch = mmrs[i:i + batch_size]
        try:
            cursor.executemany("""
                INSERT INTO mmrs_1v1 (
                    discord_uid, player_name, race, mmr,
                    games_played, games_won, games_lost, games_drawn
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (discord_uid, race) DO UPDATE SET
                    mmr = EXCLUDED.mmr,
                    games_played = EXCLUDED.games_played,
                    games_won = EXCLUDED.games_won,
                    games_lost = EXCLUDED.games_lost,
                    games_drawn = EXCLUDED.games_drawn
            """, [
                (
                    m['discord_uid'],
                    m['player_name'],
                    m['race'],
                    m['mmr'],
                    m['games_played'],
                    max(0, m['games_won']),
                    max(0, m['games_lost']),
                    m['games_drawn']
                )
                for m in batch
            ])
            
            inserted += len(batch)
            print(f"  ✅ Batch {i//batch_size + 1}: {len(batch)} records ({inserted}/{len(mmrs)})", flush=True)
            
        except Exception as e:
            print(f"  ⚠️  Batch error (continuing): {e}", flush=True)
    
    print(f"✅ MMR records: {inserted} inserted/updated", flush=True)
    return inserted, 0


def insert_preferences(cursor, preferences):
    """Insert preference records in batch"""
    print(f"\n⚙️ Inserting {len(preferences)} preference records...", flush=True)
    
    if not preferences:
        return 0, 0
    
    # Prepare batch insert
    batch_size = 50
    inserted = 0
    
    for i in range(0, len(preferences), batch_size):
        batch = preferences[i:i + batch_size]
        try:
            cursor.executemany("""
                INSERT INTO preferences_1v1 (
                    discord_uid, last_chosen_races, last_chosen_vetoes
                ) VALUES (%s, %s, %s)
                ON CONFLICT (discord_uid) DO UPDATE SET
                    last_chosen_races = EXCLUDED.last_chosen_races,
                    last_chosen_vetoes = EXCLUDED.last_chosen_vetoes
            """, [
                (
                    p['discord_uid'],
                    p['last_chosen_races'],
                    p['last_chosen_vetoes']
                )
                for p in batch
            ])
            
            inserted += len(batch)
            print(f"  ✅ Batch {i//batch_size + 1}: {len(batch)} records ({inserted}/{len(preferences)})", flush=True)
            
        except Exception as e:
            print(f"  ⚠️  Batch error (continuing): {e}", flush=True)
    
    print(f"✅ Preferences: {inserted} inserted/updated", flush=True)
    return inserted, 0


def verify_data(cursor):
    """Verify inserted data"""
    print(f"\n🔍 Verifying data...", flush=True)
    
    # Count players
    cursor.execute("SELECT COUNT(*) FROM players")
    player_count = cursor.fetchone()[0]
    print(f"  Players in database: {player_count}", flush=True)
    
    # Count MMR records
    cursor.execute("SELECT COUNT(*) FROM mmrs_1v1")
    mmr_count = cursor.fetchone()[0]
    print(f"  MMR records in database: {mmr_count}", flush=True)
    
    # Count preferences
    cursor.execute("SELECT COUNT(*) FROM preferences_1v1")
    pref_count = cursor.fetchone()[0]
    print(f"  Preferences in database: {pref_count}", flush=True)
    
    # Sample data - get first player
    cursor.execute("""
        SELECT p.player_name, p.country, COUNT(m.id) as mmr_count
        FROM players p
        LEFT JOIN mmrs_1v1 m ON p.discord_uid = m.discord_uid
        WHERE p.discord_uid = 100000000
        GROUP BY p.player_name, p.country
    """)
    sample = cursor.fetchone()
    if sample:
        print(f"\n📋 Sample player:", flush=True)
        print(f"  Name: {sample[0]}", flush=True)
        print(f"  Country: {sample[1]}", flush=True)
        print(f"  MMR records: {sample[2]}", flush=True)
    
    return player_count, mmr_count, pref_count


def main():
    """Main execution function"""
    print("=" * 60, flush=True)
    print("🚀 Supabase Mock Data Population Script", flush=True)
    print("=" * 60, flush=True)
    
    # Check for required environment variables
    required_vars = ['DATABASE_URL', 'SUPABASE_URL', 'SUPABASE_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"\n❌ Missing required environment variables: {', '.join(missing_vars)}", flush=True)
        print("\nPlease set these in your .env file:", flush=True)
        print("  DATABASE_URL=postgresql://...", flush=True)
        print("  SUPABASE_URL=https://...", flush=True)
        print("  SUPABASE_KEY=...", flush=True)
        return 1
    
    print(f"\n✅ Environment variables configured", flush=True)
    print(f"  SUPABASE_URL: {os.getenv('SUPABASE_URL')}", flush=True)
    
    # Load mock data
    try:
        data = load_mock_data()
    except Exception as e:
        print(f"\n❌ Failed to load mock data: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return 1
    
    # Initialize database connection pool
    print(f"\n🔌 Initializing database connection pool...", flush=True)
    try:
        initialize_pool(dsn=os.getenv('DATABASE_URL'))
        print(f"✅ Database connection pool initialized", flush=True)
        
        # Connect to Supabase
        print(f"\n🔌 Connecting to Supabase...", flush=True)
        with get_connection() as conn:
            with conn.cursor() as cursor:
                print(f"✅ Connected to Supabase", flush=True)
                
                # Insert data
                print(f"\n📊 Starting data insertion...", flush=True)
                player_stats = insert_players(cursor, data['players'])
                mmr_stats = insert_mmrs(cursor, data['mmrs'])
                pref_stats = insert_preferences(cursor, data['preferences'])
                
                # Commit transaction
                conn.commit()
                print(f"\n✅ All changes committed to database", flush=True)
                
                # Verify data
                player_count, mmr_count, pref_count = verify_data(cursor)
                
    except Exception as e:
        print(f"\n❌ Database error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return 1
    
    # Summary
    print("\n" + "=" * 60, flush=True)
    print("📊 POPULATION SUMMARY", flush=True)
    print("=" * 60, flush=True)
    print(f"✅ Players inserted/updated: {player_stats[0]}", flush=True)
    print(f"✅ MMR records inserted/updated: {mmr_stats[0]}", flush=True)
    print(f"✅ Preferences inserted/updated: {pref_stats[0]}", flush=True)
    print(f"\n📈 Total records in database:", flush=True)
    print(f"  Players: {player_count}", flush=True)
    print(f"  MMR records: {mmr_count}", flush=True)
    print(f"  Preferences: {pref_count}", flush=True)
    print("=" * 60, flush=True)
    print("🎉 Population complete!", flush=True)
    print("=" * 60, flush=True)
    
    # Clean up connection pool
    try:
        close_pool()
        print(f"\n🧹 Database connection pool closed", flush=True)
    except:
        pass
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

