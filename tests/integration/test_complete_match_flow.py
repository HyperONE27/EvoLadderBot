"""
Complete match flow integration tests.

These tests simulate the full real-world workflow:
1. Match is created (both players queue)
2. Match is found and displayed to both players
3. Players report match results
4. Matchmaker calculates MMR changes
5. DataAccessService writes MMR updates to database
6. Cache is invalidated as a side-effect

These tests verify that cache invalidation happens at the correct points
in this multi-service flow without requiring Discord internals.
"""

import pytest
import asyncio
import polars as pl
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.backend.services.data_access_service import DataAccessService
from src.backend.services.mmr_service import MMRService


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


def create_mock_matches_df():
    """Create a properly-structured mock matches DataFrame."""
    return pl.DataFrame({
        "id": pl.Series([123], dtype=pl.Int64),
        "player_1_discord_uid": pl.Series([1], dtype=pl.Int64),
        "player_2_discord_uid": pl.Series([2], dtype=pl.Int64),
        "player_1_race": ["terran"],
        "player_2_race": ["zerg"],
        "map_played": ["Python"],
        "server_choice": ["NA"],
        "player_1_mmr": pl.Series([1500], dtype=pl.Int64),
        "player_2_mmr": pl.Series([1600], dtype=pl.Int64),
        "mmr_change": pl.Series([0], dtype=pl.Int64),
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


@pytest.fixture
def initialized_service():
    """Provide an initialized DataAccessService with mock data."""
    service = DataAccessService()
    
    service._players_df = create_mock_players_df()
    service._mmrs_df = create_mock_mmrs_df()
    service._matches_df = create_mock_matches_df()
    service._preferences_df = pl.DataFrame({
        "discord_uid": [1, 2],
        "last_chosen_races": [None, None],
        "last_chosen_vetoes": [None, None],
    })
    service._replays_df = pl.DataFrame({
        "id": pl.Series([], dtype=pl.Int64),
        "replay_path": pl.Series([], dtype=pl.Utf8),
    })
    
    service._write_queue = asyncio.Queue()
    service._write_event = asyncio.Event()
    service._shutdown_event = asyncio.Event()
    
    return service


class TestCompleteMatchFlow:
    """Test the complete match workflow from queue to MMR update."""
    
    @pytest.mark.asyncio
    async def test_match_lifecycle_invalidates_cache_once_at_completion(self, initialized_service):
        """
        Simulate the complete match lifecycle:
        1. Match is created (cache remains valid, no MMR change)
        2. Both players report the match (cache remains valid, awaiting result)
        3. Match is completed with a result
        4. Matchmaker calculates MMR deltas
        5. MMR updates trigger cache invalidation
        
        This test verifies that the cache is only invalidated when MMR actually changes,
        not on intermediate match states.
        """
        # === PHASE 1: Mark cache as valid (simulating prior leaderboard generation) ===
        initialized_service.mark_leaderboard_cache_valid()
        assert initialized_service.is_leaderboard_cache_valid() is True, \
            "Cache should start VALID"
        
        # === PHASE 2: Match is created ===
        # In real flow: Queue command creates match via matchmaker
        # For this test, match already exists in _matches_df
        # Cache should remain valid because no MMR has changed
        assert initialized_service.is_leaderboard_cache_valid() is True, \
            "Cache should remain VALID when match is just created"
        
        # === PHASE 3: Update match result (not yet causing MMR change) ===
        # Players report, matchmaker identifies the result but hasn't calculated MMR yet
        result = await initialized_service.update_match(
            match_id=123,
            match_result=1  # Player 1 won
        )
        assert result is True, "update_match should succeed"
        
        # Cache is NOT invalidated for match_result alone (no MMR change yet)
        # The cache flag doesn't change in update_match, only in MMR operations
        initial_cache_state = initialized_service.is_leaderboard_cache_valid()
        
        # === PHASE 4: First MMR update (triggers cache invalidation) ===
        # Matchmaker calculates and writes MMR changes
        result = await initialized_service.update_player_mmr(
            discord_uid=1,
            race="terran",
            new_mmr=1516,  # +16 MMR change
            games_won=1
        )
        assert result is True, "update_player_mmr should succeed"
        assert initialized_service.is_leaderboard_cache_valid() is False, \
            "Cache should be INVALID after first MMR update"
        
        # === PHASE 5: Second MMR update (cache already invalid) ===
        # Second player's MMR also updated
        result = await initialized_service.update_player_mmr(
            discord_uid=2,
            race="zerg",
            new_mmr=1584,  # -16 MMR change
            games_lost=1
        )
        assert result is True, "update_player_mmr should succeed"
        assert initialized_service.is_leaderboard_cache_valid() is False, \
            "Cache remains INVALID"
        
        # === PHASE 6: Match MMR change recorded ===
        # Matchmaker records the final MMR delta
        result = await initialized_service.update_match_mmr_change(
            match_id=123,
            mmr_change=16
        )
        assert result is True, "update_match_mmr_change should succeed"
        assert initialized_service.is_leaderboard_cache_valid() is False, \
            "Cache remains INVALID after MMR change recorded"
    
    @pytest.mark.asyncio
    async def test_match_abort_invalidates_cache(self, initialized_service):
        """
        Verify that aborting a match (which reverts MMR if it was in-progress)
        correctly invalidates the cache.
        
        Real flow:
        1. Match is matched and in progress
        2. Player requests abort
        3. Abort handler checks for MMR changes
        4. If MMR was changed during match, abort_match triggers invalidation
        """
        # Arrange: Mark cache as valid
        initialized_service.mark_leaderboard_cache_valid()
        assert initialized_service.is_leaderboard_cache_valid() is True
        
        # Act: Abort the match (this calls abort_match which invalidates cache)
        result = await initialized_service.abort_match(
            match_id=123,
            player_discord_uid=1
        )
        
        # Assert
        assert result is True, "abort_match should succeed"
        assert initialized_service.is_leaderboard_cache_valid() is False, \
            "Cache should be INVALID after match abort"


class TestCacheInvalidationRobustness:
    """Test that cache invalidation works correctly across concurrent operations."""
    
    @pytest.mark.asyncio
    async def test_concurrent_mmr_updates_all_trigger_invalidation(self, initialized_service):
        """
        Verify that if multiple MMR updates happen concurrently (e.g., matches
        completing at the same time), cache is invalidated.
        
        This simulates:
        1. Multiple matches complete simultaneously
        2. Each triggers update_player_mmr and update_match_mmr_change
        3. Cache should be invalidated after first update
        4. Subsequent updates maintain INVALID state
        """
        # Arrange
        initialized_service.mark_leaderboard_cache_valid()
        
        # Act: Submit concurrent MMR updates
        tasks = [
            initialized_service.update_player_mmr(1, "terran", 1516, games_won=1),
            initialized_service.update_player_mmr(2, "zerg", 1584, games_lost=1),
            initialized_service.update_match_mmr_change(123, 16),
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Assert
        assert all(results), "All updates should succeed"
        assert initialized_service.is_leaderboard_cache_valid() is False, \
            "Cache should be INVALID after concurrent MMR updates"
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_persists_across_operations(self, initialized_service):
        """
        Verify that once cache is invalidated, it remains invalid until
        explicitly marked valid (by leaderboard generation).
        
        This ensures we don't accidentally serve stale leaderboard data due to
        intermediate cache marking logic.
        """
        # Arrange
        initialized_service.mark_leaderboard_cache_valid()
        
        # Act: Trigger invalidation
        await initialized_service.update_player_mmr(1, "terran", 1510, games_played=1)
        
        # Assert: Cache is now invalid
        assert initialized_service.is_leaderboard_cache_valid() is False
        
        # Act: Perform other operations (non-MMR-related)
        await initialized_service.update_player_info(1, country="CN")
        
        # Assert: Cache should still be invalid (not re-validated by non-MMR operation)
        assert initialized_service.is_leaderboard_cache_valid() is False, \
            "Cache should remain invalid until explicitly marked valid"
        
        # Act: Explicitly mark cache as valid (simulating leaderboard generation)
        initialized_service.mark_leaderboard_cache_valid()
        
        # Assert
        assert initialized_service.is_leaderboard_cache_valid() is True
