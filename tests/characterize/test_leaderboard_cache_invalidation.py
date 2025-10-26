"""
Characterization tests for event-driven leaderboard cache invalidation.

This test suite verifies that the leaderboard cache is properly invalidated
whenever ANY MMR-adjusting operation takes place:
  - update_player_mmr()
  - create_or_update_mmr()
  - abort_match()
  - update_match_mmr_change()

The cache invalidation mechanism is critical for:
1. Data freshness: Users see up-to-date leaderboard after match completion
2. Cost optimization: No wasteful 60-second background refresh loop when idle
3. Correctness: Cache never serves stale data during active gameplay
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import time
import polars as pl

from src.backend.services.data_access_service import DataAccessService
from src.backend.services.leaderboard_service import LeaderboardService


@pytest.fixture(autouse=True)
def reset_data_access_service_singleton():
    """Reset the DataAccessService singleton before each test to avoid interference."""
    # Reset the singleton for each test
    DataAccessService._instance = None
    DataAccessService._initialized = False
    yield
    # Clean up after test
    DataAccessService._instance = None
    DataAccessService._initialized = False


class TestCacheInvalidationOnMMRUpdate:
    """Test that cache is invalidated when update_player_mmr is called."""
    
    @pytest.mark.asyncio
    async def test_cache_invalidated_on_mmr_update(self):
        """
        Verify that update_player_mmr() invalidates the leaderboard cache.
        
        Scenario:
        1. Start with cache marked as valid
        2. Call update_player_mmr()
        3. Verify cache is now invalid
        """
        data_service = DataAccessService()
        
        # Ensure service is initialized with mock data
        if data_service._mmrs_1v1_df is None or len(data_service._mmrs_1v1_df) == 0:
            # Create mock MMR data
            data_service._mmrs_1v1_df = pl.DataFrame({
                "discord_uid": [123456789],
                "race": ["sc2_terran"],
                "mmr": [2000],
                "player_name": ["TestPlayer"],
                "games_played": [10],
                "games_won": [6],
                "games_lost": [4],
                "games_drawn": [0],
            })
        
        # Mark cache as valid
        data_service.mark_leaderboard_cache_valid()
        assert data_service.is_leaderboard_cache_valid() is True
        
        # Update MMR - should invalidate cache
        await data_service.update_player_mmr(
            discord_uid=123456789,
            race="sc2_terran",
            new_mmr=2100
        )
        
        # Cache should now be invalid
        assert data_service.is_leaderboard_cache_valid() is False
    
    @pytest.mark.asyncio
    async def test_cache_invalidated_with_game_count_update(self):
        """
        Verify that update_player_mmr() with game count updates invalidates cache.
        
        This tests the common scenario of match completion:
        - MMR changes
        - Game counts are incremented
        Both together should trigger cache invalidation.
        """
        data_service = DataAccessService()
        
        # Setup mock MMR data with ALL required columns
        if data_service._mmrs_1v1_df is None or len(data_service._mmrs_1v1_df) == 0:
            data_service._mmrs_1v1_df = pl.DataFrame({
                "discord_uid": pl.Series([111111111], dtype=pl.Int64),
                "race": ["bw_terran"],
                "mmr": pl.Series([1800], dtype=pl.Int64),
                "player_name": ["BWPlayer"],
                "games_played": pl.Series([20], dtype=pl.Int64),
                "games_won": pl.Series([12], dtype=pl.Int64),
                "games_lost": pl.Series([8], dtype=pl.Int64),
                "games_drawn": pl.Series([0], dtype=pl.Int64),
            })
        
        # Mark cache as valid
        data_service.mark_leaderboard_cache_valid()
        
        # Update with all game count fields
        await data_service.update_player_mmr(
            discord_uid=111111111,
            race="bw_terran",
            new_mmr=1850,
            games_played=21,
            games_won=13,
            games_lost=8,
            games_drawn=0
        )
        
        # Cache should be invalidated
        assert data_service.is_leaderboard_cache_valid() is False


class TestCacheInvalidationOnMMRCreate:
    """Test that cache is invalidated when create_or_update_mmr is called."""
    
    @pytest.mark.asyncio
    async def test_cache_invalidated_on_mmr_create_new_record(self):
        """
        Verify that creating a new MMR record invalidates the cache.
        
        Scenario:
        1. Cache is marked valid
        2. create_or_update_mmr() is called for a new player
        3. Cache should be invalid (new player on leaderboard)
        """
        data_service = DataAccessService()
        
        # Ensure we have a base MMR dataframe
        if data_service._mmrs_1v1_df is None:
            data_service._mmrs_1v1_df = pl.DataFrame({
                "discord_uid": pl.Series([], dtype=pl.Int64),
                "race": pl.Series([], dtype=pl.Utf8),
                "mmr": pl.Series([], dtype=pl.Int64),
                "player_name": pl.Series([], dtype=pl.Utf8),
                "games_played": pl.Series([], dtype=pl.Int64),
                "games_won": pl.Series([], dtype=pl.Int64),
                "games_lost": pl.Series([], dtype=pl.Int64),
                "games_drawn": pl.Series([], dtype=pl.Int64),
            })
        
        # Mark cache as valid
        data_service.mark_leaderboard_cache_valid()
        
        # Create new MMR record
        await data_service.create_or_update_mmr(
            discord_uid=999999999,
            player_name="NewLeaderboardPlayer",
            race="sc2_zerg",
            mmr=2500,
            games_played=5,
            games_won=4,
            games_lost=1,
            games_drawn=0
        )
        
        # Cache should be invalidated (new player added to leaderboard)
        assert data_service.is_leaderboard_cache_valid() is False
    
    @pytest.mark.asyncio
    async def test_cache_invalidated_on_mmr_update_via_create_or_update(self):
        """
        Verify that updating an existing MMR via create_or_update_mmr invalidates cache.
        
        Scenario:
        1. Existing player in database
        2. Cache marked valid
        3. create_or_update_mmr() called to update their MMR
        4. Cache should be invalid
        """
        data_service = DataAccessService()
        
        # Setup existing MMR data
        if data_service._mmrs_1v1_df is None or len(data_service._mmrs_1v1_df) == 0:
            data_service._mmrs_1v1_df = pl.DataFrame({
                "discord_uid": [555555555],
                "race": ["sc2_protoss"],
                "mmr": [1900],
                "player_name": ["ExistingPlayer"],
                "games_played": [15],
                "games_won": [9],
                "games_lost": [6],
                "games_drawn": [0],
            })
        
        # Mark cache as valid
        data_service.mark_leaderboard_cache_valid()
        
        # Update MMR via create_or_update
        await data_service.create_or_update_mmr(
            discord_uid=555555555,
            player_name="ExistingPlayer",
            race="sc2_protoss",
            mmr=1950,  # Changed
            games_played=16,
            games_won=10,
            games_lost=6,
            games_drawn=0
        )
        
        # Cache should be invalidated
        assert data_service.is_leaderboard_cache_valid() is False


class TestCacheInvalidationOnAbort:
    """Test that cache is invalidated when abort_match is called."""
    
    @pytest.mark.asyncio
    async def test_cache_invalidated_on_match_abort(self):
        """
        Verify that abort_match() invalidates the leaderboard cache.
        
        Scenario:
        1. Active match in progress
        2. Cache marked valid
        3. Player aborts the match
        4. Cache should be invalid (abort may affect records/stats)
        """
        data_service = DataAccessService()
        
        # Setup mock data structures
        if data_service._players_df is None:
            data_service._players_df = pl.DataFrame({
                "discord_uid": [777777777, 888888888],
                "discord_username": ["Player1", "Player2"],
                "player_name": ["Player1", "Player2"],
                "country": ["US", "KR"],
                "remaining_aborts": [3, 3],
                "alt_player_name_1": [None, None],
                "alt_player_name_2": [None, None],
            })
        
        if data_service._matches_1v1_df is None:
            data_service._matches_1v1_df = pl.DataFrame({
                "id": [1],
                "player_1_discord_uid": [777777777],
                "player_2_discord_uid": [888888888],
                "player_1_race": ["sc2_terran"],
                "player_2_race": ["sc2_zerg"],
                "map_played": ["Stasis"],
                "server_choice": ["NA"],
                "player_1_mmr": [2000],
                "player_2_mmr": [2000],
                "mmr_change": [0.0],
                "played_at": ["2025-01-01T12:00:00Z"],
                "player_1_report": [0],
                "player_2_report": [0],
                "match_result": [0],  # Not completed yet
                "player_1_replay_path": [None],
                "player_2_replay_path": [None],
                "player_1_replay_time": [None],
                "player_2_replay_time": [None],
                "status": ["IN_PROGRESS"],
            })
        
        # Mark cache as valid
        data_service.mark_leaderboard_cache_valid()
        
        # Abort the match
        await data_service.abort_match(
            match_id=1,
            player_discord_uid=777777777
        )
        
        # Cache should be invalidated
        assert data_service.is_leaderboard_cache_valid() is False


class TestCacheInvalidationOnMatchMMRChange:
    """Test that cache is invalidated when match MMR changes are recorded."""
    
    @pytest.mark.asyncio
    async def test_cache_invalidated_on_match_mmr_change(self):
        """
        Verify that update_match_mmr_change() invalidates the cache.
        
        Scenario:
        1. Match completes with MMR changes
        2. Cache marked valid
        3. update_match_mmr_change() called to record changes
        4. Cache should be invalid (MMR values changed)
        """
        data_service = DataAccessService()
        
        # Mark cache as valid
        data_service.mark_leaderboard_cache_valid()
        
        # Record MMR change for a match
        await data_service.update_match_mmr_change(
            match_id=100,
            mmr_change=45  # Player 1 gained 45 MMR
        )
        
        # Cache should be invalidated
        assert data_service.is_leaderboard_cache_valid() is False


class TestCacheInvalidationNoFalsePositives:
    """Test that cache invalidation doesn't occur for non-MMR operations."""
    
    @pytest.mark.asyncio
    async def test_cache_invalidated_on_player_info_update(self):
        """
        Verify that updating player info (name, country, etc.) DOES invalidate cache.
        
        Although this doesn't change MMR, it changes the data displayed on the leaderboard,
        so the cache must be invalidated to reflect the new name/country.
        """
        data_service = DataAccessService()
        
        # Setup player data
        if data_service._players_df is None:
            data_service._players_df = pl.DataFrame({
                "discord_uid": [123456789],
                "discord_username": ["OldName"],
                "player_name": ["OldName"],
                "country": ["US"],
                "remaining_aborts": [3],
                "alt_player_name_1": [None],
                "alt_player_name_2": [None],
            })
        
        # Mark cache as valid
        data_service.mark_leaderboard_cache_valid()
        
        # Update player info (non-MMR)
        await data_service.update_player_info(
            discord_uid=123456789,
            player_name="NewName"
        )
        
        # Cache should now be INVALID
        assert data_service.is_leaderboard_cache_valid() is False


