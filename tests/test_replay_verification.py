"""
Test replay verification feature.

This test file verifies that the replay verification logic correctly validates
replay data against match assignment data.
"""

import json
import os
from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from src.backend.services.data_access_service import DataAccessService
from src.backend.services.match_completion_service import MatchCompletionService
from src.backend.services.replay_service import parse_replay_data_blocking


@pytest.fixture
def data_service():
    """Create a DataAccessService instance with test data."""
    service = DataAccessService()
    
    # Load test match data from the proposal
    match_data = {
        "idx": [13],
        "id": [14],
        "player_1_discord_uid": ["218147282875318274"],
        "player_2_discord_uid": ["473117604488151043"],
        "player_1_race": ["bw_zerg"],
        "player_2_race": ["sc2_protoss"],
        "player_1_mmr": [1610],
        "player_2_mmr": [1500],
        "player_1_report": [2],
        "player_2_report": [2],
        "match_result": [2],
        "mmr_change": [-25],
        "map_played": ["Tokamak LE"],
        "server_used": ["USE"],
        "played_at": ["2025-10-24 06:42:00+00"],
        "player_1_replay_path": ["https://ibigtopmfsmarkujjfen.supabase.co/storage/v1/object/public/replays/14/3812a4e1c1ea9c34ddda_1761288313.SC2Replay"],
        "player_1_replay_time": ["2025-10-24 06:45:14+00"],
        "player_2_replay_path": ["https://ibigtopmfsmarkujjfen.supabase.co/storage/v1/object/public/replays/14/13fc2de194b91eabaee5_1761288312.SC2Replay"],
        "player_2_replay_time": ["2025-10-24 06:45:13+00"],
        "status": ["IN_PROGRESS"]
    }
    
    service._matches_1v1_df = pl.DataFrame(match_data, infer_schema_length=None)
    
    # Initialize empty replays dataframe
    service._replays_df = pl.DataFrame({
        "id": [],
        "replay_hash": [],
        "player_1_name": [],
        "player_2_name": [],
        "map_name": [],
        "result": []
    })
    
    return service


@pytest.fixture
def match_completion_service_instance():
    """Create a MatchCompletionService instance."""
    return MatchCompletionService()


def test_parse_valid_replay():
    """Test parsing HyperONEgunnerTokamak.SC2Replay (should pass all checks)."""
    replay_path = "tests/test_data/test_replay_files/HyperONEgunnerTokamak.SC2Replay"
    
    with open(replay_path, 'rb') as f:
        replay_bytes = f.read()
    
    replay_info = parse_replay_data_blocking(replay_bytes)
    
    # Verify no parsing errors
    assert replay_info.get("error") is None
    assert replay_info.get("map_name") is not None
    assert replay_info.get("player_1_race") is not None
    assert replay_info.get("player_2_race") is not None
    assert replay_info.get("result") is not None
    
    print(f"Parsed replay: {replay_info}")


def test_verify_races_match(data_service, match_completion_service_instance):
    """Test that race verification works correctly."""
    replay_path = "tests/test_data/test_replay_files/HyperONEgunnerTokamak.SC2Replay"
    
    with open(replay_path, 'rb') as f:
        replay_bytes = f.read()
    
    replay_info = parse_replay_data_blocking(replay_bytes)
    match_info = data_service.get_match(14)
    
    # Test race verification
    races_ok = match_completion_service_instance._verify_races(match_info, replay_info)
    
    print(f"Match races: {match_info.get('player_1_race')}, {match_info.get('player_2_race')}")
    print(f"Replay races: {replay_info.get('player_1_race')}, {replay_info.get('player_2_race')}")
    print(f"Races match: {races_ok}")
    
    assert races_ok is True, "Races should match for HyperONEgunnerTokamak replay"


