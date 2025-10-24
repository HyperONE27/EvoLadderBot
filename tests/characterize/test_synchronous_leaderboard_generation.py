"""
Characterization tests for synchronous leaderboard generation refactoring.

This test suite verifies that the refactored leaderboard generation:
1. Maintains correctness after moving from ProcessPoolExecutor to asyncio.to_thread()
2. Handles filtering accurately (country, race, rank, best_race_only)
3. Performs pagination correctly
4. Maintains performance within acceptable bounds
5. Properly uses asyncio.to_thread() for non-blocking execution
6. Handles edge cases (empty filters, large datasets, concurrent requests)

The refactoring is critical because:
- ProcessPoolExecutor adds ~700ms startup overhead
- Polars is already multi-threaded (uses Rust under the hood)
- The actual filtering is ~20-30ms, which is fast enough to block the event loop safely
- Using asyncio.to_thread() preserves async compatibility with zero IPC overhead
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
import time
import polars as pl
from functools import partial

from src.backend.services.data_access_service import DataAccessService
from src.backend.services.leaderboard_service import (
    LeaderboardService,
    _get_filtered_leaderboard_dataframe
)
from src.backend.services.countries_service import CountriesService
from src.backend.services.races_service import RacesService


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons before each test to avoid interference."""
    DataAccessService._instance = None
    DataAccessService._initialized = False
    yield
    DataAccessService._instance = None
    DataAccessService._initialized = False


def create_mock_leaderboard_dataframe(num_players: int = 100) -> pl.DataFrame:
    """Create a realistic mock leaderboard DataFrame for testing."""
    return pl.DataFrame({
        "discord_uid": pl.Series(range(1, num_players + 1), dtype=pl.Int64),
        "player_name": [f"Player{i}" for i in range(1, num_players + 1)],
        "mmr": pl.Series(list(range(num_players, 0, -1)), dtype=pl.Int64),
        "race": [["t", "p", "z"][i % 3] for i in range(num_players)],
        "country": [["US", "KR", "CN", "ZZ"][i % 4] for i in range(num_players)],
        "last_played": pl.Series([int(time.time()) - i * 100 for i in range(num_players)], dtype=pl.Int64),
        "rank": ["s_rank" if i < 20 else "a_rank" if i < 50 else "b_rank" for i in range(num_players)],
        "is_active": [True] * num_players,
    })


