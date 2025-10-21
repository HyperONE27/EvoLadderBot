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

import polars as pl

from src.backend.db.db_reader_writer import DatabaseReader
from src.backend.services.countries_service import CountriesService
from src.backend.services.races_service import RacesService

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


def invalidate_leaderboard_cache():
    """
    Invalidate the leaderboard cache to force a refresh on next access.
    
    This should be called whenever MMR changes occur to ensure the leaderboard
    reflects the latest data without waiting for cache expiration.
    """
    global _leaderboard_cache
    _leaderboard_cache["data"] = None
    _leaderboard_cache["dataframe"] = None
    _leaderboard_cache["timestamp"] = 0
    print("[Leaderboard Cache] Invalidated due to MMR changes")


def _refresh_leaderboard_worker(database_url: str) -> bytes:
    """
    Blocking worker function to refresh leaderboard data in a separate process.
    
    This function:
    1. Initializes database connection pool for this worker process
    2. Fetches all player data from the database
    3. Calculates ranks using the ranking service
    4. Converts to a Polars DataFrame
    5. Closes the connection pool
    6. Returns the pickled DataFrame
    
    Args:
        database_url: Database connection URL (DSN)
        
    Returns:
        Pickled Polars DataFrame containing all leaderboard data with ranks
    """
    print("[Leaderboard Worker] Starting refresh in worker process...")
    
    # Import here to avoid circular imports and ensure fresh imports in worker
    from src.backend.db.connection_pool import initialize_pool, close_pool
    from src.backend.db.db_reader_writer import DatabaseReader
    from src.backend.services.ranking_service import RankingService
    
    try:
        # Initialize connection pool for this worker process
        # Each worker process needs its own pool since processes don't share memory
        print("[Leaderboard Worker] Initializing connection pool...")
        from src.bot.config import DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS
        initialize_pool(
            dsn=database_url,
            min_conn=DB_POOL_MIN_CONNECTIONS,
            max_conn=DB_POOL_MAX_CONNECTIONS,
            force=True  # Force reinitialization in worker process
        )
        
        # Create fresh instances for this worker process
        db_reader = DatabaseReader()
        ranking_service = RankingService(db_reader=db_reader)
        
        # Fetch all players
        all_players = db_reader.get_leaderboard_1v1(limit=10000)
        print(f"[Leaderboard Worker] Fetched {len(all_players)} players from database")
        
        # Refresh rankings
        print("[Leaderboard Worker] Refreshing rankings...")
        ranking_service.refresh_rankings()
        
        # Convert database format to expected format and add rank information
        formatted_players = []
        for player in all_players:
            discord_uid = player.get("discord_uid")
            race = player.get("race", "Unknown")
            
            # Get rank from ranking service
            rank = "u_rank"  # Default to unranked
            if discord_uid is not None and race != "Unknown":
                rank = ranking_service.get_rank(discord_uid, race)
            
            formatted_players.append({
                "player_id": player.get("player_name", "Unknown"),
                "mmr": player.get("mmr", 0),
                "race": race,
                "country": player.get("country", "Unknown"),
                "discord_uid": discord_uid,
                "rank": rank,
                "last_played": player.get("last_played", "1970-01-01T00:00:00Z")  # Default to epoch for sorting
            })
        
        # Convert to DataFrame
        df = pl.DataFrame(formatted_players)
        print(f"[Leaderboard Worker] Created DataFrame with {len(df)} rows")
        
        # Pickle the DataFrame for transfer back to main process
        pickled_df = pickle.dumps(df)
        print(f"[Leaderboard Worker] Pickled DataFrame size: {len(pickled_df) / 1024:.1f} KB")
        
        return pickled_df
        
    finally:
        # Always close the connection pool when done to prevent stale connections
        print("[Leaderboard Worker] Closing connection pool...")
        close_pool()


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
        
        NOTE: This is a synchronous method. For async contexts, use the async version
        which can optionally offload to a worker process.
        
        Returns:
            Polars DataFrame with all player data including ranks
        """
        current_time = time.time()
        
        # Check if cache is valid
        if (_leaderboard_cache["dataframe"] is not None and 
            current_time - _leaderboard_cache["timestamp"] < _leaderboard_cache["ttl"]):
            print(f"[Leaderboard Cache] HIT - Age: {current_time - _leaderboard_cache['timestamp']:.1f}s")
            return _leaderboard_cache["dataframe"]
        
        # Cache miss or expired - fetch from database (synchronous path)
        print("[Leaderboard Cache] MISS - Fetching from database (sync)...")
        all_players = self.db_reader.get_leaderboard_1v1(limit=10000)
        
        # Refresh rankings FIRST before processing players
        print("[Leaderboard Cache] Refreshing rankings...")
        self.ranking_service.refresh_rankings()
        
        # Convert database format to expected format and add rank information
        formatted_players = []
        for player in all_players:
            discord_uid = player.get("discord_uid")
            race = player.get("race", "Unknown")
            
            # Get rank from ranking service
            rank = "u_rank"
            if discord_uid is not None and race != "Unknown":
                rank = self.ranking_service.get_rank(discord_uid, race)
            
            formatted_players.append({
                "player_id": player.get("player_name", "Unknown"),
                "mmr": player.get("mmr", 0),
                "race": race,
                "country": player.get("country", "Unknown"),
                "discord_uid": discord_uid,
                "rank": rank,
                "last_played": player.get("last_played", "1970-01-01T00:00:00Z")  # Default to epoch for sorting
            })
        
        # Convert to DataFrame ONCE and cache it
        df = pl.DataFrame(formatted_players)
        
        # Update cache
        _leaderboard_cache["data"] = all_players
        _leaderboard_cache["dataframe"] = df
        _leaderboard_cache["timestamp"] = current_time
        print(f"[Leaderboard Cache] Updated - Cached {len(all_players)} players as DataFrame")
        
        return df
    
    async def _get_cached_leaderboard_dataframe_async(self, process_pool=None) -> pl.DataFrame:
        """
        Async version of _get_cached_leaderboard_dataframe that can optionally use
        a process pool to offload the heavy computation.
        
        Args:
            process_pool: Optional ProcessPoolExecutor for offloading work
            
        Returns:
            Polars DataFrame with all player data including ranks
        """
        current_time = time.time()
        
        # Check if cache is valid
        if (_leaderboard_cache["dataframe"] is not None and 
            current_time - _leaderboard_cache["timestamp"] < _leaderboard_cache["ttl"]):
            print(f"[Leaderboard Cache] HIT - Age: {current_time - _leaderboard_cache['timestamp']:.1f}s")
            return _leaderboard_cache["dataframe"]
        
        # Cache miss or expired - use process pool if available
        if process_pool is not None:
            print("[Leaderboard Cache] MISS - Offloading to worker process...")
            import asyncio
            from src.bot.config import DATABASE_URL
            loop = asyncio.get_running_loop()
            
            # Offload to worker process
            # Pass DATABASE_URL so worker can initialize its own connection pool
            pickled_df = await loop.run_in_executor(
                process_pool,
                _refresh_leaderboard_worker,
                DATABASE_URL
            )
            
            # Unpickle the DataFrame in the main process
            df = pickle.loads(pickled_df)
            print(f"[Leaderboard Cache] Received DataFrame from worker: {len(df)} rows")
            
            # Update cache
            _leaderboard_cache["dataframe"] = df
            _leaderboard_cache["timestamp"] = current_time
            
            return df
        else:
            # Process pool is required for async leaderboard operations
            raise RuntimeError("Process pool is required for async leaderboard operations. No synchronous fallback available.")
    
    async def get_leaderboard_data(
        self,
        *,
        country_filter: Optional[List[str]] = None,
        race_filter: Optional[List[str]] = None,
        best_race_only: bool = False,
        rank_filter: Optional[str] = None,
        current_page: int = 1,
        page_size: int = 20,
        process_pool=None
    ) -> Dict[str, Any]:
        """
        Get leaderboard data with filters applied.
        
        STATELESS: All filter state is passed as parameters to prevent race conditions.
        
        Args:
            country_filter: List of country codes to filter by (None = all)
            race_filter: List of race codes to filter by (None = all)
            best_race_only: If True, show only best race per player
            rank_filter: Rank to filter by (e.g., "s_rank", "a_rank", None = all)
            current_page: Page number (1-indexed)
            page_size: Number of items per page
            process_pool: Optional ProcessPoolExecutor for offloading heavy computation
        
        Returns:
            Dictionary containing players, pagination info, and totals
        """
        perf_start = time.time()
        
        # Get cached DataFrame (already has ranks computed)
        # Use async version to optionally offload to process pool
        df = await self._get_cached_leaderboard_dataframe_async(process_pool=process_pool)
        
        perf_cache = time.time()
        print(f"[Leaderboard Perf] Cache fetch: {(perf_cache - perf_start)*1000:.2f}ms")
        
        # Apply filters (optimized for large filter lists)
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
                    _non_common_countries_cache = self.country_service.get_all_non_common_country_codes()
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
        
        # Apply all filters at once using Polars' optimized all_horizontal combinator
        # This is fully vectorized and more efficient than manually combining with &
        if filter_conditions:
            df = df.filter(pl.all_horizontal(filter_conditions))
        
        perf_filter = time.time()
        print(f"[Leaderboard Perf] Apply filters: {(perf_filter - perf_cache)*1000:.2f}ms")
        
        # Apply best race only filtering if enabled
        if best_race_only:
            # Group by player_id and keep only the highest MMR entry
            # Sort first, then group and take first (highest MMR per player)
            df = (df
                .sort(["mmr", "last_played"], descending=[True, True])
                .group_by("player_id", maintain_order=True)
                .first()
            )
        
        perf_best_race = time.time()
        if best_race_only:
            print(f"[Leaderboard Perf] Best race filter: {(perf_best_race - perf_filter)*1000:.2f}ms")
        
        # Sort by MMR (descending), then by last_played (descending) for tie-breaking
        # Only sort if we didn't just do best_race_only (which already sorted)
        if not best_race_only:
            df = df.sort(["mmr", "last_played"], descending=[True, True])
        # Note: If best_race_only was enabled, data is already sorted from groupby operation
        
        perf_sort = time.time()
        print(f"[Leaderboard Perf] Sort by MMR: {(perf_sort - perf_best_race)*1000:.2f}ms")
        
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
        
        perf_slice = time.time()
        print(f"[Leaderboard Perf] Slice page: {(perf_slice - perf_sort)*1000:.2f}ms")
        
        # Convert back to list of dicts for compatibility
        page_players = page_df.to_dicts()
        
        perf_to_dicts = time.time()
        print(f"[Leaderboard Perf] to_dicts(): {(perf_to_dicts - perf_slice)*1000:.2f}ms")
        print(f"[Leaderboard Perf] TOTAL: {(perf_to_dicts - perf_start)*1000:.2f}ms")
        
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
        perf_start = time.time()
        
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