def test_verify_map_match(data_service, match_completion_service_instance):
    """Test that map verification works correctly."""
    replay_path = "tests/test_data/test_replay_files/HyperONEgunnerTokamak.SC2Replay"
    
    with open(replay_path, 'rb') as f:
        replay_bytes = f.read()
    
    replay_info = parse_replay_data_blocking(replay_bytes)
    match_info = data_service.get_match(14)
    
    # Test map verification
    map_ok = match_completion_service_instance._verify_map(match_info, replay_info)
    
    print(f"Match map: {match_info.get('map_played')}")
    print(f"Replay map: {replay_info.get('map_name')}")
    print(f"Map matches: {map_ok}")
    
    assert map_ok is True, "Map should match for HyperONEgunnerTokamak replay"


def test_verify_timestamp_match(data_service, match_completion_service_instance):
    """Test that timestamp verification works correctly."""
    replay_path = "tests/test_data/test_replay_files/HyperONEgunnerTokamak.SC2Replay"
    
    with open(replay_path, 'rb') as f:
        replay_bytes = f.read()
    
    replay_info = parse_replay_data_blocking(replay_bytes)
    match_info = data_service.get_match(14)
    
    # Test timestamp verification
    timestamp_ok = match_completion_service_instance._verify_timestamp(match_info, replay_info)
    
    print(f"Match played_at: {match_info.get('played_at')}")
    print(f"Replay date: {replay_info.get('replay_date')}")
    print(f"Replay duration: {replay_info.get('duration')} seconds")
    print(f"Timestamp matches: {timestamp_ok}")
    
    assert timestamp_ok is True, "Timestamp should match for HyperONEgunnerTokamak replay"


def test_verify_observers(data_service, match_completion_service_instance):
    """Test that observer verification works correctly."""
    replay_path = "tests/test_data/test_replay_files/HyperONEgunnerTokamak.SC2Replay"
    
    with open(replay_path, 'rb') as f:
        replay_bytes = f.read()
    
    replay_info = parse_replay_data_blocking(replay_bytes)
    
    # Test observer verification
    observers_ok = match_completion_service_instance._verify_observers(replay_info)
    
    print(f"Replay observers: {replay_info.get('observers')}")
    print(f"No observers: {observers_ok}")
    
    assert observers_ok is True, "No observers should be present in HyperONEgunnerTokamak replay"


def test_full_verification_valid_replay(data_service, match_completion_service_instance):
    """Test full verification flow for a valid replay (HyperONEgunnerTokamak)."""
    replay_path = "tests/test_data/test_replay_files/HyperONEgunnerTokamak.SC2Replay"
    
    with open(replay_path, 'rb') as f:
        replay_bytes = f.read()
    
    replay_info = parse_replay_data_blocking(replay_bytes)
    match_info = data_service.get_match(14)
    
    # Perform all verification checks
    races_ok = match_completion_service_instance._verify_races(match_info, replay_info)
    map_ok = match_completion_service_instance._verify_map(match_info, replay_info)
    timestamp_ok = match_completion_service_instance._verify_timestamp(match_info, replay_info)
    observers_ok = match_completion_service_instance._verify_observers(replay_info)
    all_ok = all([races_ok, map_ok, timestamp_ok, observers_ok])
    
    print("\n=== Verification Results for HyperONEgunnerTokamak ===")
    print(f"Races match: {races_ok}")
    print(f"Map matches: {map_ok}")
    print(f"Timestamp matches: {timestamp_ok}")
    print(f"No observers: {observers_ok}")
    print(f"All checks pass: {all_ok}")
    
    assert all_ok is True, "All verification checks should pass for HyperONEgunnerTokamak replay"


