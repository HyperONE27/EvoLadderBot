"""
Comprehensive test for replay upload flow using DataAccessService.

This test verifies that:
1. Replays can be parsed correctly
2. Replay data is stored in memory
3. Match records are updated with replay paths
4. Async upload flow works correctly
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.backend.services.data_access_service import DataAccessService
from src.backend.services.replay_service import ReplayService, parse_replay_data_blocking
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS


async def test_replay_upload_flow():
    """Test the complete replay upload flow."""
    print("\n[TEST] Starting replay upload flow test")
    
    # Initialize DataAccessService
    data_service = DataAccessService()
    await data_service.initialize_async()
    
    # Create test players
    test_player_1_uid = 444444444444444444
    test_player_2_uid = 555555555555555555
    
    await data_service.create_player(
        discord_uid=test_player_1_uid,
        discord_username="ReplayTestPlayer1",
        player_name="ReplayPlayer1"
    )
    
    await data_service.create_player(
        discord_uid=test_player_2_uid,
        discord_username="ReplayTestPlayer2",
        player_name="ReplayPlayer2"
    )
    
    # Wait for writes
    await asyncio.sleep(0.5)
    
    # Create MMR records
    await data_service.create_or_update_mmr(
        discord_uid=test_player_1_uid,
        player_name="ReplayPlayer1",
        race="sc2_terran",
        mmr=1500
    )
    
    await data_service.create_or_update_mmr(
        discord_uid=test_player_2_uid,
        player_name="ReplayPlayer2",
        race="sc2_zerg",
        mmr=1500
    )
    
    # Wait for writes
    await asyncio.sleep(0.5)
    
    # Create a test match
    match_data = {
        'player_1_discord_uid': test_player_1_uid,
        'player_2_discord_uid': test_player_2_uid,
        'player_1_race': 'sc2_terran',
        'player_2_race': 'sc2_zerg',
        'map_played': 'Test Map',
        'server_choice': 'US-West',
        'player_1_mmr': 1500,
        'player_2_mmr': 1500,
        'mmr_change': 0
    }
    
    print("[TEST] Creating match...")
    match_id = await data_service.create_match(match_data)
    assert match_id is not None, "Match ID should not be None"
    print(f"[TEST] Match created with ID: {match_id}")
    
    # Wait for match to be loaded into memory
    await asyncio.sleep(0.5)
    
    # Load a test replay file
    test_replay_path = project_root / "tests" / "test_data" / "test_replay_files" / "DarkReBellionIsles.SC2Replay"
    
    if not test_replay_path.exists():
        print(f"[TEST] WARNING: Test replay file not found at {test_replay_path}")
        print("[TEST] Skipping replay upload test")
        await data_service.shutdown()
        return True
    
    print(f"[TEST] Loading test replay from {test_replay_path}")
    with open(test_replay_path, 'rb') as f:
        replay_bytes = f.read()
    
    # Initialize replay service
    replay_service = ReplayService()
    
    # Parse replay in blocking mode (for testing)
    print("[TEST] Parsing replay...")
    parsed_dict = parse_replay_data_blocking(replay_bytes)
    
    if parsed_dict.get("error"):
        print(f"[TEST] Replay parsing failed: {parsed_dict['error']}")
        await data_service.shutdown()
        return False
    
    print(f"[TEST] Replay parsed successfully:")
    print(f"   Player 1: {parsed_dict.get('player_1_name')} ({parsed_dict.get('player_1_race')})")
    print(f"   Player 2: {parsed_dict.get('player_2_name')} ({parsed_dict.get('player_2_race')})")
    print(f"   Map: {parsed_dict.get('map_name')}")
    print(f"   Duration: {parsed_dict.get('duration')}")
    
    # Store replay using async method
    print("[TEST] Storing replay...")
    result = await replay_service.store_upload_from_parsed_dict_async(
        match_id,
        test_player_1_uid,
        replay_bytes,
        parsed_dict
    )
    
    assert result["success"], f"Replay upload should succeed, got: {result}"
    print("[TEST] Replay stored successfully")
    
    # Wait for writes to complete
    await asyncio.sleep(1.0)
    
    # Verify match was updated with replay path
    print("[TEST] Verifying match replay path...")
    match = data_service.get_match(match_id)
    
    assert match is not None, "Match should still exist in memory"
    
    # Check if either player's replay path was updated
    p1_replay = match.get('player_1_replay_path')
    p2_replay = match.get('player_2_replay_path')
    
    print(f"[TEST] Match replay paths:")
    print(f"   Player 1: {p1_replay}")
    print(f"   Player 2: {p2_replay}")
    
    # At least one should be set
    assert p1_replay is not None or p2_replay is not None, "At least one replay path should be set"
    
    print("[TEST] Match replay path verified")
    
    # Shutdown
    await data_service.shutdown()
    
    print("[TEST] Replay upload flow test completed successfully")
    return True


if __name__ == "__main__":
    try:
        initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
        success = asyncio.run(test_replay_upload_flow())
        close_pool()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[FATAL] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        close_pool()
        sys.exit(1)

