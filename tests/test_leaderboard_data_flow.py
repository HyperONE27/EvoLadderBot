#!/usr/bin/env python3
"""
Test script to debug leaderboard data flow.
"""

import sys
import os
import asyncio

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS
from src.backend.services.leaderboard_service import LeaderboardService
from src.backend.services.data_access_service import DataAccessService

async def test_leaderboard_data_flow():
    """Test leaderboard data flow from DataAccessService to LeaderboardService"""
    print("🧪 Testing Leaderboard Data Flow")
    print("=" * 50)
    
    # Initialize database pool
    print("📊 Initializing database pool...")
    initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
    
    try:
        # Initialize services
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        leaderboard_service = LeaderboardService(data_service=data_service)
        
        # Test leaderboard data
        print("\n🔍 Testing leaderboard data...")
        leaderboard_data = await leaderboard_service.get_leaderboard_data(
            current_page=1,
            page_size=10,
            country_filter=None,
            race_filter=None,
            best_race_only=False,
            rank_filter=None
        )
        
        print(f"✅ Leaderboard data retrieved: {len(leaderboard_data['players'])} players")
        
        # Check first few players
        print("\n📋 Sample leaderboard players:")
        for i, player in enumerate(leaderboard_data['players'][:5]):
            print(f"Player {i+1}:")
            print(f"  discord_uid: {player.get('discord_uid')}")
            print(f"  player_name: {player.get('player_name')}")
            print(f"  race: {player.get('race')}")
            print(f"  mmr: {player.get('mmr')}")
            print(f"  country: {player.get('country')}")
            print()
            
        # Check if player_name is None
        null_names = [p for p in leaderboard_data['players'] if p.get('player_name') is None]
        print(f"📊 Players with null names: {len(null_names)}")
        
        if len(null_names) > 0:
            print("❌ Found players with null names!")
            for player in null_names[:3]:
                print(f"  discord_uid: {player.get('discord_uid')}, player_name: {player.get('player_name')}")
        else:
            print("✅ All players have non-null names!")
            
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Clean up
        print("\n🧹 Cleaning up...")
        close_pool()
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_leaderboard_data_flow())
    if success:
        print("\n🎉 Leaderboard data flow test completed!")
    else:
        print("\n💥 Leaderboard data flow test failed!")
        sys.exit(1)
