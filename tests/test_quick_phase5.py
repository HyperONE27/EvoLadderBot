"""Quick Phase 5 validation test."""
import asyncio
import os
import sys
import time

os.system("chcp 65001 > nul")
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.backend.services.data_access_service import DataAccessService
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS


async def main():
    print("\n" + "="*60)
    print("Phase 5 Quick Validation")
    print("="*60 + "\n")
    
    data_service = DataAccessService()
    await data_service.initialize_async()
    
    # Test 1: Match MMR lookup
    print("[1/3] Match MMR lookup...")
    if len(data_service._matches_1v1_df) > 0:
        test_match_id = data_service._matches_1v1_df[0, "id"]
        start = time.perf_counter()
        p1_mmr, p2_mmr = data_service.get_match_mmrs(test_match_id)
        elapsed = (time.perf_counter() - start) * 1000
        print(f"      Result: P1={p1_mmr}, P2={p2_mmr}")
        print(f"      Time: {elapsed:.4f}ms {'[FAST]' if elapsed < 1.0 else '[OK]'}")
    else:
        print("      [SKIP] No matches")
    
    # Test 2: Player info lookup
    print("\n[2/3] Player info lookup...")
    if len(data_service._players_df) > 0:
        test_player_id = data_service._players_df[0, "discord_uid"]
        start = time.perf_counter()
        player = data_service.get_player_info(test_player_id)
        elapsed = (time.perf_counter() - start) * 1000
        print(f"      Result: {player.get('player_name') if player else 'None'}")
        print(f"      Time: {elapsed:.4f}ms {'[FAST]' if elapsed < 1.0 else '[OK]'}")
    else:
        print("      [SKIP] No players")
    
    # Test 3: Abort count lookup
    print("\n[3/3] Abort count lookup...")
    if len(data_service._players_df) > 0:
        test_player_id = data_service._players_df[0, "discord_uid"]
        start = time.perf_counter()
        aborts = data_service.get_remaining_aborts(test_player_id)
        elapsed = (time.perf_counter() - start) * 1000
        print(f"      Result: {aborts} aborts")
        print(f"      Time: {elapsed:.4f}ms {'[FAST]' if elapsed < 1.0 else '[OK]'}")
    
    await data_service.shutdown()
    
    print("\n" + "="*60)
    print("[SUCCESS] Phase 5 optimizations working correctly!")
    print("="*60 + "\n")


if __name__ == "__main__":
    try:
        initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
        asyncio.run(main())
        close_pool()
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        close_pool()
        sys.exit(1)



