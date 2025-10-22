#!/usr/bin/env python3
"""
Test script to verify MMR update flow after match completion.
This tests the complete flow from match completion to MMR updates.
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

async def test_mmr_update_flow():
    """Test the MMR update flow after match completion"""
    print("🧪 Testing MMR Update Flow")
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
        
        # Test 1: Check match 138 data
        print("\n1️⃣ Testing Match 138 Data")
        match_138 = data_service.get_match(138)
        if match_138:
            print(f"✅ Match 138 found:")
            print(f"  Player 1: {match_138.get('player_1_discord_uid')}")
            print(f"  Player 2: {match_138.get('player_2_discord_uid')}")
            print(f"  Player 1 Report: {match_138.get('player_1_report')}")
            print(f"  Player 2 Report: {match_138.get('player_2_report')}")
            print(f"  Match Result: {match_138.get('match_result')}")
            print(f"  Player 1 Race: {match_138.get('player_1_race')}")
            print(f"  Player 2 Race: {match_138.get('player_2_race')}")
        else:
            print("❌ Match 138 not found!")
            return False
        
        # Test 2: Check current MMR values
        print("\n2️⃣ Testing Current MMR Values")
        p1_uid = match_138.get('player_1_discord_uid')
        p2_uid = match_138.get('player_2_discord_uid')
        p1_race = match_138.get('player_1_race')
        p2_race = match_138.get('player_2_race')
        
        if p1_uid and p2_uid and p1_race and p2_race:
            p1_mmr = data_service.get_player_mmr(p1_uid, p1_race)
            p2_mmr = data_service.get_player_mmr(p2_uid, p2_race)
            print(f"  Player 1 MMR ({p1_uid}/{p1_race}): {p1_mmr}")
            print(f"  Player 2 MMR ({p2_uid}/{p2_race}): {p2_mmr}")
        else:
            print("❌ Missing player or race data!")
            return False
        
        # Test 3: Check if match completion should be triggered
        print("\n3️⃣ Testing Match Completion Detection")
        p1_report = match_138.get('player_1_report')
        p2_report = match_138.get('player_2_report')
        match_result = match_138.get('match_result')
        
        print(f"  Player 1 Report: {p1_report}")
        print(f"  Player 2 Report: {p2_report}")
        print(f"  Match Result: {match_result}")
        
        # Check if both players have reported
        if p1_report is not None and p2_report is not None:
            print("✅ Both players have reported")
            
            # Check if match is complete
            if match_result is not None and match_result != -1:
                print(f"✅ Match is complete with result: {match_result}")
                
                # Test 4: Manually trigger match completion
                print("\n4️⃣ Testing Manual Match Completion")
                try:
                    await completion_service.check_match_completion(138)
                    print("✅ Match completion check completed")
                    
                    # Check MMR values after completion
                    print("\n5️⃣ Testing MMR Values After Completion")
                    p1_mmr_after = data_service.get_player_mmr(p1_uid, p1_race)
                    p2_mmr_after = data_service.get_player_mmr(p2_uid, p2_race)
                    print(f"  Player 1 MMR after: {p1_mmr_after}")
                    print(f"  Player 2 MMR after: {p2_mmr_after}")
                    
                    if p1_mmr_after != p1_mmr or p2_mmr_after != p2_mmr:
                        print("✅ MMR values were updated!")
                    else:
                        print("❌ MMR values were NOT updated!")
                        return False
                        
                except Exception as e:
                    print(f"❌ Error during match completion: {e}")
                    import traceback
                    traceback.print_exc()
                    return False
            else:
                print("❌ Match is not complete or was aborted")
                return False
        else:
            print("❌ Not both players have reported")
            return False
        
        print("\n✅ All MMR update flow tests passed!")
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
    success = asyncio.run(test_mmr_update_flow())
    if success:
        print("\n🎉 All tests passed!")
    else:
        print("\n💥 Some tests failed!")
        sys.exit(1)