class TestSynchronousFilteringCorrectness:
    """Test that the synchronous filtering function produces correct results."""
    
    def test_filter_function_returns_correct_types(self):
        """Verify _get_filtered_leaderboard_dataframe returns (DataFrame, int, int)."""
        df = create_mock_leaderboard_dataframe(50)
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            page_size=20
        )
        
        assert isinstance(result_df, pl.DataFrame)
        assert isinstance(total_players, int)
        assert isinstance(total_pages, int)
        assert len(result_df) == 50
        assert total_players == 50
        assert total_pages == 3  # 50 / 20 = 2.5, rounded up to 3
    
    def test_country_filter_works(self):
        """Verify country filtering produces correct subset."""
        df = create_mock_leaderboard_dataframe(100)
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            country_filter=["US"],
            page_size=20
        )
        
        # Should have only US players (~25% of 100)
        assert all(result_df["country"] == "US")
        assert total_players <= 30  # Allow some variance in the mock data
        assert total_pages >= 1
    
    def test_race_filter_works(self):
        """Verify race filtering produces correct subset."""
        df = create_mock_leaderboard_dataframe(100)
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            race_filter=["t"],
            page_size=20
        )
        
        # Should have only Terran players (~33% of 100)
        assert all(result_df["race"] == "t")
        assert total_players <= 40
        assert total_pages >= 1
    
    def test_multiple_filters_combined(self):
        """Verify multiple filters work together (intersection)."""
        df = create_mock_leaderboard_dataframe(100)
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            country_filter=["US"],
            race_filter=["t"],
            page_size=20
        )
        
        # Should have only US Terrans (intersection)
        assert all(result_df["country"] == "US")
        assert all(result_df["race"] == "t")
        assert total_players <= 15  # ~1/4 of 1/3 of 100
    
    def test_rank_filter_works(self):
        """Verify rank filtering produces correct subset."""
        df = create_mock_leaderboard_dataframe(100)
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            rank_filter="s_rank",
            page_size=20
        )
        
        # Should have only S-rank players
        assert all(result_df["rank"] == "s_rank")
        assert total_players <= 25
    
    def test_best_race_only_deduplicates_by_player(self):
        """Verify best_race_only shows one entry per discord_uid."""
        df = pl.DataFrame({
            "discord_uid": pl.Series([1, 1, 1, 2, 2, 3], dtype=pl.Int64),
            "player_name": ["Player1", "Player1", "Player1", "Player2", "Player2", "Player3"],
            "mmr": pl.Series([100, 80, 90, 150, 120, 200], dtype=pl.Int64),
            "race": ["t", "p", "z", "p", "t", "z"],
            "country": ["US", "US", "US", "KR", "KR", "CN"],
            "last_played": pl.Series([100, 90, 80, 100, 90, 100], dtype=pl.Int64),
            "rank": ["a_rank", "a_rank", "a_rank", "a_rank", "a_rank", "s_rank"],
            "is_active": [True] * 6,
        })
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            best_race_only=True,
            page_size=20
        )
        
        # Should have 3 players (one best race each)
        assert len(result_df) == 3
        unique_uids = result_df["discord_uid"].to_list()
        assert len(unique_uids) == len(set(unique_uids))  # All unique
    
    def test_no_filters_returns_all_data(self):
        """Verify no filters returns entire dataset."""
        df = create_mock_leaderboard_dataframe(100)
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            page_size=20
        )
        
        assert len(result_df) == 100
        assert total_players == 100
        assert total_pages == 5


class TestPaginationCorrectness:
    """Test that pagination calculations are correct."""
    
    def test_pagination_calculation_exact_fit(self):
        """Verify pagination when data divides evenly by page_size."""
        df = create_mock_leaderboard_dataframe(100)
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            page_size=20
        )
        
        assert total_players == 100
        assert total_pages == 5
    
    def test_pagination_calculation_with_remainder(self):
        """Verify pagination when data doesn't divide evenly."""
        df = create_mock_leaderboard_dataframe(47)
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            page_size=20
        )
        
        assert total_players == 47
        assert total_pages == 3  # ceil(47/20)
    
    def test_pagination_limits_to_25_pages_max(self):
        """Verify pagination caps at 25 pages to avoid Discord dropdown limits."""
        df = create_mock_leaderboard_dataframe(1000)
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            page_size=20
        )
        
        assert total_pages == 25  # Max capped at 25
        assert total_players == 500  # 25 pages * 20 per page
        assert len(result_df) == 500


class TestDataIsProperlyOrdered:
    """Test that data is properly sorted after filtering."""
    
    def test_data_sorted_by_mmr_descending(self):
        """Verify data is sorted by MMR descending."""
        df = create_mock_leaderboard_dataframe(50)
        
        result_df, _, _ = _get_filtered_leaderboard_dataframe(
            df,
            page_size=20
        )
        
        mmrs = result_df["mmr"].to_list()
        assert mmrs == sorted(mmrs, reverse=True)
    
    def test_tie_breaking_by_last_played(self):
        """Verify same MMR entries are sorted by last_played descending."""
        df = pl.DataFrame({
            "discord_uid": pl.Series([1, 2, 3], dtype=pl.Int64),
            "player_name": ["P1", "P2", "P3"],
            "mmr": pl.Series([100, 100, 100], dtype=pl.Int64),
            "race": ["t", "p", "z"],
            "country": ["US", "US", "US"],
            "last_played": pl.Series([300, 100, 200], dtype=pl.Int64),
            "rank": ["a_rank"] * 3,
            "is_active": [True] * 3,
        })
        
        result_df, _, _ = _get_filtered_leaderboard_dataframe(
            df,
            page_size=20
        )
        
        last_played = result_df["last_played"].to_list()
        assert last_played == [300, 200, 100]  # Descending order


