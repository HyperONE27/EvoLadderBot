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

# Fix Windows console encoding for Unicode emojis
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.backend.db.connection_pool import get_connection


def load_mock_data():
    """Load mock data from JSON file"""
    mock_data_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'backend', 'db', 'mock_data.json')
    
    with open(mock_data_path, 'r') as f:
        data = json.load(f)
    
    print(f"✅ Loaded mock data: {len(data['players'])} players, {len(data['mmrs'])} MMR records, {len(data['preferences'])} preferences")
    return data


def insert_players(cursor, players):
    """Insert player records"""
    print(f"\n🎮 Inserting {len(players)} players...")
    
    inserted = 0
    skipped = 0
    
    for player in players:
        try:
            cursor.execute("""
                INSERT INTO players (
                    discord_uid, discord_username, player_name, battletag,
                    country, region, accepted_tos, completed_setup, activation_code
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (discord_uid) DO NOTHING
                RETURNING id
            """, (
                player['discord_uid'],
                player['discord_username'],
                player['player_name'],
                player['battletag'],
                player['country'],
                player['region'],
                player['accepted_tos'],
                player['completed_setup'],
                f"MOCK{player['discord_uid']}"  # Generate activation codes
            ))
            
            result = cursor.fetchone()
            if result:
                inserted += 1
                if inserted % 10 == 0:
                    print(f"  Inserted {inserted}/{len(players)} players...")
            else:
                skipped += 1
                
        except Exception as e:
            print(f"  ❌ Error inserting player {player['discord_uid']}: {e}")
            skipped += 1
    
    print(f"✅ Players: {inserted} inserted, {skipped} skipped (already exist)")
    return inserted, skipped


def insert_mmrs(cursor, mmrs):
    """Insert MMR records"""
    print(f"\n📊 Inserting {len(mmrs)} MMR records...")
    
    inserted = 0
    skipped = 0
    
    for mmr in mmrs:
        try:
            cursor.execute("""
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
                RETURNING id
            """, (
                mmr['discord_uid'],
                mmr['player_name'],
                mmr['race'],
                mmr['mmr'],
                mmr['games_played'],
                max(0, mmr['games_won']),  # Ensure non-negative
                max(0, mmr['games_lost']),  # Ensure non-negative
                mmr['games_drawn']
            ))
            
            result = cursor.fetchone()
            if result:
                inserted += 1
                if inserted % 50 == 0:
                    print(f"  Inserted {inserted}/{len(mmrs)} MMR records...")
            else:
                skipped += 1
                
        except Exception as e:
            print(f"  ❌ Error inserting MMR for {mmr['discord_uid']}/{mmr['race']}: {e}")
            skipped += 1
    
    print(f"✅ MMR records: {inserted} inserted/updated, {skipped} skipped")
    return inserted, skipped


def insert_preferences(cursor, preferences):
    """Insert preference records"""
    print(f"\n⚙️ Inserting {len(preferences)} preference records...")
    
    inserted = 0
    skipped = 0
    
    for pref in preferences:
        try:
            cursor.execute("""
                INSERT INTO preferences_1v1 (
                    discord_uid, last_chosen_races, last_chosen_vetoes
                ) VALUES (%s, %s, %s)
                ON CONFLICT (discord_uid) DO UPDATE SET
                    last_chosen_races = EXCLUDED.last_chosen_races,
                    last_chosen_vetoes = EXCLUDED.last_chosen_vetoes
                RETURNING id
            """, (
                pref['discord_uid'],
                pref['last_chosen_races'],
                pref['last_chosen_vetoes']
            ))
            
            result = cursor.fetchone()
            if result:
                inserted += 1
            else:
                skipped += 1
                
        except Exception as e:
            print(f"  ❌ Error inserting preference for {pref['discord_uid']}: {e}")
            skipped += 1
    
    print(f"✅ Preferences: {inserted} inserted/updated, {skipped} skipped")
    return inserted, skipped


def verify_data(cursor):
    """Verify inserted data"""
    print(f"\n🔍 Verifying data...")
    
    # Count players
    cursor.execute("SELECT COUNT(*) FROM players")
    player_count = cursor.fetchone()[0]
    print(f"  Players in database: {player_count}")
    
    # Count MMR records
    cursor.execute("SELECT COUNT(*) FROM mmrs_1v1")
    mmr_count = cursor.fetchone()[0]
    print(f"  MMR records in database: {mmr_count}")
    
    # Count preferences
    cursor.execute("SELECT COUNT(*) FROM preferences_1v1")
    pref_count = cursor.fetchone()[0]
    print(f"  Preferences in database: {pref_count}")
    
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
        print(f"\n📋 Sample player:")
        print(f"  Name: {sample[0]}")
        print(f"  Country: {sample[1]}")
        print(f"  MMR records: {sample[2]}")
    
    return player_count, mmr_count, pref_count


def main():
    """Main execution function"""
    print("=" * 60)
    print("🚀 Supabase Mock Data Population Script")
    print("=" * 60)
    
    # Check for required environment variables
    required_vars = ['DATABASE_URL', 'SUPABASE_URL', 'SUPABASE_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"\n❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("\nPlease set these in your .env file:")
        print("  DATABASE_URL=postgresql://...")
        print("  SUPABASE_URL=https://...")
        print("  SUPABASE_KEY=...")
        return 1
    
    print(f"\n✅ Environment variables configured")
    print(f"  SUPABASE_URL: {os.getenv('SUPABASE_URL')}")
    
    # Load mock data
    try:
        data = load_mock_data()
    except Exception as e:
        print(f"\n❌ Failed to load mock data: {e}")
        return 1
    
    # Connect to Supabase
    print(f"\n🔌 Connecting to Supabase...")
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                print(f"✅ Connected to Supabase")
                
                # Insert data
                player_stats = insert_players(cursor, data['players'])
                mmr_stats = insert_mmrs(cursor, data['mmrs'])
                pref_stats = insert_preferences(cursor, data['preferences'])
                
                # Commit transaction
                conn.commit()
                print(f"\n✅ All changes committed to database")
                
                # Verify data
                player_count, mmr_count, pref_count = verify_data(cursor)
                
    except Exception as e:
        print(f"\n❌ Database error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 POPULATION SUMMARY")
    print("=" * 60)
    print(f"✅ Players inserted/updated: {player_stats[0]}")
    print(f"✅ MMR records inserted/updated: {mmr_stats[0]}")
    print(f"✅ Preferences inserted/updated: {pref_stats[0]}")
    print(f"\n📈 Total records in database:")
    print(f"  Players: {player_count}")
    print(f"  MMR records: {mmr_count}")
    print(f"  Preferences: {pref_count}")
    print("=" * 60)
    print("🎉 Population complete!")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

