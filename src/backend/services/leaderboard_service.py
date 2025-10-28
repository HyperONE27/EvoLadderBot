"""
Leaderboard service.

This module defines the LeaderboardService class, which contains methods for:
- Retrieving leaderboard data from the database
- Filtering the leaderboard based on provided criteria
- Returning the leaderboard data in a formatted manner
- STATELESS: No mutable state stored to prevent race conditions between users

Intended usage:
    from backend.services.leaderboard_service import LeaderboardService

    leaderboard = LeaderboardService()
    data = await leaderboard.get_leaderboard_data(
        country_filter=['US', 'KR'],
        race_filter=['sc2_terran'],
        current_page=1,
        page_size=40
    )
"""

import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import pickle
import asyncio

import polars as pl

from src.backend.services.data_access_service import DataAccessService
from src.backend.services.countries_service import CountriesService
from src.backend.services.races_service import RacesService

if TYPE_CHECKING:
    from src.backend.services.ranking_service import RankingService


# Global cache removed - DataAccessService handles this now

# Cache for non-common country codes (still used)
_non_common_countries_cache = None


def _get_filtered_leaderboard_dataframe(
    df: pl.DataFrame,
    country_filter: Optional[List[str]] = None,
    race_filter: Optional[List[str]] = None,
    best_race_only: bool = False,
    rank_filter: Optional[str] = None,
    page_size: int = 20
) -> tuple[pl.DataFrame, int, int, int]:
    """
    Synchronous function that performs Polars filtering and sorting.
    
    This function contains all the CPU-bound Polars operations and is
    designed to be called via asyncio.to_thread() from an async context.
    
    Args:
        df: The leaderboard DataFrame with all player data
        country_filter: List of country codes to filter by (None = all)
        race_filter: List of race codes to filter by (None = all)
        best_race_only: If True, show only best race per player
        rank_filter: Rank to filter by (e.g., "s_rank", "a_rank", None = all)
        page_size: Number of items per page
    
    Returns:
        Tuple of (filtered_df, total_players, total_pages, true_total_players)
    """
    perf_start = time.time()
    
    # FIRST: Apply best_race_only filter if enabled
    # This MUST happen BEFORE other filters to ensure correct rank distribution
    # when the rank filter is subsequently applied
    if best_race_only:
        # Group by discord_uid and keep only the highest MMR entry (their best race)
        # Sort first, then group and take first (highest MMR per player)
        df = (df
            .sort(["mmr", "last_played"], descending=[True, True])
            .group_by("discord_uid", maintain_order=True)
            .first()
        )
    
    perf_best_race = time.time()
    best_race_time = (perf_best_race - perf_start) * 1000 if best_race_only else 0
    
    # THEN: Apply other filters (country, race, rank)
    # Build filter conditions and apply them in one operation for better performance
    filter_conditions = []
    
    if country_filter:
        # If ZZ ("Other") is selected, expand it to all non-common countries
        # Cache this expansion to avoid recomputing
        global _non_common_countries_cache
        filter_countries = country_filter.copy()
        if "ZZ" in filter_countries:
            filter_countries.remove("ZZ")
            if _non_common_countries_cache is None:
                from src.backend.services.countries_service import CountriesService
                _non_common_countries_cache = CountriesService().get_all_non_common_country_codes()
            filter_countries.extend(_non_common_countries_cache)
        
        # Optimize: Use is_in with sorted list for better performance
        if len(filter_countries) > 10:
            # Sort the list to help Polars optimize the lookup
            filter_countries = sorted(filter_countries)
        
        filter_conditions.append(pl.col("country").is_in(filter_countries))
    
    if race_filter:
        # Optimize: Use is_in with sorted list for better performance
        if len(race_filter) > 5:
            # Sort the list to help Polars optimize the lookup
            race_filter = sorted(race_filter)
        
        filter_conditions.append(pl.col("race").is_in(race_filter))
    
    if rank_filter:
        # Filter by specific rank (e.g., "s_rank", "a_rank")
        filter_conditions.append(pl.col("rank") == rank_filter)
    
    # Always exclude unranked players (u_rank) from leaderboard display
    # Unranked players are stored but only shown in /profile and /queue
    filter_conditions.append(pl.col("rank") != "u_rank")
    
    # Apply all filters at once using Polars' optimized all_horizontal combinator
    # This is fully vectorized and more efficient than manually combining with &
    if filter_conditions:
        df = df.filter(pl.all_horizontal(filter_conditions))
    
    perf_filter = time.time()
    filter_time = (perf_filter - perf_best_race) * 1000
    
    # Sort by MMR (descending), then by last_played (descending) for tie-breaking
    # Only sort if we didn't just do best_race_only (which already sorted)
    if not best_race_only:
        df = df.sort(["mmr", "last_played"], descending=[True, True])
    # Note: If best_race_only was enabled, data is already sorted from groupby operation
    
    perf_sort = time.time()
    sort_time = (perf_sort - perf_filter) * 1000
    
    # Calculate pagination
    true_total_players = len(df)  # Store true count before limiting
    total_players = true_total_players
    total_pages = max(1, (total_players + page_size - 1) // page_size)
    
    # Limit to 25 pages to avoid Discord dropdown limits
    max_pages = 25
    if total_pages > max_pages:
        total_pages = max_pages
        max_players = max_pages * page_size
        df = df.head(max_players)
        total_players = max_players
    
    perf_end = time.time()
    total_filter_time = (perf_end - perf_start) * 1000
    
    # Compact performance logging
    if best_race_only:
        print(f"[LB-Filter] BestRace:{best_race_time:.1f}ms Filter:{filter_time:.1f}ms Sort:{sort_time:.1f}ms | Total:{total_filter_time:.1f}ms")
    else:
        print(f"[LB-Filter] Filter:{filter_time:.1f}ms Sort:{sort_time:.1f}ms | Total:{total_filter_time:.1f}ms")
    
    return df, total_players, total_pages, true_total_players


class LeaderboardService:
    """
    STATELESS service for handling leaderboard data operations.
    
    All filter state is passed as parameters to prevent race conditions between users.
    """

    def __init__(
        self,
        *,
        country_service: Optional[CountriesService] = None,
        race_service: Optional[RacesService] = None,
        data_service: Optional[DataAccessService] = None,
        ranking_service: Optional["RankingService"] = None,
    ) -> None:
        # Services (stateless)
        self.country_service = country_service or CountriesService()
        self.race_service = race_service or RacesService()
        self.data_service = data_service or DataAccessService()
        
        # Ranking service (will be set after initialization if not provided)
        self._ranking_service = ranking_service
    
    @property
    def ranking_service(self) -> "RankingService":
        """Get ranking service, lazily importing if not provided during init."""
        if self._ranking_service is None:
            from src.backend.services.app_context import ranking_service
            self._ranking_service = ranking_service
        return self._ranking_service
    
    def _get_cached_leaderboard_dataframe(self) -> pl.DataFrame:
        """
        Get leaderboard data as a Polars DataFrame from DataAccessService.
        
        DataAccessService is now the single source of truth - no caching needed.
        All data is already in memory and up-to-date.
        
        Returns:
            Polars DataFrame with all player data including ranks
        """
        # Get data directly from DataAccessService (in-memory, always current)
        df = self.data_service.get_leaderboard_dataframe()
        
        # Add rank column using RankingService
        # Use a more efficient approach: create rank list and add as column
        ranks = []
        global_ranks = []
        for row in df.iter_rows(named=True):
            discord_uid = row.get('discord_uid')
            race = row.get('race')
            if discord_uid and race:
                letter_rank = self.ranking_service.get_letter_rank(discord_uid, race)
                global_rank = self.ranking_service.get_global_rank(discord_uid, race)
                ranks.append(letter_rank if letter_rank else "unranked")
                global_ranks.append(global_rank)
            else:
                ranks.append("unranked")
                global_ranks.append(-1)
        
        # Add both rank columns to existing DataFrame
        df = df.with_columns([
            pl.Series("rank", ranks, dtype=pl.Utf8),
            pl.Series("global_rank", global_ranks, dtype=pl.Int64)
        ])
        
        return df
    
    # _get_cached_leaderboard_dataframe_async() removed - DataAccessService handles this now
    
    async def get_leaderboard_data(
        self,
        *,
        country_filter: Optional[List[str]] = None,
        race_filter: Optional[List[str]] = None,
        best_race_only: bool = False,
        rank_filter: Optional[str] = None,
        current_page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        Get leaderboard data with filters applied.
        
        STATELESS: All filter state is passed as parameters to prevent race conditions.
        
        Now fully synchronous Polars filtering called via asyncio.to_thread().
        This eliminates the overhead of process pool startup (~700ms) while
        maintaining full async compatibility. The filtering is fast enough
        (~20-30ms) that the 30ms event loop block is imperceptible.
        
        Args:
            country_filter: List of country codes to filter by (None = all)
            race_filter: List of race codes to filter by (None = all)
            best_race_only: If True, show only best race per player
            rank_filter: Rank to filter by (e.g., "s_rank", "a_rank", None = all)
            current_page: Page number (1-indexed)
            page_size: Number of items per page
        
        Returns:
            Dictionary containing players, pagination info, and totals
        """
        perf_start = time.time()
        
        # Get DataFrame directly from DataAccessService (single source of truth)
        # DataAccessService provides data directly from memory
        df = self._get_cached_leaderboard_dataframe()
        
        perf_cache = time.time()
        cache_time = (perf_cache - perf_start) * 1000
        
        # Run synchronous Polars filtering via asyncio.to_thread()
        # This allows the filtering to happen without blocking the event loop
        # while keeping the code simple and leveraging Polars' internal parallelism
        loop = asyncio.get_running_loop()
        filtered_df, total_players, total_pages, true_total_players = await loop.run_in_executor(
            None,  # Use default executor (ThreadPoolExecutor)
            _get_filtered_leaderboard_dataframe,
            df,
            country_filter,
            race_filter,
            best_race_only,
            rank_filter,
            page_size
        )
        
        perf_filter = time.time()
        filter_time = (perf_filter - perf_cache) * 1000
        
        # Get page data (zero-copy slicing)
        start_idx = (current_page - 1) * page_size
        page_df = filtered_df.slice(start_idx, page_size)
        
        perf_slice = time.time()
        slice_time = (perf_slice - perf_filter) * 1000
        
        # Convert back to list of dicts for compatibility
        page_players = page_df.to_dicts()
        
        perf_to_dicts = time.time()
        dicts_time = (perf_to_dicts - perf_slice) * 1000
        total_time = (perf_to_dicts - perf_start) * 1000
        
        # Compact performance logging
        print(f"[LB] Cache:{cache_time:.1f}ms Filter:{filter_time:.1f}ms Slice:{slice_time:.1f}ms Dicts:{dicts_time:.1f}ms | Total:{total_time:.1f}ms")
        
        return {
            "players": page_players,
            "total_pages": total_pages,
            "current_page": current_page,
            "total_players": total_players,
            "true_total_players": true_total_players
        }
    
    def get_button_states(self, current_page: int, total_pages: int) -> Dict[str, bool]:
        """Get button states based on current page and total pages."""
        return {
            "previous_disabled": current_page <= 1,
            "next_disabled": current_page >= total_pages,
            "best_race_only_disabled": False
        }
    
    def get_filter_info(
        self,
        *,
        race_filter: Optional[List[str]] = None,
        country_filter: Optional[List[str]] = None,
        best_race_only: bool = False
    ) -> Dict[str, Any]:
        """Get filter information as structured data."""
        filter_info = {
            "race_filter": race_filter,
            "country_filter": country_filter,
            "best_race_only": best_race_only
        }
        
        # Add formatted race names if race filter is active
        if race_filter:
            if isinstance(race_filter, list):
                race_order = self.race_service.get_race_order()
                ordered_races = [race for race in race_order if race in race_filter]
                filter_info["race_names"] = [self.race_service.format_race_name(race) for race in ordered_races]
            else:
                filter_info["race_names"] = [self.race_service.format_race_name(race_filter)]
        
        # Add formatted country names if country filter is active
        if country_filter:
            country_names = self.country_service.get_ordered_country_names(country_filter)
            filter_info["country_names"] = country_names
        
        return filter_info
    
    def get_leaderboard_data_formatted(
        self,
        players: List[Dict],
        current_page: int,
        page_size: int = 20
    ) -> List[Dict[str, Any]]:
        """Get leaderboard data formatted for display."""
        perf_start = time.time()
        
        if not players:
            return []
        
        formatted_players = []
        for player in players:
            # Use the pre-calculated global_rank instead of calculating temporary rank
            global_rank = player.get('global_rank', -1)
            mmr_value = player.get('mmr', 0)
            mmr_display = int(round(mmr_value)) if isinstance(mmr_value, (int, float)) else 0
            
            formatted_players.append({
                "rank": global_rank,  # Now uses the pre-calculated global rank
                "player_name": player['player_name'],
                "mmr": mmr_display,
                "race": self.race_service.format_race_name(player['race']),
                "race_code": player['race'],
                "country": player['country'],
                "mmr_rank": player['rank']
            })
        
        perf_end = time.time()
        print(f"[Format Players] Formatted {len(formatted_players)} players in {(perf_end - perf_start)*1000:.2f}ms")
        
        return formatted_players
    
    def get_pagination_info(self, current_page: int, total_pages: int, total_players: int) -> Dict[str, Any]:
        """Get pagination information as structured data."""
        return {
            "current_page": current_page,
            "total_pages": total_pages,
            "total_players": total_players
        }
    
    # get_player_mmr_from_cache() removed - use DataAccessService.get_player_mmr() directly
    
    # get_player_info_from_cache() removed - use DataAccessService.get_player_info() directly
    
    # get_player_all_mmrs_from_cache() removed - use DataAccessService.get_all_player_mmrs() directly
    
    @staticmethod
    def invalidate_cache():
        """Invalidate leaderboard cache - now handled by DataAccessService."""
        # DataAccessService handles cache invalidation automatically
        pass
