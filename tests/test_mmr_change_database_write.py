#!/usr/bin/env python3
"""
Test script to verify MMR change is properly written to the database.
This tests the complete flow from match completion to database write.
"""

import sys
import os
import asyncio
import time

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS
from src.backend.services.data_access_service import DataAccessService
from src.backend.services.match_completion_service import MatchCompletionService
from src.backend.services.matchmaking_service import Matchmaker
from src.backend.db.db_reader_writer import DatabaseReader

async def test_mmr_change_database_write():
    """Test that MMR change is properly written to the database"""
    print("🧪 Testing MMR Change Database Write")
    print("=" * 50)
    
    # Initialize database pool
    print("📊 Initializing database pool...")
    initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
    
    try:
        # Initialize DataAccessService
        print("🔄 Initializing DataAccessService...")
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        # Initialize services
        print("🔄 Initializing services...")
        matchmaker = Matchmaker()
        completion_service = MatchCompletionService()
        db_reader = DatabaseReader()
        
        # Test 1: Check match 138 data before
        print("\n1️⃣ Testing Match 138 Data Before")
        match_138 = data_service.get_match(138)
        if match_138:
            print(f"✅ Match 138 found:")
            print(f"  Match ID: {match_138.get('id')}")
            print(f"  Player 1: {match_138.get('player_1_discord_uid')}")
            print(f"  Player 2: {match_138.get('player_2_discord_uid')}")
            print(f"  Player 1 Report: {match_138.get('player_1_report')}")
            print(f"  Player 2 Report: {match_138.get('player_2_report')}")
            print(f"  Match Result: {match_138.get('match_result')}")
        else:
            print("❌ Match 138 not found!")
            return False
        
        # Test 2: Check current MMR values from database
        print("\n2️⃣ Testing Current MMR Values from Database")
        p1_uid = match_138.get('player_1_discord_uid')
        p2_uid = match_138.get('player_2_discord_uid')
        p1_race = match_138.get('player_1_race')
        p2_race = match_138.get('player_2_race')
        
        if p1_uid and p2_uid and p1_race and p2_race:
            # Get MMR from database directly
            p1_mmr_db = db_reader.get_player_mmr_1v1(p1_uid, p1_race)
            p2_mmr_db = db_reader.get_player_mmr_1v1(p2_uid, p2_race)
            print(f"  Player 1 MMR from DB ({p1_uid}/{p1_race}): {p1_mmr_db}")
            print(f"  Player 2 MMR from DB ({p2_uid}/{p2_race}): {p2_mmr_db}")
        else:
            print("❌ Missing player or race data!")
            return False
        
        # Test 3: Check match MMR change in database before
        print("\n3️⃣ Testing Match MMR Change in Database Before")
        match_mmr_change_before = db_reader.get_match_mmr_change(138)
        print(f"  Match 138 MMR change in DB: {match_mmr_change_before}")
        
        # Test 4: Manually trigger match completion
        print("\n4️⃣ Testing Manual Match Completion")
        try:
            await completion_service.check_match_completion(138)
            print("✅ Match completion check completed")
            
            # Wait for database writes to complete
            print("⏳ Waiting for database writes to complete...")
            await asyncio.sleep(2.0)
            
            # Test 5: Check MMR values in database after
            print("\n5️⃣ Testing MMR Values in Database After")
            p1_mmr_db_after = db_reader.get_player_mmr_1v1(p1_uid, p1_race)
            p2_mmr_db_after = db_reader.get_player_mmr_1v1(p2_uid, p2_race)
            print(f"  Player 1 MMR from DB after: {p1_mmr_db_after}")
            print(f"  Player 2 MMR from DB after: {p2_mmr_db_after}")
            
            if p1_mmr_db_after != p1_mmr_db or p2_mmr_db_after != p2_mmr_db:
                print("✅ MMR values were updated in database!")
            else:
                print("❌ MMR values were NOT updated in database!")
                return False
            
            # Test 6: Check match MMR change in database after
            print("\n6️⃣ Testing Match MMR Change in Database After")
            match_mmr_change_after = db_reader.get_match_mmr_change(138)
            print(f"  Match 138 MMR change in DB after: {match_mmr_change_after}")
            
            if match_mmr_change_after != match_mmr_change_before and match_mmr_change_after != 0:
                print("✅ Match MMR change was updated in database!")
            else:
                print("❌ Match MMR change was NOT updated in database!")
                return False
                
        except Exception as e:
            print(f"❌ Error during match completion: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        print("\n✅ All MMR change database write tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Clean up
        print("\n🧹 Cleaning up...")
        close_pool()

if __name__ == "__main__":
    success = asyncio.run(test_mmr_change_database_write())
    if success:
        print("\n🎉 All tests passed!")
    else:
        print("\n💥 Some tests failed!")
        sys.exit(1)
