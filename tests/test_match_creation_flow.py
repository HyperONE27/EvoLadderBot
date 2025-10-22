"""
Comprehensive test for match creation flow using DataAccessService.

This test verifies that:
1. Matches can be created successfully
2. Match data is stored in memory correctly
3. Schema alignment works properly
4. Match retrieval works after creation
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.backend.db.connection_pool import initialize_pool, close_pool
from src.backend.services.data_access_service import DataAccessService
from src.bot.config import DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS


async def test_match_creation_flow():
    """Test the complete match creation flow."""
    print("\n[TEST] Starting match creation flow test")
    
    # Initialize DataAccessService
    data_service = DataAccessService()
    await data_service.initialize_async()
    
    # Create test players first
    test_player_1_uid = 111111111111111111
    test_player_2_uid = 222222222222222222
    
    await data_service.create_player(
        discord_uid=test_player_1_uid,
        discord_username="TestPlayer1",
        player_name="Player1"
    )
    
    await data_service.create_player(
        discord_uid=test_player_2_uid,
        discord_username="TestPlayer2",
        player_name="Player2"
    )
    
    # Create MMR records
    await data_service.create_or_update_mmr(
        discord_uid=test_player_1_uid,
        player_name="Player1",
        race="bw_terran",
        mmr=1500
    )
    
    await data_service.create_or_update_mmr(
        discord_uid=test_player_2_uid,
        player_name="Player2",
        race="sc2_protoss",
        mmr=1500
    )
    
    # Wait for writes to complete
    await asyncio.sleep(0.5)
    
    # Create a match
    match_data = {
        'player_1_discord_uid': test_player_1_uid,
        'player_2_discord_uid': test_player_2_uid,
        'player_1_race': 'bw_terran',
        'player_2_race': 'sc2_protoss',
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
    
    # Wait for the match to be loaded into memory
    await asyncio.sleep(0.5)
    
    # Retrieve the match from memory
    print("[TEST] Retrieving match from memory...")
    match = data_service.get_match(match_id)
    
    assert match is not None, "Match should be retrievable from memory"
    assert match['id'] == match_id, "Match ID should match"
    assert match['player_1_discord_uid'] == test_player_1_uid, "Player 1 UID should match"
    assert match['player_2_discord_uid'] == test_player_2_uid, "Player 2 UID should match"
    assert match['player_1_race'] == 'bw_terran', "Player 1 race should match"
    assert match['player_2_race'] == 'sc2_protoss', "Player 2 race should match"
    
    print("[TEST] Match data verified successfully")
    
    # Test get_match_mmrs
    print("[TEST] Testing get_match_mmrs...")
    p1_mmr, p2_mmr = data_service.get_match_mmrs(match_id)
    assert p1_mmr == 1500, "Player 1 MMR should be 1500"
    assert p2_mmr == 1500, "Player 2 MMR should be 1500"
    print(f"[TEST] Match MMRs verified: P1={p1_mmr}, P2={p2_mmr}")
    
    # Shutdown
    await data_service.shutdown()
    
    print("[TEST] Match creation flow test completed successfully")
    return True


if __name__ == "__main__":
    try:
        initialize_pool(DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS)
        success = asyncio.run(test_match_creation_flow())
        close_pool()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[FATAL] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        close_pool()
        sys.exit(1)