def test_full_verification_invalid_replay_isles(data_service, match_completion_service_instance):
    """Test full verification flow for an invalid replay (DarkReBellionIsles)."""
    replay_path = "tests/test_data/test_replay_files/DarkReBellionIsles.SC2Replay"
    
    with open(replay_path, 'rb') as f:
        replay_bytes = f.read()
    
    replay_info = parse_replay_data_blocking(replay_bytes)
    match_info = data_service.get_match(14)
    
    # Perform all verification checks
    races_ok = match_completion_service_instance._verify_races(match_info, replay_info)
    map_ok = match_completion_service_instance._verify_map(match_info, replay_info)
    timestamp_ok = match_completion_service_instance._verify_timestamp(match_info, replay_info)
    observers_ok = match_completion_service_instance._verify_observers(replay_info)
    all_ok = all([races_ok, map_ok, timestamp_ok, observers_ok])
    
    print("\n=== Verification Results for DarkReBellionIsles ===")
    print(f"Races match: {races_ok}")
    print(f"Map matches: {map_ok}")
    print(f"Timestamp matches: {timestamp_ok}")
    print(f"No observers: {observers_ok}")
    print(f"All checks pass: {all_ok}")
    
    # At least one check should fail
    assert all_ok is False, "At least one verification check should fail for DarkReBellionIsles replay"


def test_full_verification_invalid_replay_golden_wall(data_service, match_completion_service_instance):
    """Test full verification flow for an invalid replay (threepointPSIArcGoldenWall)."""
    replay_path = "tests/test_data/test_replay_files/threepointPSIArcGoldenWall.SC2Replay"
    
    with open(replay_path, 'rb') as f:
        replay_bytes = f.read()
    
    replay_info = parse_replay_data_blocking(replay_bytes)
    match_info = data_service.get_match(14)
    
    # Perform all verification checks
    races_ok = match_completion_service_instance._verify_races(match_info, replay_info)
    map_ok = match_completion_service_instance._verify_map(match_info, replay_info)
    timestamp_ok = match_completion_service_instance._verify_timestamp(match_info, replay_info)
    observers_ok = match_completion_service_instance._verify_observers(replay_info)
    all_ok = all([races_ok, map_ok, timestamp_ok, observers_ok])
    
    print("\n=== Verification Results for threepointPSIArcGoldenWall ===")
    print(f"Races match: {races_ok}")
    print(f"Map matches: {map_ok}")
    print(f"Timestamp matches: {timestamp_ok}")
    print(f"No observers: {observers_ok}")
    print(f"All checks pass: {all_ok}")
    
    # At least one check should fail
    assert all_ok is False, "At least one verification check should fail for threepointPSIArcGoldenWall replay"


def test_determine_winner_report(match_completion_service_instance):
    """Test winner determination logic."""
    match_info = {"player_1_race": "bw_zerg", "player_2_race": "sc2_protoss"}
    
    # Test player 1 win - replay data must include both player races
    replay_data_p1_win = {
        "result": 1,
        "player_1_race": "bw_zerg",
        "player_2_race": "sc2_protoss"
    }
    winner = match_completion_service_instance._determine_winner_report(match_info, replay_data_p1_win)
    assert winner == 1, "Should return 1 for player 1 win with matching race"
    
    # Test player 2 win - replay data must include both player races
    replay_data_p2_win = {
        "result": 2,
        "player_1_race": "bw_zerg",
        "player_2_race": "sc2_protoss"
    }
    winner = match_completion_service_instance._determine_winner_report(match_info, replay_data_p2_win)
    assert winner == 2, "Should return 2 for player 2 win with matching race"
    
    # Test draw
    replay_data_draw = {
        "result": 0,
        "player_1_race": "bw_zerg",
        "player_2_race": "sc2_protoss"
    }
    winner = match_completion_service_instance._determine_winner_report(match_info, replay_data_draw)
    assert winner == 0, "Should return 0 for draw"
    
    # Test race mismatch - winner's race doesn't match any assigned race (players swapped)
    replay_data_race_mismatch = {
        "result": 1,
        "player_1_race": "sc2_terran",  # Doesn't match either assigned race
        "player_2_race": "sc2_protoss"
    }
    winner = match_completion_service_instance._determine_winner_report(match_info, replay_data_race_mismatch)
    assert winner is None, "Should return None when winner's race doesn't match assigned races"
    
    print("Winner determination tests passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

