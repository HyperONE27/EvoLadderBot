"""
Test player operations in DataAccessService.
"""

import asyncio
import os
import sys

os.system("chcp 65001 > nul")

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.backend.db.db_reader_writer import DatabaseWriter
from src.backend.services.data_access_service import DataAccessService
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS

TEST_UID = 999888777


def cleanup():
    """Clean up test data."""
    try:
        writer = DatabaseWriter()
        conn = writer.adapter.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM players WHERE discord_uid = %s', (TEST_UID,))
        conn.commit()
        cursor.close()
        writer.adapter.return_connection(conn)
    except:
        pass


async def test_player_ops():
    """Test player operations."""
    print("\n=== Player Operations Test ===\n")
    
    try:
        data_service = DataAccessService()
        await data_service.initialize_async()
        
        # Test 1: Create player
        print("[1/5] Creating test player...")
        success = await data_service.create_player(
            discord_uid=TEST_UID,
            discord_username="TestUser",
            player_name="TestPlayer",
            country="US"
        )
        if success:
            print("      [PASS] Player created")
        else:
            print("      [FAIL] Failed to create")
            return False
        
        # Test 2: Get player info
        print("[2/5] Getting player info...")
        player = data_service.get_player_info(TEST_UID)
        if player and player.get('player_name') == 'TestPlayer':
            print(f"      [PASS] Found: {player.get('player_name')}")
        else:
            print("      [FAIL] Not found")
            return False
        
        # Test 3: Update player
        print("[3/5] Updating player...")
        success = await data_service.update_player_info(
            discord_uid=TEST_UID,
            player_name="UpdatedPlayer"
        )
        if success:
            player = data_service.get_player_info(TEST_UID)
            if player.get('player_name') == 'UpdatedPlayer':
                print("      [PASS] Update successful")
            else:
                print("      [FAIL] Update not reflected")
                return False
        
        # Test 4: Abort count
        print("[4/5] Testing abort count...")
        aborts = data_service.get_remaining_aborts(TEST_UID)
        await data_service.update_remaining_aborts(TEST_UID, 2)
        new_aborts = data_service.get_remaining_aborts(TEST_UID)
        if new_aborts == 2:
            print(f"      [PASS] Abort count: {aborts} -> {new_aborts}")
        else:
            print("      [FAIL] Abort count failed")
            return False
        
        # Test 5: Player exists
        print("[5/5] Testing player_exists...")
        if data_service.player_exists(TEST_UID):
            print("      [PASS] player_exists working")
        else:
            print("      [FAIL] player_exists failed")
            return False
        
        await asyncio.sleep(0.5)
        await data_service.shutdown()
        print(f"\n[SUCCESS] All player operations passed! ({data_service._total_writes_queued} writes queued) [PASS]\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
        cleanup()
        success = asyncio.run(test_player_ops())
        cleanup()
        close_pool()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[FATAL] {e}")
        close_pool()
        sys.exit(1)