class TestCacheRefreshOnDemand:
    """Test that on-demand cache refresh works in leaderboard service."""
    
    @pytest.mark.asyncio
    async def test_leaderboard_detects_invalid_cache_and_refreshes(self):
        """
        Integration test: Verify that LeaderboardService detects invalid cache
        and performs on-demand refresh before returning data.
        
        Scenario:
        1. Leaderboard cache is invalid
        2. get_leaderboard_data() is called
        3. Service detects invalid cache
        4. Performs on-demand database refresh
        5. Returns fresh data
        """
        data_service = DataAccessService()
        leaderboard_service = LeaderboardService(data_service=data_service)
        
        # Setup initial data
        if data_service._mmrs_1v1_df is None:
            data_service._mmrs_1v1_df = pl.DataFrame({
                "discord_uid": [123456789],
                "race": ["sc2_terran"],
                "mmr": [2000],
                "player_name": ["TestPlayer"],
                "games_played": [10],
                "games_won": [6],
                "games_lost": [4],
                "games_drawn": [0],
            })
        
        if data_service._players_df is None:
            data_service._players_df = pl.DataFrame({
                "discord_uid": [123456789],
                "discord_username": ["TestPlayer"],
                "player_name": ["TestPlayer"],
                "country": ["US"],
                "remaining_aborts": [3],
                "alt_player_name_1": [None],
                "alt_player_name_2": [None],
            })
        
        # Mark cache as invalid (simulating a cache invalidation event)
        data_service.invalidate_leaderboard_cache()
        assert data_service.is_leaderboard_cache_valid() is False
        
        # Mock the database reader to track refresh calls
        original_get_lb = data_service._db_reader.get_leaderboard_1v1
        call_count = {'count': 0}
        
        def mock_get_leaderboard(*args, **kwargs):
            # NOTE: This must be synchronous - it's called via run_in_executor()
            call_count['count'] += 1
            # Return fresh data
            return [
                {
                    "discord_uid": 123456789,
                    "race": "sc2_terran",
                    "mmr": 2100,  # Updated MMR
                    "player_name": "TestPlayer",
                    "games_played": 11,
                    "games_won": 7,
                    "games_lost": 4,
                    "games_drawn": 0,
                }
            ]
        
        with patch.object(data_service._db_reader, 'get_leaderboard_1v1', side_effect=mock_get_leaderboard):
            # Call get_leaderboard_data
            result = await leaderboard_service.get_leaderboard_data()
        
        # Verify refresh was called (on-demand refresh triggered)
        assert call_count['count'] >= 1, "Should call database refresh when cache invalid"
        
        # Verify cache is now marked valid
        assert data_service.is_leaderboard_cache_valid() is True
        
        # Verify we got data back
        assert result is not None
        assert 'players' in result or isinstance(result, dict)


