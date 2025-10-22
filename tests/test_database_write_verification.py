#!/usr/bin/env python3
"""
Test script to verify database write operations are working correctly.
"""

import sys
import os
import asyncio
import time

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS
from src.backend.db.db_reader_writer import DatabaseReader, DatabaseWriter

async def test_database_write_verification():
    """Test that database writes are working correctly"""
    print("🧪 Testing Database Write Verification")
    print("=" * 50)
    
    # Initialize database pool
    print("📊 Initializing database pool...")
    initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
    
    try:
        db_reader = DatabaseReader()
        db_writer = DatabaseWriter()
        
        # Test 1: Check current MMR change for match 138
        print("\n1️⃣ Testing Current MMR Change for Match 138")
        current_mmr_change = db_reader.get_match_mmr_change(138)
        print(f"  Current MMR change: {current_mmr_change}")
        
        # Test 2: Update MMR change to a different value
        print("\n2️⃣ Testing MMR Change Update")
        new_mmr_change = 999  # Use a distinctive value
        result = db_writer.update_match_mmr_change(138, new_mmr_change)
        print(f"  Update result: {result}")
        
        # Test 3: Verify the update
        print("\n3️⃣ Testing MMR Change Verification")
        updated_mmr_change = db_reader.get_match_mmr_change(138)
        print(f"  Updated MMR change: {updated_mmr_change}")
        
        if updated_mmr_change == new_mmr_change:
            print("✅ Database write verification successful!")
            return True
        else:
            print(f"❌ Database write verification failed! Expected {new_mmr_change}, got {updated_mmr_change}")
            return False
            
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
    success = asyncio.run(test_database_write_verification())
    if success:
        print("\n🎉 Database write verification passed!")
    else:
        print("\n💥 Database write verification failed!")
        sys.exit(1)