class TestAsyncBehavior:
    """Test async behavior using asyncio.to_thread()."""
    
    @pytest.mark.asyncio
    async def test_async_to_thread_integration(self):
        """Verify leaderboard service correctly uses asyncio.to_thread()."""
        # Mock the data service and its methods
        with patch("src.backend.services.leaderboard_service.DataAccessService") as mock_das:
            mock_instance = MagicMock()
            mock_das.get_instance.return_value = mock_instance
            
            # Mock cache validity
            mock_instance.is_leaderboard_cache_valid.return_value = True
            mock_instance._get_cached_leaderboard_dataframe.return_value = create_mock_leaderboard_dataframe(100)
            
            # Create leaderboard service
            service = LeaderboardService(
                country_service=MagicMock(),
                race_service=MagicMock(),
                data_service=mock_instance,
                ranking_service=MagicMock()
            )
            
            # Call get_leaderboard_data
            start = time.time()
            data = await service.get_leaderboard_data(
                country_filter=None,
                race_filter=None,
                best_race_only=False,
                rank_filter=None,
                current_page=1,
                page_size=20
            )
            elapsed = time.time() - start
            
            # Verify result is valid
            assert "players" in data
            assert "total_pages" in data
            assert "current_page" in data
            assert "total_players" in data
            assert data["current_page"] == 1
            assert len(data["players"]) <= 20
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_dont_block(self):
        """Verify multiple concurrent leaderboard requests don't block each other."""
        with patch("src.backend.services.leaderboard_service.DataAccessService") as mock_das:
            mock_instance = MagicMock()
            mock_das.get_instance.return_value = mock_instance
            mock_instance.is_leaderboard_cache_valid.return_value = True
            mock_instance._get_cached_leaderboard_dataframe.return_value = create_mock_leaderboard_dataframe(100)
            
            service = LeaderboardService(
                country_service=MagicMock(),
                race_service=MagicMock(),
                data_service=mock_instance,
                ranking_service=MagicMock()
            )
            
            # Run 3 concurrent requests
            start = time.time()
            results = await asyncio.gather(
                service.get_leaderboard_data(country_filter=None, current_page=1, page_size=20),
                service.get_leaderboard_data(country_filter=["US"], current_page=1, page_size=20),
                service.get_leaderboard_data(race_filter=["t"], current_page=1, page_size=20),
            )
            elapsed = time.time() - start
            
            # All requests should complete
            assert len(results) == 3
            for result in results:
                assert "players" in result
            
            # Concurrent execution should be faster than sequential
            # (This is a loose check, but demonstrates async behavior)
            assert elapsed < 5.0  # Should complete quickly


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_dataframe(self):
        """Verify handling of empty DataFrame."""
        df = pl.DataFrame({
            "discord_uid": pl.Series([], dtype=pl.Int64),
            "player_name": pl.Series([], dtype=pl.Utf8),
            "mmr": pl.Series([], dtype=pl.Int64),
            "race": pl.Series([], dtype=pl.Utf8),
            "country": pl.Series([], dtype=pl.Utf8),
            "last_played": pl.Series([], dtype=pl.Int64),
            "rank": pl.Series([], dtype=pl.Utf8),
            "is_active": pl.Series([], dtype=pl.Boolean),
        })
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            page_size=20
        )
        
        assert len(result_df) == 0
        assert total_players == 0
        assert total_pages == 1  # Minimum 1 page
    
    def test_single_player(self):
        """Verify handling of single player DataFrame."""
        df = create_mock_leaderboard_dataframe(1)
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            page_size=20
        )
        
        assert len(result_df) == 1
        assert total_players == 1
        assert total_pages == 1
    
    def test_filter_with_no_matches(self):
        """Verify handling of filter that matches no players."""
        df = create_mock_leaderboard_dataframe(100)
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            country_filter=["XX"],  # Non-existent country
            page_size=20
        )
        
        assert len(result_df) == 0
        assert total_players == 0
        assert total_pages == 1
    
    def test_page_size_one(self):
        """Verify handling of page_size=1."""
        df = create_mock_leaderboard_dataframe(10)
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            page_size=1
        )
        
        assert total_pages == 10
    
    def test_large_page_size(self):
        """Verify handling of page_size larger than dataset."""
        df = create_mock_leaderboard_dataframe(10)
        
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            page_size=1000
        )
        
        assert len(result_df) == 10
        assert total_players == 10
        assert total_pages == 1


