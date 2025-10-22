#!/usr/bin/env python3
"""
Test script to debug player names in leaderboard.
"""

import sys
import os
import asyncio
import polars as pl

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS
from src.backend.services.data_access_service import DataAccessService

async def test_player_names():
    """Test player names in DataAccessService"""
    print("🧪 Testing Player Names in DataAccessService")
    print("=" * 50)
    
    # Initialize database pool
    print("📊 Initializing database pool...")
    initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
    
    try:
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        # Check what's in the players DataFrame
        if data_service._players_df is not None:
            print(f"\n✅ Players DataFrame loaded: {len(data_service._players_df)} rows")
            print(f"Columns: {data_service._players_df.columns}")
            
            # Check if player_name column exists and has data
            if 'player_name' in data_service._players_df.columns:
                non_null_names = data_service._players_df.filter(pl.col('player_name').is_not_null())
                print(f"\n📊 Players with non-null names: {len(non_null_names)}")
                
                if len(non_null_names) > 0:
                    print("\n📋 Sample player names:")
                    sample = non_null_names.select(['discord_uid', 'player_name']).head(10)
                    print(sample)
                else:
                    print("\n❌ No players with non-null names found!")
                    
                # Check for null names
                null_names = data_service._players_df.filter(pl.col('player_name').is_null())
                print(f"\n📊 Players with null names: {len(null_names)}")
                
                if len(null_names) > 0:
                    print("\n📋 Sample null name players:")
                    sample_null = null_names.select(['discord_uid', 'player_name']).head(5)
                    print(sample_null)
            else:
                print("\n❌ player_name column not found!")
        else:
            print("\n❌ Players DataFrame is None!")
            
        # Test leaderboard DataFrame
        print("\n🔍 Testing leaderboard DataFrame...")
        leaderboard_df = data_service.get_leaderboard_dataframe()
        
        if leaderboard_df is not None:
            print(f"✅ Leaderboard DataFrame: {len(leaderboard_df)} rows")
            print(f"Columns: {leaderboard_df.columns}")
            
            if 'player_name' in leaderboard_df.columns:
                non_null_leaderboard_names = leaderboard_df.filter(pl.col('player_name').is_not_null())
                print(f"📊 Leaderboard entries with non-null names: {len(non_null_leaderboard_names)}")
                
                if len(non_null_leaderboard_names) > 0:
                    print("\n📋 Sample leaderboard names:")
                    sample_leaderboard = non_null_leaderboard_names.select(['discord_uid', 'player_name', 'mmr']).head(10)
                    print(sample_leaderboard)
                else:
                    print("\n❌ No leaderboard entries with non-null names!")
            else:
                print("\n❌ player_name column not found in leaderboard!")
        else:
            print("\n❌ Leaderboard DataFrame is None!")
            
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
    success = asyncio.run(test_player_names())
    if success:
        print("\n🎉 Player names test completed!")
    else:
        print("\n💥 Player names test failed!")
        sys.exit(1)
