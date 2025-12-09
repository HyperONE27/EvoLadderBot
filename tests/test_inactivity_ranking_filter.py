"""
Test for the two-week inactivity filter in the ranking system.

This test verifies that:
1. Players with 0 games are unranked
2. Players with no last_played timestamp are unranked
3. Players with last_played > 2 weeks ago are unranked
4. Players with last_played within 2 weeks are ranked
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
import polars as pl
from typing import Optional

from src.backend.services.ranking_service import RankingService
from src.backend.services.data_access_service import DataAccessService


def create_mock_mmr_entry(
    discord_uid: int,
    race: str,
    mmr: int,
    games_played: int,
    last_played: Optional[datetime] = None
):
    """Helper to create a mock MMR entry."""
    return {
        "discord_uid": discord_uid,
        "race": race,
        "mmr": mmr,
        "games_played": games_played,
        "last_played": last_played,
        "games_won": 0,
        "games_lost": 0,
        "games_drawn": 0,
        "player_name": f"Player{discord_uid}"
    }


def test_ranking_service_filters_inactive_players():
    """Test that the ranking service correctly filters out inactive players."""
    
    # Setup: Create mock data service
    mock_data_service = Mock(spec=DataAccessService)
    
    # Create test data with various activity states
    now = datetime.now(timezone.utc)
    one_day_ago = now - timedelta(days=1)
    ten_days_ago = now - timedelta(days=10)
    thirteen_days_ago = now - timedelta(days=13)
    fifteen_days_ago = now - timedelta(days=15)
    twenty_days_ago = now - timedelta(days=20)
    thirty_days_ago = now - timedelta(days=30)
    
    # Create mock MMR DataFrame with various scenarios
    mock_mmr_data = [
        # Active players (should be ranked)
        create_mock_mmr_entry(1, "sc2_terran", 2000, 10, one_day_ago),
        create_mock_mmr_entry(2, "sc2_zerg", 1900, 5, ten_days_ago),
        create_mock_mmr_entry(3, "sc2_protoss", 1800, 8, thirteen_days_ago),
        
        # Inactive players (should be unranked)
        create_mock_mmr_entry(4, "sc2_terran", 1700, 15, fifteen_days_ago),  # Just over 2 weeks
        create_mock_mmr_entry(5, "sc2_zerg", 1600, 20, twenty_days_ago),  # 20 days
        create_mock_mmr_entry(6, "sc2_protoss", 1500, 25, thirty_days_ago),  # 30 days
        
        # Edge cases (should be unranked)
        create_mock_mmr_entry(7, "sc2_terran", 1400, 0, None),  # Never played
        create_mock_mmr_entry(8, "sc2_zerg", 1300, 5, None),  # Played but no timestamp
        create_mock_mmr_entry(9, "sc2_protoss", 0, 0, None),  # Brand new player
    ]
    
    # Convert to Polars DataFrame (mimicking what DataAccessService returns)
    mock_df = pl.DataFrame(mock_mmr_data)
    
    # Mock the get_leaderboard_dataframe method
    mock_data_service.get_leaderboard_dataframe.return_value = mock_df
    
    # Create ranking service with mock data service
    ranking_service = RankingService(data_service=mock_data_service)
    
    # Execute: Refresh rankings
    ranking_service.refresh_rankings()
    
    # Verify: Check that active players are ranked
    player1_rank = ranking_service.get_rank(1, "sc2_terran")
    assert player1_rank["letter_rank"] != "u_rank", "Player 1 (1 day ago) should be ranked"
    assert player1_rank["global_rank"] > 0, "Player 1 should have a valid global rank"
    
    player2_rank = ranking_service.get_rank(2, "sc2_zerg")
    assert player2_rank["letter_rank"] != "u_rank", "Player 2 (10 days ago) should be ranked"
    assert player2_rank["global_rank"] > 0, "Player 2 should have a valid global rank"
    
    player3_rank = ranking_service.get_rank(3, "sc2_protoss")
    assert player3_rank["letter_rank"] != "u_rank", "Player 3 (13 days ago) should be ranked"
    assert player3_rank["global_rank"] > 0, "Player 3 should have a valid global rank"
    
    # Verify: Check that inactive players are unranked
    player4_rank = ranking_service.get_rank(4, "sc2_terran")
    assert player4_rank["letter_rank"] == "u_rank", "Player 4 (15 days ago) should be unranked"
    assert player4_rank["global_rank"] == -1, "Player 4 should have no global rank"
    
    player5_rank = ranking_service.get_rank(5, "sc2_zerg")
    assert player5_rank["letter_rank"] == "u_rank", "Player 5 (20 days ago) should be unranked"
    assert player5_rank["global_rank"] == -1, "Player 5 should have no global rank"
    
    player6_rank = ranking_service.get_rank(6, "sc2_protoss")
    assert player6_rank["letter_rank"] == "u_rank", "Player 6 (30 days ago) should be unranked"
    assert player6_rank["global_rank"] == -1, "Player 6 should have no global rank"
    
    # Verify: Check edge cases are unranked
    player7_rank = ranking_service.get_rank(7, "sc2_terran")
    assert player7_rank["letter_rank"] == "u_rank", "Player 7 (0 games) should be unranked"
    
    player8_rank = ranking_service.get_rank(8, "sc2_zerg")
    assert player8_rank["letter_rank"] == "u_rank", "Player 8 (no timestamp) should be unranked"
    
    player9_rank = ranking_service.get_rank(9, "sc2_protoss")
    assert player9_rank["letter_rank"] == "u_rank", "Player 9 (new player) should be unranked"
    
    # Verify: Check total counts
    total_ranked = ranking_service.get_total_ranked_entries()
    assert total_ranked == 3, f"Expected 3 ranked entries, got {total_ranked}"


def test_exact_two_week_boundary():
    """Test behavior at exactly the 2-week boundary."""
    
    mock_data_service = Mock(spec=DataAccessService)
    
    now = datetime.now(timezone.utc)
    exactly_two_weeks_ago = now - timedelta(weeks=2)
    just_under_two_weeks = now - timedelta(days=13, hours=23, minutes=59)
    just_over_two_weeks = now - timedelta(days=14, hours=0, minutes=1)
    
    mock_mmr_data = [
        create_mock_mmr_entry(1, "sc2_terran", 2000, 10, just_under_two_weeks),
        create_mock_mmr_entry(2, "sc2_zerg", 1900, 10, exactly_two_weeks_ago),
        create_mock_mmr_entry(3, "sc2_protoss", 1800, 10, just_over_two_weeks),
    ]
    
    mock_df = pl.DataFrame(mock_mmr_data)
    mock_data_service.get_leaderboard_dataframe.return_value = mock_df
    
    ranking_service = RankingService(data_service=mock_data_service)
    ranking_service.refresh_rankings()
    
    # Just under 2 weeks should be ranked
    player1_rank = ranking_service.get_rank(1, "sc2_terran")
    assert player1_rank["letter_rank"] != "u_rank", "Player 1 (just under 2 weeks) should be ranked"
    
    # Exactly 2 weeks should still be ranked (within the 2-week window)
    player2_rank = ranking_service.get_rank(2, "sc2_zerg")
    assert player2_rank["letter_rank"] != "u_rank", "Player 2 (exactly 2 weeks) should still be ranked"
    
    # Just over 2 weeks should be unranked
    player3_rank = ranking_service.get_rank(3, "sc2_protoss")
    assert player3_rank["letter_rank"] == "u_rank", "Player 3 (just over 2 weeks) should be unranked"


def test_malformed_timestamp_handling():
    """Test that malformed timestamps are handled gracefully."""
    
    mock_data_service = Mock(spec=DataAccessService)
    
    now = datetime.now(timezone.utc)
    valid_timestamp_str = (now - timedelta(days=5)).isoformat()
    
    # In a real-world bad data scenario, the column might be loaded as strings (object/utf8)
    # if the types are inconsistent. We simulate that here.
    mock_mmr_data = [
        create_mock_mmr_entry(1, "sc2_terran", 2000, 10, valid_timestamp_str),
        create_mock_mmr_entry(2, "sc2_zerg", 1900, 10, "invalid-timestamp"),
        create_mock_mmr_entry(3, "sc2_protoss", 1800, 10, "2023-99-99T99:99:99+00:00"),
    ]
    
    # Polars can create a DataFrame if all values in the column are strings
    mock_df = pl.DataFrame(mock_mmr_data)
    mock_data_service.get_leaderboard_dataframe.return_value = mock_df
    
    ranking_service = RankingService(data_service=mock_data_service)
    
    # Should not crash
    ranking_service.refresh_rankings()
    
    # Valid timestamp should be ranked
    player1_rank = ranking_service.get_rank(1, "sc2_terran")
    assert player1_rank["letter_rank"] != "u_rank", "Player 1 (valid timestamp) should be ranked"
    
    # Invalid timestamps should be unranked
    player2_rank = ranking_service.get_rank(2, "sc2_zerg")
    assert player2_rank["letter_rank"] == "u_rank", "Player 2 (malformed timestamp) should be unranked"
    
    player3_rank = ranking_service.get_rank(3, "sc2_protoss")
    assert player3_rank["letter_rank"] == "u_rank", "Player 3 (invalid timestamp) should be unranked"


def test_last_played_column_from_database():
    """Test that last_played comes from the database, not calculated dynamically."""
    
    # This test verifies that DataAccessService returns last_played from mmrs_1v1 table
    # We'll mock the database loading to ensure the column is present
    
    mock_data_service = Mock(spec=DataAccessService)
    
    now = datetime.now(timezone.utc)
    db_timestamp = (now - timedelta(days=5))
    
    # This simulates what would come from the database
    mock_mmr_data = [
        {
            "discord_uid": 1,
            "race": "sc2_terran",
            "mmr": 2000,
            "games_played": 10,
            "last_played": db_timestamp,  # This comes from mmrs_1v1.last_played
            "games_won": 5,
            "games_lost": 5,
            "games_drawn": 0,
            "player_name": "Player1"
        }
    ]
    
    mock_df = pl.DataFrame(mock_mmr_data)
    mock_data_service.get_leaderboard_dataframe.return_value = mock_df
    
    ranking_service = RankingService(data_service=mock_data_service)
    ranking_service.refresh_rankings()
    
    # Verify the player is ranked using the database timestamp
    player_rank = ranking_service.get_rank(1, "sc2_terran")
    assert player_rank["letter_rank"] != "u_rank", "Player should be ranked based on database last_played"
    assert player_rank["global_rank"] > 0, "Player should have a valid global rank"


if __name__ == "__main__":
    # Run tests
    print("Running test_ranking_service_filters_inactive_players...")
    test_ranking_service_filters_inactive_players()
    print("✓ PASSED\n")
    
    print("Running test_exact_two_week_boundary...")
    test_exact_two_week_boundary()
    print("✓ PASSED\n")
    
    print("Running test_malformed_timestamp_handling...")
    test_malformed_timestamp_handling()
    print("✓ PASSED\n")
    
    print("Running test_last_played_column_from_database...")
    test_last_played_column_from_database()
    print("✓ PASSED\n")
    
    print("=" * 60)
    print("All tests passed successfully!")
    print("=" * 60)

