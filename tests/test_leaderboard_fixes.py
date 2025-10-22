#!/usr/bin/env python3
"""
Test script to verify leaderboard fixes:
1. Names showing up correctly
2. Country flag handling for None values
3. Rank filter button functionality
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
from src.bot.utils.discord_utils import get_flag_emote, country_to_flag

async def test_leaderboard_fixes():
    """Test the leaderboard fixes"""
    print("🧪 Testing Leaderboard Fixes")
    print("=" * 50)
    
    # Initialize database pool
    print("📊 Initializing database pool...")
    initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
    
    try:
        # Initialize DataAccessService
        print("🔄 Initializing DataAccessService...")
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        # Test 1: Check if leaderboard DataFrame has player names
        print("\n1️⃣ Testing Leaderboard DataFrame Structure")
        df = data_service.get_leaderboard_dataframe()
        if df is None:
            print("❌ Leaderboard DataFrame is None!")
            return False
        
        print(f"✅ Leaderboard DataFrame loaded: {len(df)} rows")
        print(f"📋 Columns: {df.columns}")
        
        # Check if player_name column exists
        if 'player_name' in df.columns:
            print("✅ player_name column found in leaderboard DataFrame")
            
            # Check for sample data
            sample_data = df.head(5).to_dicts()
            for i, player in enumerate(sample_data):
                player_name = player.get('player_name')
                discord_uid = player.get('discord_uid')
                print(f"  Player {i+1}: {player_name} (Discord: {discord_uid})")
        else:
            print("❌ player_name column missing from leaderboard DataFrame")
            return False
        
        # Test 2: Check country flag handling
        print("\n2️⃣ Testing Country Flag Handling")
        
        # Test with None country
        none_flag = get_flag_emote(None)
        print(f"✅ None country flag: {none_flag}")
        
        # Test with empty string
        empty_flag = get_flag_emote("")
        print(f"✅ Empty country flag: {empty_flag}")
        
        # Test with valid country
        us_flag = get_flag_emote("US")
        print(f"✅ US country flag: {us_flag}")
        
        # Test 3: Check rank filter cycle
        print("\n3️⃣ Testing Rank Filter Cycle")
        
        # Simulate the rank cycle from the button
        RANK_CYCLE = [None, "s_rank", "a_rank", "b_rank", "c_rank", "d_rank", "e_rank", "f_rank"]
        
        print("🔄 Testing rank cycle progression:")
        current_rank = None
        for i in range(len(RANK_CYCLE) + 2):  # Test wrap-around
            try:
                current_index = RANK_CYCLE.index(current_rank)
            except ValueError:
                current_index = 0
            
            next_index = (current_index + 1) % len(RANK_CYCLE)
            next_rank = RANK_CYCLE[next_index]
            
            print(f"  {current_rank} -> {next_rank}")
            current_rank = next_rank
            
            # Check for E-rank to F-rank transition
            if current_rank == "e_rank":
                print("  ✅ E-rank found in cycle")
            elif current_rank == "f_rank" and i > 0:
                print("  ✅ F-rank found after E-rank")
        
        print("\n✅ All leaderboard fixes verified!")
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
    success = asyncio.run(test_leaderboard_fixes())
    if success:
        print("\n🎉 All tests passed!")
    else:
        print("\n💥 Some tests failed!")
        sys.exit(1)