class TestCacheInvalidationConcurrency:
    """Test that cache invalidation is thread-safe and handles concurrent operations."""
    
    @pytest.mark.asyncio
    async def test_concurrent_mmr_updates_all_invalidate_cache(self):
        """
        Verify that multiple concurrent MMR updates all trigger cache invalidation.
        
        Scenario:
        1. Start with valid cache
        2. Multiple players' MMRs are updated concurrently
        3. Cache should be invalid after all updates complete
        """
        data_service = DataAccessService()
        
        # Setup base MMR data for multiple players with explicit dtypes
        if data_service._mmrs_1v1_df is None or len(data_service._mmrs_1v1_df) == 0:
            data_service._mmrs_1v1_df = pl.DataFrame({
                "discord_uid": pl.Series([111111111, 222222222, 333333333], dtype=pl.Int64),
                "race": ["sc2_terran", "sc2_zerg", "sc2_protoss"],
                "mmr": pl.Series([2000, 1900, 2100], dtype=pl.Int64),
                "player_name": ["Player1", "Player2", "Player3"],
                "games_played": pl.Series([10, 10, 10], dtype=pl.Int64),
                "games_won": pl.Series([6, 5, 7], dtype=pl.Int64),
                "games_lost": pl.Series([4, 5, 3], dtype=pl.Int64),
                "games_drawn": pl.Series([0, 0, 0], dtype=pl.Int64),
            })
        
        # Mark cache as valid
        data_service.mark_leaderboard_cache_valid()
        
        # Concurrent MMR updates
        await asyncio.gather(
            data_service.update_player_mmr(111111111, "sc2_terran", 2050),
            data_service.update_player_mmr(222222222, "sc2_zerg", 1950),
            data_service.update_player_mmr(333333333, "sc2_protoss", 2150),
        )
        
        # Cache should be invalid (at least one update invalidated it)
        assert data_service.is_leaderboard_cache_valid() is False
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_is_idempotent(self):
        """
        Verify that calling invalidate_leaderboard_cache() multiple times is safe.
        
        Calling invalidate() 10 times should have the same effect as calling it once.
        """
        data_service = DataAccessService()
        
        # Mark cache as valid
        data_service.mark_leaderboard_cache_valid()
        assert data_service.is_leaderboard_cache_valid() is True
        
        # Invalidate multiple times
        for _ in range(10):
            data_service.invalidate_leaderboard_cache()
        
        # Should still be invalid
        assert data_service.is_leaderboard_cache_valid() is False
        
        # Should be safe to mark valid after multiple invalidations
        data_service.mark_leaderboard_cache_valid()
        assert data_service.is_leaderboard_cache_valid() is True

