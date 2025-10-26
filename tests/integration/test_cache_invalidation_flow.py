"""
Integration tests for event-driven leaderboard cache invalidation.

These tests verify that high-level service methods correctly invalidate the cache
as a side-effect, ensuring the cache invalidation logic is properly integrated
throughout the data access layer.
"""

import pytest
import asyncio
import polars as pl
from datetime import datetime

from src.backend.services.data_access_service import DataAccessService


@pytest.fixture(autouse=True)
def reset_data_access_service_singleton():
    """Reset the DataAccessService singleton before each test."""
    # Clear the singleton
    DataAccessService._instance = None
    DataAccessService._initialized = False
    yield
    # Cleanup after test
    DataAccessService._instance = None
    DataAccessService._initialized = False


@pytest.fixture
def initialized_service():
    """Provide an initialized DataAccessService instance with mock data."""
    service = DataAccessService()
    
    # Manually initialize in-memory DataFrames with mock data
    service._players_df = pl.DataFrame({
        "discord_uid": [1, 2],
        "discord_username": ["user1", "user2"],
        "player_name": ["Player1", "Player2"],
        "country": ["US", "KR"],
        "remaining_aborts": [3, 3],
        "battletag": [None, None],
        "alt_player_name_1": [None, None],
        "alt_player_name_2": [None, None],
        "region": ["NA", "KR"],
    })
    
    service._mmrs_1v1_df = pl.DataFrame({
        "discord_uid": pl.Series([1, 2], dtype=pl.Int64),
        "race": ["terran", "zerg"],
        "mmr": pl.Series([1500, 1600], dtype=pl.Int64),
        "player_name": ["Player1", "Player2"],
        "games_played": pl.Series([10, 15], dtype=pl.Int64),
        "games_won": pl.Series([6, 9], dtype=pl.Int64),
        "games_lost": pl.Series([4, 6], dtype=pl.Int64),
        "games_drawn": pl.Series([0, 0], dtype=pl.Int64),
    })
    
    service._preferences_1v1_df = pl.DataFrame({
        "discord_uid": [1, 2],
        "last_chosen_races": [None, None],
        "last_chosen_vetoes": [None, None],
    })
    
    service._matches_1v1_df = pl.DataFrame({
        "id": [123],
        "player_1_discord_uid": [1],
        "player_2_discord_uid": [2],
        "player_1_race": ["terran"],
        "player_2_race": ["zerg"],
        "map_played": ["Python"],
        "server_choice": ["NA"],
        "player_1_mmr": [1500],
        "player_2_mmr": [1600],
        "mmr_change": [0],
        "played_at": ["2025-10-24"],
        "player_1_report": [None],
        "player_2_report": [None],
        "match_result": [None],
        "player_1_replay_path": [None],
        "player_2_replay_path": [None],
        "player_1_replay_time": [None],
        "player_2_replay_time": [None],
        "status": ["IN_PROGRESS"],
    })
    
    service._replays_df = pl.DataFrame({
        "id": pl.Series([], dtype=pl.Int64),
        "replay_path": pl.Series([], dtype=pl.Utf8),
    })
    
    # Initialize write queue and other async state
    service._write_queue = asyncio.Queue()
    service._write_event = asyncio.Event()
    service._shutdown_event = asyncio.Event()
    
    return service


class TestMatchCompletionInvalidatesCache:
    """Test that completing a match invalidates the leaderboard cache."""
    
    @pytest.mark.asyncio
    async def test_match_completion_flow_invalidates_cache(self, initialized_service):
        """
        Verify that updating match MMR change correctly invalidates the cache.
        
        This simulates the workflow where a match completes and MMRs are adjusted.
        """
        # Arrange: Mark cache as valid
        initialized_service.mark_leaderboard_cache_valid()
        assert initialized_service.is_leaderboard_cache_valid() is True, \
            "Cache should be VALID as a precondition"
        
        # Act: Simulate match completion (which triggers MMR update)
        result = await initialized_service.update_match_mmr_change(
            match_id=123,
            mmr_change=16
        )
        
        # Assert
        assert result is True, "update_match_mmr_change should succeed"
        assert initialized_service.is_leaderboard_cache_valid() is False, \
            "Cache should be INVALID after match MMR change"


class TestPlayerInfoInvalidatesCache:
    """Test that player info changes invalidate the leaderboard cache."""
    
    @pytest.mark.asyncio
    async def test_player_info_update_flow_invalidates_cache(self, initialized_service):
        """
        Verify that updating player info (country) correctly invalidates the cache.
        
        This simulates a player changing their country via `/setcountry`.
        """
        # Arrange: Mark cache as valid
        initialized_service.mark_leaderboard_cache_valid()
        assert initialized_service.is_leaderboard_cache_valid() is True, \
            "Cache should be VALID as a precondition"
        
        # Act: Update player info (country is displayed on leaderboard)
        result = await initialized_service.update_player_info(
            discord_uid=1,
            country="CN"
        )
        
        # Assert
        assert result is True, "update_player_info should succeed"
        assert initialized_service.is_leaderboard_cache_valid() is False, \
            "Cache should be INVALID after player info change"


class TestNonLeaderboardActionsPreserveCache:
    """Test that non-leaderboard actions do not invalidate the cache."""
    
    @pytest.mark.asyncio
    async def test_non_mmr_flow_does_not_invalidate_cache(self, initialized_service):
        """
        Verify that updating player preferences does NOT invalidate the cache.
        
        Preferences are not displayed on the leaderboard, so they should not
        trigger cache invalidation.
        """
        # Arrange: Mark cache as valid
        initialized_service.mark_leaderboard_cache_valid()
        assert initialized_service.is_leaderboard_cache_valid() is True, \
            "Cache should be VALID as a precondition"
        
        # Act: Update player preferences (not displayed on leaderboard)
        result = await initialized_service.update_player_preferences(
            discord_uid=1,
            last_chosen_races='["T"]'
        )
        
        # Assert
        assert result is True, "update_player_preferences should succeed"
        assert initialized_service.is_leaderboard_cache_valid() is True, \
            "Cache should remain VALID after preference change (not leaderboard-related)"

