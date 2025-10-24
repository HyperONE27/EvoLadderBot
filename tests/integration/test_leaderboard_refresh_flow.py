"""
Integration test for leaderboard refresh flow.

Tests the event-driven cache invalidation feature end-to-end:
1. First leaderboard request generates and caches the data.
2. Second request hits the cache without refreshing.
3. An MMR-changing event invalidates the cache in DataAccessService.
4. Third request detects the invalid cache and triggers a full data refresh.

This test validates the complete loop of the event-driven leaderboard caching.
"""

import pytest
import asyncio
import polars as pl
from unittest.mock import patch, AsyncMock

from src.backend.services.data_access_service import DataAccessService
from src.backend.services.leaderboard_service import LeaderboardService


@pytest.fixture(autouse=True)
def reset_data_access_service_singleton():
    """Reset the DataAccessService singleton before each test."""
    DataAccessService._instance = None
    DataAccessService._initialized = False
    yield
    DataAccessService._instance = None
    DataAccessService._initialized = False


def create_mock_mmrs_df():
    """Create a properly-structured mock MMRs DataFrame."""
    return pl.DataFrame({
        "discord_uid": pl.Series([1, 2], dtype=pl.Int64),
        "race": ["terran", "zerg"],
        "mmr": pl.Series([1500, 1600], dtype=pl.Int64),
        "player_name": ["Player1", "Player2"],
        "games_played": pl.Series([10, 15], dtype=pl.Int64),
        "games_won": pl.Series([6, 9], dtype=pl.Int64),
        "games_lost": pl.Series([4, 6], dtype=pl.Int64),
        "games_drawn": pl.Series([0, 0], dtype=pl.Int64),
    })


