"""
Unit test to verify that in-memory DataFrame updates are correctly applied.

This test verifies:
1. DataFrame updates work correctly with the new helper method
2. create_or_update_mmr works for both create and update paths
3. update_player_mmr uses the helper method correctly
4. Operations are thread-safe with proper locking
"""
import sys
from pathlib import Path
import asyncio

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def test_in_memory_updates():
    """Test that in-memory DataFrame updates are correctly persisted."""
    print("\n" + "="*80)
    print("TEST: In-Memory DataFrame Update Persistence")
    print("="*80)
    
    from src.backend.services.data_access_service import DataAccessService
    
    # Create a fresh instance for testing
    service = DataAccessService()
    
    # Initialize the service (this would normally load from DB, but we'll work with empty state)
    print("\n[Test 1] Testing create_or_update_mmr (create path)...")
    
    # Manually initialize the DataFrame to empty state
    import polars as pl
    from datetime import timezone as tz
    service._mmrs_1v1_df = pl.DataFrame({
        "id": pl.Series([], dtype=pl.Int64),
        "discord_uid": pl.Series([], dtype=pl.Int64),
        "player_name": pl.Series([], dtype=pl.Utf8),
        "race": pl.Series([], dtype=pl.Utf8),
        "mmr": pl.Series([], dtype=pl.Int64),
        "games_played": pl.Series([], dtype=pl.Int64),
        "games_won": pl.Series([], dtype=pl.Int64),
        "games_lost": pl.Series([], dtype=pl.Int64),
        "games_drawn": pl.Series([], dtype=pl.Int64),
        "last_played": pl.Series([], dtype=pl.Datetime(time_zone="UTC"))
    })
    
    # Mock the write queue so we don't need database
    service._write_queue = asyncio.Queue()
    
    initial_count = len(service._mmrs_1v1_df)
    print(f"    Initial DataFrame row count: {initial_count}")
    
    # Create a new MMR record
    await service.create_or_update_mmr(
        discord_uid=123456789,
        player_name="TestPlayer1",
        race="terran",
        mmr=1500,
        games_played=1,
        games_won=1,
        games_lost=0,
        games_drawn=0
    )
    
    after_create_count = len(service._mmrs_1v1_df)
    print(f"    After create: {after_create_count} rows")
    
    if after_create_count == initial_count + 1:
        print("    OK: New row was added to in-memory DataFrame")
    else:
        print(f"    X FAIL: Expected {initial_count + 1} rows, got {after_create_count}")
        return False
    
    # Verify the data is actually in the DataFrame
    test_record = service._mmrs_1v1_df.filter(
        (pl.col("discord_uid") == 123456789) & (pl.col("race") == "terran")
    )
    
    if len(test_record) == 1:
        print("    OK: New record is retrievable from DataFrame")
        record_dict = test_record.to_dicts()[0]
        print(f"        discord_uid={record_dict['discord_uid']}, race={record_dict['race']}, mmr={record_dict['mmr']}")
    else:
        print(f"    X FAIL: Expected 1 record, found {len(test_record)}")
        return False
    
    print("\n[Test 2] Testing create_or_update_mmr (update path)...")
    
    # Update the existing record
    await service.create_or_update_mmr(
        discord_uid=123456789,
        player_name="TestPlayer1",
        race="terran",
        mmr=1550,
        games_played=2,
        games_won=2,
        games_lost=0,
        games_drawn=0
    )
    
    after_update_count = len(service._mmrs_1v1_df)
    print(f"    After update: {after_update_count} rows")
    
    if after_update_count == after_create_count:
        print("    OK: Row count unchanged (update, not create)")
    else:
        print(f"    X FAIL: Expected {after_create_count} rows, got {after_update_count}")
        return False
    
    # Verify the MMR was actually updated
    updated_record = service._mmrs_1v1_df.filter(
        (pl.col("discord_uid") == 123456789) & (pl.col("race") == "terran")
    )
    
    if len(updated_record) == 1:
        record_dict = updated_record.to_dicts()[0]
        if record_dict['mmr'] == 1550 and record_dict['games_played'] == 2:
            print("    OK: Record was updated correctly in DataFrame")
            print(f"        mmr={record_dict['mmr']}, games_played={record_dict['games_played']}")
        else:
            print(f"    X FAIL: MMR not updated (expected 1550, got {record_dict['mmr']})")
            return False
    else:
        print(f"    X FAIL: Expected 1 record after update, found {len(updated_record)}")
        return False
    
    print("\n[Test 3] Testing update_player_mmr...")
    
    # Use update_player_mmr on the existing record
    await service.update_player_mmr(
        discord_uid=123456789,
        race="terran",
        new_mmr=1600,
        games_played=3,
        games_won=3,
        games_lost=0,
        games_drawn=0
    )
    
    final_record = service._mmrs_1v1_df.filter(
        (pl.col("discord_uid") == 123456789) & (pl.col("race") == "terran")
    )
    
    if len(final_record) == 1:
        record_dict = final_record.to_dicts()[0]
        if record_dict['mmr'] == 1600 and record_dict['games_played'] == 3:
            print("    OK: update_player_mmr correctly updated DataFrame")
            print(f"        mmr={record_dict['mmr']}, games_played={record_dict['games_played']}")
        else:
            print(f"    X FAIL: MMR not updated (expected 1600, got {record_dict['mmr']})")
            return False
    else:
        print(f"    X FAIL: Expected 1 record, found {len(final_record)}")
        return False
    
    print("\n[Test 4] Testing concurrent updates (locking)...")
    
    # Create multiple records
    await service.create_or_update_mmr(
        discord_uid=111111111,
        player_name="Player1",
        race="protoss",
        mmr=1400,
        games_played=1,
        games_won=1,
        games_lost=0,
        games_drawn=0
    )
    
    await service.create_or_update_mmr(
        discord_uid=222222222,
        player_name="Player2",
        race="zerg",
        mmr=1600,
        games_played=1,
        games_won=1,
        games_lost=0,
        games_drawn=0
    )
    
    current_count = len(service._mmrs_1v1_df)
    print(f"    Current DataFrame row count: {current_count}")
    
    # Run concurrent updates
    tasks = [
        service.update_player_mmr(111111111, "protoss", 1450, 2, 2, 0, 0),
        service.update_player_mmr(222222222, "zerg", 1650, 2, 2, 0, 0),
    ]
    
    results = await asyncio.gather(*tasks)
    
    if all(results):
        print("    OK: All concurrent updates succeeded")
    else:
        print("    X FAIL: Some concurrent updates failed")
        return False
    
    # Verify both were updated
    player1 = service._mmrs_1v1_df.filter(
        (pl.col("discord_uid") == 111111111) & (pl.col("race") == "protoss")
    ).to_dicts()[0]
    
    player2 = service._mmrs_1v1_df.filter(
        (pl.col("discord_uid") == 222222222) & (pl.col("race") == "zerg")
    ).to_dicts()[0]
    
    if player1['mmr'] == 1450 and player2['mmr'] == 1650:
        print("    OK: Concurrent updates were both applied correctly")
        print(f"        Player1: mmr={player1['mmr']}")
        print(f"        Player2: mmr={player2['mmr']}")
    else:
        print("    X FAIL: Concurrent updates not correctly applied")
        return False
    
    print("\n" + "="*80)
    print("ALL TESTS PASSED - In-memory updates working correctly")
    print("="*80)
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_in_memory_updates())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nTest failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

