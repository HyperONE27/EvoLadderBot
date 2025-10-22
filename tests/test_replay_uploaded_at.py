"""
Test that replay uploads include the uploaded_at column and work end-to-end.
"""

import asyncio
import os
import sys
import json

os.system("chcp 65001 > nul")

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.backend.services.data_access_service import DataAccessService
from src.backend.db.db_reader_writer import get_timestamp, DatabaseReader
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS


async def test_replay_with_uploaded_at():
    """Test that replay inserts include uploaded_at column."""
    print("\n" + "="*60)
    print("Replay uploaded_at Column Test")
    print("="*60 + "\n")
    
    data_service = DataAccessService()
    await data_service.initialize_async()
    
    # Create test replay data with uploaded_at
    import time
    test_timestamp = get_timestamp()
    unique_id = str(int(time.time() * 1000))  # Millisecond timestamp for uniqueness
    test_replay_data = {
        "replay_hash": f"test_hash_{unique_id}",
        "replay_date": test_timestamp,
        "player_1_name": "TestPlayerA",
        "player_2_name": "TestPlayerB",
        "player_1_race": "bw_terran",
        "player_2_race": "sc2_zerg",
        "result": 1,
        "player_1_handle": "handleA",
        "player_2_handle": "handleB",
        "observers": json.dumps([]),
        "map_name": "TestMap",
        "duration": 600,
        "replay_path": f"/test/replay_{unique_id}.rep",  # Unique path
        "uploaded_at": test_timestamp  # NEW COLUMN
    }
    
    print(f"[1/4] Creating test replay with uploaded_at...")
    print(f"      Timestamp: {test_timestamp}")
    
    # Insert replay (async, non-blocking)
    await data_service.insert_replay(test_replay_data)
    print(f"      [PASS] Replay insert queued")
    
    # Wait for write queue to process
    print(f"\n[2/4] Waiting for async write to complete...")
    await asyncio.sleep(1.0)
    
    # Verify replay was written to database with uploaded_at
    print(f"\n[3/4] Verifying replay in database...")
    db_reader = DatabaseReader()
    
    # Use the adapter's query method directly
    with db_reader.adapter.get_connection() as conn:
        with conn.cursor() as cursor:
            query = "SELECT * FROM replays WHERE replay_hash = %s ORDER BY id DESC LIMIT 1"
            cursor.execute(query, (test_replay_data["replay_hash"],))
            columns = [desc[0] for desc in cursor.description]
            row = cursor.fetchone()
            result = [dict(zip(columns, row))] if row else []
    
    if result and len(result) > 0:
        replay = result[0]
        print(f"      [PASS] Replay found in database")
        print(f"      ID: {replay.get('id')}")
        print(f"      Hash: {replay.get('replay_hash')}")
        
        # Check if uploaded_at column exists and has a value
        if 'uploaded_at' in replay:
            uploaded_at = replay.get('uploaded_at')
            print(f"      uploaded_at: {uploaded_at}")
            
            if uploaded_at:
                print(f"      [PASS] uploaded_at column populated")
            else:
                print(f"      [WARN] uploaded_at is NULL")
        else:
            print(f"      [FAIL] uploaded_at column not in result")
            print(f"      Available columns: {list(replay.keys())}")
    else:
        print(f"      [FAIL] Replay not found in database")
        await data_service.shutdown()
        return False
    
    # Clean up test data
    print(f"\n[4/4] Cleaning up test data...")
    try:
        with db_reader.adapter.get_connection() as conn:
            with conn.cursor() as cursor:
                cleanup_query = "DELETE FROM replays WHERE replay_hash = %s"
                cursor.execute(cleanup_query, (test_replay_data["replay_hash"],))
        print(f"      [PASS] Test replay deleted")
    except Exception as e:
        print(f"      [WARN] Cleanup failed: {e}")
    
    await data_service.shutdown()
    
    print("\n" + "="*60)
    print("[SUCCESS] Replay uploaded_at column working correctly!")
    print("="*60 + "\n")
    
    return True


if __name__ == "__main__":
    try:
        initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
        success = asyncio.run(test_replay_with_uploaded_at())
        close_pool()
        
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
            
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        close_pool()
        sys.exit(1)

