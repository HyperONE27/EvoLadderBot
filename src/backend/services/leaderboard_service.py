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

from typing import Any, Dict, List, Optional, TYPE_CHECKING
from functools import lru_cache
import time
import polars as pl

from src.backend.services.countries_service import CountriesService
from src.backend.services.races_service import RacesService
from src.backend.db.db_reader_writer import DatabaseReader

if TYPE_CHECKING:
    from src.backend.services.ranking_service import RankingService


# Global cache for leaderboard data with timestamp
_leaderboard_cache = {
    "data": None,
    "dataframe": None,  # Store as Polars DataFrame for fast filtering
    "timestamp": 0,
    "ttl": 60  # Cache for 60 seconds
}

# Cache for non-common country codes
_non_common_countries_cache = None


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
        db_reader: Optional[DatabaseReader] = None,
        ranking_service: Optional["RankingService"] = None,
    ) -> None:
        # Services (stateless)
        self.country_service = country_service or CountriesService()
        self.race_service = race_service or RacesService()
        self.db_reader = db_reader or DatabaseReader()
        
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
        Get leaderboard data as a Polars DataFrame from cache or database.
        
        Cache is global and shared across all LeaderboardService instances.
        This dramatically reduces database load and includes pre-computed ranks.
        
        Returns:
            Polars DataFrame with all player data including ranks
        """
        current_time = time.time()
        
        # Check if cache is valid
        if (_leaderboard_cache["dataframe"] is not None and 
            current_time - _leaderboard_cache["timestamp"] < _leaderboard_cache["ttl"]):
            print(f"[Leaderboard Cache] HIT - Age: {current_time - _leaderboard_cache['timestamp']:.1f}s")
            return _leaderboard_cache["dataframe"]
        
        # Cache miss or expired - fetch from database
        print("[Leaderboard Cache] MISS - Fetching from database...")
        all_players = []
        
        # Get all players regardless of race
        all_players = self.db_reader.get_leaderboard_1v1(limit=10000)
        
        # Refresh rankings FIRST before processing players
        print("[Leaderboard Cache] Refreshing rankings...")
        self.ranking_service.refresh_rankings()
        
        # Convert database format to expected format and add rank information
        # Do this ONCE during cache refresh, not on every page view
        formatted_players = []
        for player in all_players:
            discord_uid = player.get("discord_uid")
            race = player.get("race", "Unknown")
            
            # Get rank from ranking service (pre-computed during refresh above)
            rank = "u_rank"  # Default to unranked
            if discord_uid is not None and race != "Unknown":
                rank = self.ranking_service.get_rank(discord_uid, race)
            
            formatted_players.append({
                "player_id": player.get("player_name", "Unknown"),
                "mmr": player.get("mmr", 0),
                "race": race,
                "country": player.get("country", "Unknown"),
                "discord_uid": discord_uid,
                "rank": rank
            })
        
        # Convert to DataFrame ONCE and cache it
        df = pl.DataFrame(formatted_players)
        
        # Update cache
        _leaderboard_cache["data"] = all_players  # Keep for backward compatibility
        _leaderboard_cache["dataframe"] = df
        _leaderboard_cache["timestamp"] = current_time
        print(f"[Leaderboard Cache] Updated - Cached {len(all_players)} players as DataFrame")
        
        return df
    
    async def get_leaderboard_data(
        self,
        *,
        country_filter: Optional[List[str]] = None,
        race_filter: Optional[List[str]] = None,
        best_race_only: bool = False,
        current_page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        Get leaderboard data with filters applied.
        
        STATELESS: All filter state is passed as parameters to prevent race conditions.
        
        Args:
            country_filter: List of country codes to filter by (None = all)
            race_filter: List of race codes to filter by (None = all)
            best_race_only: If True, show only best race per player
            current_page: Page number (1-indexed)
            page_size: Number of items per page
        
        Returns:
            Dictionary containing players, pagination info, and totals
        """
        # Get cached DataFrame (already has ranks computed)
        df = self._get_cached_leaderboard_dataframe()
        
        # Apply filters (multi-threaded, much faster than list comprehensions)
        if country_filter:
            # If ZZ ("Other") is selected, expand it to all non-common countries
            # Cache this expansion to avoid recomputing
            global _non_common_countries_cache
            filter_countries = country_filter.copy()
            if "ZZ" in filter_countries:
                filter_countries.remove("ZZ")
                if _non_common_countries_cache is None:
                    _non_common_countries_cache = self.country_service.get_all_non_common_country_codes()
                filter_countries.extend(_non_common_countries_cache)
            
            df = df.filter(pl.col("country").is_in(filter_countries))
        
        if race_filter:
            df = df.filter(pl.col("race").is_in(race_filter))
        
        # Apply best race only filtering if enabled
        if best_race_only:
            # Group by player_id and keep only the highest MMR entry (optimized groupby)
            df = (df
                .sort("mmr", descending=True)
                .group_by("player_id")
                .first()
            )
        
        # Sort by MMR (multi-threaded, very fast)
        df = df.sort("mmr", descending=True)
        
        # Calculate pagination
        total_players = len(df)
        total_pages = max(1, (total_players + page_size - 1) // page_size)
        
        # Limit to 25 pages to avoid Discord dropdown limits
        max_pages = 25
        if total_pages > max_pages:
            total_pages = max_pages
            max_players = max_pages * page_size
            df = df.head(max_players)
            total_players = max_players
        
        # Get page data (zero-copy slicing)
        start_idx = (current_page - 1) * page_size
        page_df = df.slice(start_idx, page_size)
        
        # Convert back to list of dicts for compatibility
        page_players = page_df.to_dicts()
        
        return {
            "players": page_players,
            "total_pages": total_pages,
            "current_page": current_page,
            "total_players": total_players
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
        if not players:
            return []
        
        formatted_players = []
        for i, player in enumerate(players, 1):
            rank = (current_page - 1) * page_size + i
            mmr_value = player.get('mmr', 0)
            mmr_display = int(round(mmr_value)) if isinstance(mmr_value, (int, float)) else 0
            
            formatted_players.append({
                "rank": rank,
                "player_id": player.get('player_id', 'Unknown'),
                "mmr": mmr_display,
                "race": self.race_service.format_race_name(player.get('race', 'Unknown')),
                "race_code": player.get('race', 'Unknown'),
                "country": player.get('country', 'Unknown'),
                "mmr_rank": player.get('rank', 'u_rank')
            })
        
        return formatted_players
    
    def get_pagination_info(self, current_page: int, total_pages: int, total_players: int) -> Dict[str, Any]:
        """Get pagination information as structured data."""
        return {
            "current_page": current_page,
            "total_pages": total_pages,
            "total_players": total_players
        }
    
    @staticmethod
    def invalidate_cache() -> None:
        """
        Invalidate the leaderboard cache.
        
        Call this when MMR values change (e.g., after a match is completed)
        to ensure the leaderboard reflects the latest data.
        """
        global _non_common_countries_cache
        _leaderboard_cache["data"] = None
        _leaderboard_cache["dataframe"] = None
        _leaderboard_cache["timestamp"] = 0
        _non_common_countries_cache = None
        print("[Leaderboard Cache] Invalidated")