def create_mock_players_df():
    """Create a properly-structured mock players DataFrame."""
    return pl.DataFrame({
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


@pytest.fixture
def initialized_service():
    """Provide an initialized DataAccessService with mock data."""
    service = DataAccessService()
    service._players_df = create_mock_players_df()
    service._mmrs_df = create_mock_mmrs_df()
    service._preferences_df = pl.DataFrame({
        "discord_uid": [1, 2],
        "last_chosen_races": [None, None],
        "last_chosen_vetoes": [None, None],
    })
    service._matches_df = pl.DataFrame({
        "id": pl.Series([], dtype=pl.Int64),
        "player_1_discord_uid": pl.Series([], dtype=pl.Int64),
        "player_2_discord_uid": pl.Series([], dtype=pl.Int64),
        "player_1_race": pl.Series([], dtype=pl.Utf8),
        "player_2_race": pl.Series([], dtype=pl.Utf8),
        "map_played": pl.Series([], dtype=pl.Utf8),
        "server_choice": pl.Series([], dtype=pl.Utf8),
        "player_1_mmr": pl.Series([], dtype=pl.Int64),
        "player_2_mmr": pl.Series([], dtype=pl.Int64),
        "mmr_change": pl.Series([], dtype=pl.Int64),
        "played_at": pl.Series([], dtype=pl.Utf8),
        "player_1_report": pl.Series([], dtype=pl.Int64),
        "player_2_report": pl.Series([], dtype=pl.Int64),
        "match_result": pl.Series([], dtype=pl.Int64),
        "player_1_replay_path": pl.Series([], dtype=pl.Utf8),
        "player_2_replay_path": pl.Series([], dtype=pl.Utf8),
        "player_1_replay_time": pl.Series([], dtype=pl.Float64),
        "player_2_replay_time": pl.Series([], dtype=pl.Float64),
        "status": pl.Series([], dtype=pl.Utf8),
    })
    service._replays_df = pl.DataFrame({
        "id": pl.Series([], dtype=pl.Int64),
        "replay_path": pl.Series([], dtype=pl.Utf8),
    })
    
    service._write_queue = asyncio.Queue()
    service._write_event = asyncio.Event()
    service._shutdown_event = asyncio.Event()
    
    return service


class TestLeaderboardRefreshFlow:
    """Test the event-driven leaderboard cache refresh mechanism."""
    
    @pytest.mark.asyncio
    async def test_leaderboard_service_detects_invalid_cache_and_refreshes(self, initialized_service):
        """
        Verify the complete event-driven cache lifecycle:
        1. First leaderboard request generates and caches the data.
        2. Second request hits the cache, avoiding a data refresh.
        3. An MMR-changing event invalidates the cache in DataAccessService.
        4. Third request detects the invalid cache and triggers a full data refresh.
        """
        # === PHASE 1: Setup Services ===
        data_service = initialized_service
        leaderboard_service = LeaderboardService(data_service=data_service)
        
        # Mark the cache as valid to start, as if a leaderboard was just generated
        data_service.mark_leaderboard_cache_valid()
        assert data_service.is_leaderboard_cache_valid() is True
        
        # === PHASE 2: First Call (Cache Hit - Already Valid) ===
        # Spy on the cache refresh method to ensure it's not called when cache is valid
        with patch.object(data_service._db_reader, 'get_leaderboard_1v1', 
                          wraps=data_service._db_reader.get_leaderboard_1v1) as spy_refresh:
            
            # Act: Request leaderboard data for the first time
            result1 = await leaderboard_service.get_leaderboard_data()
            
            # Assert: Since cache started VALID, no database refresh should occur
            spy_refresh.assert_not_called()
            assert result1 is not None
        
        # === PHASE 3: Verify Cache Is Still Valid ===
        assert data_service.is_leaderboard_cache_valid() is True
        
        # === PHASE 4: Invalidate the Cache ===
        # Simulate a match completion that changes MMR
        await data_service.update_player_mmr(
            discord_uid=1, 
            race="terran", 
            new_mmr=1520
        )
        
        # Assert: The cache is now marked as invalid
        assert data_service.is_leaderboard_cache_valid() is False
        print("[Test] Cache invalidated successfully")
        
        # === PHASE 5: Second Call (Cache Miss & Refresh) ===
        # Mock the database reader to return fresh data when cache is invalid
        mock_leaderboard_data = [
            {'discord_uid': 1, 'race': 'terran', 'mmr': 1520, 'player_name': 'Player1', 
             'games_played': 11, 'games_won': 7, 'games_lost': 4, 'games_drawn': 0},
            {'discord_uid': 2, 'race': 'zerg', 'mmr': 1550, 'player_name': 'Player2',
             'games_played': 12, 'games_won': 7, 'games_lost': 5, 'games_drawn': 0},
        ]
        
        with patch.object(data_service._db_reader, 'get_leaderboard_1v1', 
                          return_value=mock_leaderboard_data) as spy_refresh:
            
            # Act: Request the leaderboard after cache invalidation
            result2 = await leaderboard_service.get_leaderboard_data()
            
            # Assert: The refresh method SHOULD have been called to reload data
            spy_refresh.assert_called_once()
            assert result2 is not None
            print("[Test] Cache refresh was triggered as expected")
        
        # === PHASE 6: Verify Cache Is Valid Again ===
        # After refresh, the cache should be marked as valid
        assert data_service.is_leaderboard_cache_valid() is True
        print("[Test] Cache marked as valid after refresh")
        
        # === PHASE 7: Third Call (Cache Hit Again) ===
        # Now that cache is valid again, it should not refresh on the next call
        with patch.object(data_service._db_reader, 'get_leaderboard_1v1', 
                          wraps=data_service._db_reader.get_leaderboard_1v1) as spy_refresh:
            
            # Act: Request the leaderboard again
            result3 = await leaderboard_service.get_leaderboard_data()
            
            # Assert: No refresh should occur since cache is now valid
            spy_refresh.assert_not_called()
            assert result3 is not None
            print("[Test] Cache hit - no refresh triggered")
