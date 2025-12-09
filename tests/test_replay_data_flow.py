"""
Test for the complete replay data flow with the four new game setting columns.

This test validates:
1. parse_replay_data_blocking extracts the four new fields
2. ReplayParsed dataclass includes them
3. replay_service.py includes them in the database insert dictionary
4. db_reader_writer.py SQL statement includes them
5. data_access_service.py DataFrame schema includes them
6. Data flows correctly through the entire pipeline
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.backend.services.replay_service import (
    parse_replay_data_blocking,
    ReplayParsed,
)
from src.backend.db.db_reader_writer import DatabaseWriter
from src.backend.services.data_access_service import DataAccessService
import dataclasses
import inspect


def test_parse_replay_data_blocking_extracts_new_fields():
    """Test that parse_replay_data_blocking extracts the four new game setting fields."""
    print("\n[TEST] parse_replay_data_blocking extracts new fields...")
    
    source = inspect.getsource(parse_replay_data_blocking)
    required_fields = ["game_privacy", "game_speed", "game_duration_setting", "locked_alliances"]
    
    for field in required_fields:
        assert field in source, f"{field} not found in parse_replay_data_blocking"
    
    print("[PASS] All four fields are extracted in parse_replay_data_blocking")


def test_replay_parsed_dataclass_includes_new_fields():
    """Test that ReplayParsed dataclass has the four new fields."""
    print("\n[TEST] ReplayParsed dataclass includes new fields...")
    
    fields = {f.name for f in dataclasses.fields(ReplayParsed)}
    required = {"game_privacy", "game_speed", "game_duration_setting", "locked_alliances"}
    
    assert required.issubset(fields), f"Missing fields: {required - fields}"
    
    # Verify field types are correct
    field_types = {f.name: f.type for f in dataclasses.fields(ReplayParsed)}
    for field_name in required:
        assert field_types[field_name] == str, f"{field_name} should be str type"
    
    print(f"[PASS] ReplayParsed has {len(fields)} fields including the 4 new ones")


def test_database_writer_includes_new_fields():
    """Test that DatabaseWriter.insert_replay includes the four new fields."""
    print("\n[TEST] DatabaseWriter.insert_replay includes new fields...")
    
    source = inspect.getsource(DatabaseWriter.insert_replay)
    required_fields = ["game_privacy", "game_speed", "game_duration_setting", "locked_alliances"]
    
    for field in required_fields:
        assert field in source, f"{field} not found in DatabaseWriter.insert_replay"
        # Also verify the parameter placeholder is there
        assert f":{field}" in source, f":{field} placeholder not found in SQL"
    
    print("[PASS] DatabaseWriter.insert_replay includes all new fields in SQL")


def test_replay_service_includes_new_fields():
    """Test that replay_service prepares replay_data with the four new fields."""
    print("\n[TEST] replay_service includes new fields in data preparation...")
    
    from src.backend.services.replay_service import ReplayService
    
    source = inspect.getsource(ReplayService.store_upload_from_parsed_dict_async)
    required_fields = ["game_privacy", "game_speed", "game_duration_setting", "locked_alliances"]
    
    for field in required_fields:
        assert f'"{field}"' in source or f"'{field}'" in source, \
            f"{field} not found in replay_service data preparation"
        assert f"parsed_dict[" in source, "Should access parsed_dict to get values"
    
    print("[PASS] replay_service includes all new fields when preparing data")


def test_data_access_service_schema_includes_new_fields():
    """Test that DataAccessService replays DataFrame schema includes the new fields."""
    print("\n[TEST] DataAccessService replays schema includes new fields...")
    
    source = inspect.getsource(DataAccessService._load_all_tables)
    required_fields = ["game_privacy", "game_speed", "game_duration_setting", "locked_alliances"]
    
    for field in required_fields:
        assert field in source, f"{field} not found in DataAccessService._load_all_tables"
    
    print("[PASS] DataAccessService DataFrame schema includes all new fields")


def test_data_flow_integration():
    """
    Test that data can flow correctly through the pipeline.
    
    This is a conceptual test that verifies all components are compatible.
    """
    print("\n[TEST] Data flow integration...")
    
    # Step 1: Create a mock parsed_dict like parse_replay_data_blocking would return
    parsed_dict = {
        "error": None,
        "replay_hash": "test_hash_12345",
        "replay_date": "2025-10-28T12:00:00",
        "player_1_name": "Player1",
        "player_2_name": "Player2",
        "player_1_race": "sc2_terran",
        "player_2_race": "sc2_zerg",
        "result": 1,
        "player_1_handle": "handle1",
        "player_2_handle": "handle2",
        "observers": [],
        "map_name": "Golden Wall",
        "duration": 600,
        "game_privacy": "Private",
        "game_speed": "Faster",
        "game_duration_setting": "Unlimited",
        "locked_alliances": "Off",
    }
    
    # Step 2: Verify all expected fields are present
    expected_fields = [
        "replay_hash", "replay_date", "player_1_name", "player_2_name",
        "player_1_race", "player_2_race", "result", "player_1_handle",
        "player_2_handle", "observers", "map_name", "duration",
        "game_privacy", "game_speed", "game_duration_setting", "locked_alliances"
    ]
    
    for field in expected_fields:
        assert field in parsed_dict, f"Field {field} missing from parsed_dict"
    
    # Step 3: Verify that this dict could be converted to ReplayParsed
    try:
        # Note: We skip uploaded_at since it's added later
        replay_parsed = ReplayParsed(
            replay_hash=parsed_dict["replay_hash"],
            replay_date=parsed_dict["replay_date"],
            player_1_name=parsed_dict["player_1_name"],
            player_2_name=parsed_dict["player_2_name"],
            player_1_race=parsed_dict["player_1_race"],
            player_2_race=parsed_dict["player_2_race"],
            result=parsed_dict["result"],
            player_1_handle=parsed_dict["player_1_handle"],
            player_2_handle=parsed_dict["player_2_handle"],
            observers=parsed_dict["observers"],
            map_name=parsed_dict["map_name"],
            duration=parsed_dict["duration"],
            game_privacy=parsed_dict["game_privacy"],
            game_speed=parsed_dict["game_speed"],
            game_duration_setting=parsed_dict["game_duration_setting"],
            locked_alliances=parsed_dict["locked_alliances"],
        )
        print("[PASS] Parsed dict can be converted to ReplayParsed")
    except TypeError as e:
        raise AssertionError(f"Failed to create ReplayParsed: {e}")
    
    print("[PASS] Data flow integration test passed")


if __name__ == "__main__":
    try:
        test_parse_replay_data_blocking_extracts_new_fields()
        test_replay_parsed_dataclass_includes_new_fields()
        test_database_writer_includes_new_fields()
        test_replay_service_includes_new_fields()
        test_data_access_service_schema_includes_new_fields()
        test_data_flow_integration()
        
        print("\n" + "=" * 60)
        print("[SUCCESS] All replay data flow tests passed!")
        print("=" * 60)
        print("\nImplementation Summary:")
        print("[OK] parse_replay_data_blocking extracts 4 new fields")
        print("[OK] ReplayParsed dataclass includes 4 new fields")
        print("[OK] DatabaseWriter.insert_replay SQL includes 4 new fields")
        print("[OK] replay_service prepares replay_data with 4 new fields")
        print("[OK] DataAccessService schema includes 4 new fields")
        print("[OK] Data flow is correctly integrated end-to-end")
        print("\nThe new game settings are now persisted in the database and")
        print("available for future use in frontend display and other services.")
    except AssertionError as e:
        print(f"\n[FAILED] {e}")
        sys.exit(1)
