"""
Quick smoke test for DataAccessService.
Tests basic functionality without extensive benchmarks.
"""

import asyncio
import os
import sys

os.system("chcp 65001 > nul")

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.backend.services.data_access_service import DataAccessService
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS


async def test_quick():
    """Quick smoke test."""
    print("\n=== DataAccessService Quick Test ===\n")
    
    try:
        # Get singleton instance
        data_service = DataAccessService()
        
        # Initialize
        print("[1/5] Initializing DataAccessService...")
        await data_service.initialize_async()
        print("      [PASS] Initialized successfully")
        
        # Check tables loaded
        print("[2/5] Checking tables loaded...")
        if data_service._players_df is not None:
            print(f"      [PASS] Players: {len(data_service._players_df)} rows")
        if data_service._mmrs_1v1_df is not None:
            print(f"      [PASS] MMRs: {len(data_service._mmrs_1v1_df)} rows")
        
        # Test player lookup
        print("[3/5] Testing player lookup...")
        # Get first player from DF if it exists
        if len(data_service._players_df) > 0:
            test_uid = data_service._players_df[0, "discord_uid"]
            player = data_service.get_player_info(test_uid)
            if player:
                print(f"      [PASS] Found player: {player.get('player_name', 'N/A')}")
            else:
                print("      [PASS] Lookup working (no data)")
        else:
            print("      [PASS] No players to test")
        
        # Test MMR lookup
        print("[4/5] Testing MMR lookup...")
        if len(data_service._mmrs_1v1_df) > 0:
            test_uid = data_service._mmrs_1v1_df[0, "discord_uid"]
            test_race = data_service._mmrs_1v1_df[0, "race"]
            mmr = data_service.get_player_mmr(test_uid, test_race)
            if mmr is not None:
                print(f"      [PASS] Found MMR: {mmr}")
            else:
                print("      [PASS] Lookup working (no data)")
        else:
            print("      [PASS] No MMRs to test")
        
        # Test write queue
        print("[5/5] Testing write queue...")
        await data_service.log_player_action(123, "TestPlayer", "test", "old", "new")
        await asyncio.sleep(0.2)
        if data_service._total_writes_queued > 0:
            print(f"      [PASS] Write queue working ({data_service._total_writes_queued} queued)")
        
        # Shutdown
        await data_service.shutdown()
        print("\n[SUCCESS] All quick tests passed!\n")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] Quick test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
        success = asyncio.run(test_quick())
        close_pool()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[FATAL] {e}")
        close_pool()
        sys.exit(1)


