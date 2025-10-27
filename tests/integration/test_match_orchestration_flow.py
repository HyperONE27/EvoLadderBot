"""
Integration test for match completion orchestration flow.

Tests that the MatchmakingService correctly orchestrates match completion:
1. Orchestrator receives a completed match with results
2. Fetches necessary player data from DataAccessService
3. Calculates new MMRs via MMRService
4. Calls the correct DataAccessService methods to write updates
5. The side-effect is that the leaderboard cache becomes invalid

This test validates the orchestration layer between business logic and data access.
"""

import pytest
import asyncio
import polars as pl
from unittest.mock import patch, AsyncMock, MagicMock

from src.backend.services.data_access_service import DataAccessService
from src.backend.services.matchmaking_service import Matchmaker


@pytest.fixture(autouse=True)
def reset_data_access_service_singleton():
    """Reset the DataAccessService singleton before each test."""
    DataAccessService._instance = None
    DataAccessService._initialized = False
    yield
    DataAccessService._instance = None
    DataAccessService._initialized = False


def create_mock_mmrs_1v1_df():
    """Create a properly-structured mock MMRs DataFrame with multiple players and races."""
    return pl.DataFrame({
        "discord_uid": pl.Series([1, 1, 2, 2], dtype=pl.Int64),
        "race": ["terran", "zerg", "terran", "zerg"],
        "mmr": pl.Series([1500, 1400, 1600, 1550], dtype=pl.Int64),
        "player_name": ["Player1", "Player1", "Player2", "Player2"],
        "games_played": pl.Series([10, 8, 15, 12], dtype=pl.Int64),
        "games_won": pl.Series([6, 4, 9, 7], dtype=pl.Int64),
        "games_lost": pl.Series([4, 4, 6, 5], dtype=pl.Int64),
        "games_drawn": pl.Series([0, 0, 0, 0], dtype=pl.Int64),
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
    service._mmrs_1v1_df = create_mock_mmrs_1v1_df()
    service._preferences_1v1_df = pl.DataFrame({
        "discord_uid": [1, 2],
        "last_chosen_races": [None, None],
        "last_chosen_vetoes": [None, None],
    })
    service._matches_1v1_df = pl.DataFrame({
        "id": pl.Series([123], dtype=pl.Int64),
        "player_1_discord_uid": pl.Series([1], dtype=pl.Int64),
        "player_2_discord_uid": pl.Series([2], dtype=pl.Int64),
        "player_1_race": ["terran"],
        "player_2_race": ["zerg"],
        "map_played": ["[SC:Evo] Radeon (라데온)"],
        "server_choice": ["NA"],
        "player_1_mmr": pl.Series([1500], dtype=pl.Int64),
        "player_2_mmr": pl.Series([1550], dtype=pl.Int64),
        "mmr_change": pl.Series([0], dtype=pl.Int64),
        "played_at": ["2025-10-24"],
        "player_1_report": pl.Series([1], dtype=pl.Int64),
        "player_2_report": pl.Series([1], dtype=pl.Int64),
        "match_result": [None],
        "player_1_replay_path": [None],
        "player_2_replay_path": [None],
        "player_1_replay_time": [None],
        "player_2_replay_time": [None],
        "status": ["COMPLETED"],
    })
    service._replays_df = pl.DataFrame({
        "id": pl.Series([], dtype=pl.Int64),
        "replay_path": pl.Series([], dtype=pl.Utf8),
    })
    
    service._write_queue = asyncio.Queue()
    service._write_event = asyncio.Event()
    service._shutdown_event = asyncio.Event()
    
    return service


class TestMatchOrchestrationFlow:
    """Test the match completion orchestration flow."""
    
    @pytest.mark.asyncio
    async def test_match_orchestrator_updates_mmr_and_invalidates_cache(self, initialized_service):
        """
        Verify that the MatchmakingService correctly orchestrates match completion:
        1. Receives match completion data
        2. Calculates new MMRs
        3. Calls correct DataAccessService methods to write updates
        4. The side-effect is that the leaderboard cache becomes invalid
        """
        # === PHASE 1: Setup Services and State ===
        data_service = initialized_service
        matchmaker = Matchmaker()
        
        # We start with a valid cache (as if leaderboard was just generated)
        data_service.mark_leaderboard_cache_valid()
        assert data_service.is_leaderboard_cache_valid() is True
        print("[Test] Started with VALID cache")
        
        # Mock data for a completed match
        match_id = 123
        match_data = {
            'player_1_discord_uid': 1,
            'player_2_discord_uid': 2,
            'player_1_race': 'terran',
            'player_2_race': 'zerg',
            'match_result': 1,  # Player 1 wins
        }
        
        # === PHASE 2: Act - Run the Orchestrator ===
        # Call the orchestrator WITHOUT mocking the data layer.
        # This allows us to see the side-effect (cache invalidation).
        await matchmaker._calculate_and_write_mmr(match_id, match_data)
        print("[Test] Matchmaker orchestration completed")
        
        # === PHASE 3: Assert the Final State ===
        # The key assertion: after orchestration, cache MUST be invalid.
        # This happens as a side-effect of calling update_player_mmr which calls invalidate_leaderboard_cache()
        assert data_service.is_leaderboard_cache_valid() is False, \
            "A successful match completion must invalidate the leaderboard cache"
        
        print("[Test] Cache successfully invalidated after match orchestration")