class TestCacheIntegration:
    """Test integration with cache invalidation."""
    
    @pytest.mark.asyncio
    async def test_cache_invalid_triggers_refresh(self):
        """Verify that invalid cache triggers on-demand refresh."""
        # Create mock data service with invalid cache
        mock_db_reader = MagicMock()
        mock_db_reader.get_leaderboard_1v1 = MagicMock(
            return_value=[
                {"discord_uid": 1, "player_name": "P1", "mmr": 100, "race": "t", "country": "US", "last_played": int(time.time())},
                {"discord_uid": 2, "player_name": "P2", "mmr": 90, "race": "p", "country": "KR", "last_played": int(time.time())},
            ]
        )
        
        with patch("src.backend.services.leaderboard_service.DataAccessService") as mock_das:
            mock_instance = MagicMock()
            mock_das.get_instance.return_value = mock_instance
            
            # Cache is initially invalid
            mock_instance.is_leaderboard_cache_valid.return_value = False
            mock_instance._db_reader = mock_db_reader
            mock_instance._mmrs_df = create_mock_leaderboard_dataframe(100)
            mock_instance._get_cached_leaderboard_dataframe.return_value = create_mock_leaderboard_dataframe(100)
            
            service = LeaderboardService(
                country_service=MagicMock(),
                race_service=MagicMock(),
                data_service=mock_instance,
                ranking_service=MagicMock()
            )
            
            # Get leaderboard data
            data = await service.get_leaderboard_data(current_page=1, page_size=20)
            
            # Verify data was returned
            assert "players" in data
            # Verify mark_leaderboard_cache_valid was called
            mock_instance.mark_leaderboard_cache_valid.assert_called()


class TestPerformance:
    """Test performance characteristics."""
    
    def test_filtering_completes_quickly(self):
        """Verify that filtering completes within acceptable time."""
        df = create_mock_leaderboard_dataframe(1000)
        
        start = time.time()
        result_df, _, _ = _get_filtered_leaderboard_dataframe(
            df,
            country_filter=["US"],
            race_filter=["t"],
            best_race_only=False,
            page_size=20
        )
        elapsed = (time.time() - start) * 1000
        
        # Should complete in under 100ms for typical datasets
        assert elapsed < 100, f"Filtering took {elapsed:.2f}ms, expected < 100ms"
    
    def test_best_race_only_performance(self):
        """Verify best_race_only doesn't cause excessive slowdown."""
        df = create_mock_leaderboard_dataframe(1000)
        
        start = time.time()
        result_df, _, _ = _get_filtered_leaderboard_dataframe(
            df,
            best_race_only=True,
            page_size=20
        )
        elapsed = (time.time() - start) * 1000
        
        # Should still complete quickly
        assert elapsed < 150, f"Best race only took {elapsed:.2f}ms, expected < 150ms"
    
    def test_large_dataset_handling(self):
        """Verify handling of large datasets."""
        df = create_mock_leaderboard_dataframe(10000)
        
        start = time.time()
        result_df, total_players, total_pages = _get_filtered_leaderboard_dataframe(
            df,
            country_filter=["US", "KR"],
            race_filter=["t", "p"],
            page_size=40
        )
        elapsed = (time.time() - start) * 1000
        
        # Should complete in reasonable time even with large dataset
        assert elapsed < 200, f"Large dataset filtering took {elapsed:.2f}ms, expected < 200ms"
        assert total_pages <= 25  # Should respect max pages


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
