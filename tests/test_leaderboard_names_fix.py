#!/usr/bin/env python3
"""
Test script to verify leaderboard names fix.
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

async def test_leaderboard_names_fix():
    """Test that leaderboard names are now working correctly"""
    print("🧪 Testing Leaderboard Names Fix")
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
            page_size=5,
            country_filter=None,
            race_filter=None,
            best_race_only=False,
            rank_filter=None
        )
        
        print(f"✅ Leaderboard data retrieved: {len(leaderboard_data['players'])} players")
        
        # Test formatted data
        print("\n🔍 Testing formatted leaderboard data...")
        formatted_players = leaderboard_service.get_leaderboard_data_formatted(
            leaderboard_data['players'],
            current_page=1,
            page_size=5
        )
        
        print(f"✅ Formatted data: {len(formatted_players)} players")
        
        # Check player names
        print("\n📋 Sample formatted players:")
        for i, player in enumerate(formatted_players):
            print(f"Player {i+1}:")
            print(f"  rank: {player.get('rank')}")
            print(f"  player_name: {player.get('player_name')}")
            print(f"  mmr: {player.get('mmr')}")
            print(f"  race: {player.get('race')}")
            print(f"  country: {player.get('country')}")
            print()
            
        # Check for "Unknown" names
        unknown_names = [p for p in formatted_players if p.get('player_name') == 'Unknown']
        print(f"📊 Players with 'Unknown' names: {len(unknown_names)}")
        
        if len(unknown_names) > 0:
            print("❌ Found players with 'Unknown' names!")
            for player in unknown_names:
                print(f"  rank: {player.get('rank')}, player_name: {player.get('player_name')}")
        else:
            print("✅ All players have proper names!")
            
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
    success = asyncio.run(test_leaderboard_names_fix())
    if success:
        print("\n🎉 Leaderboard names fix test completed!")
    else:
        print("\n💥 Leaderboard names fix test failed!")
        sys.exit(1)
