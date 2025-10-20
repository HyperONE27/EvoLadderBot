"""
Leaderboard service.

This module defines the LeaderboardService class, which contains methods for:
- Retrieving leaderboard data from the database
- Filtering the leaderboard based on provided criteria
- Returning the leaderboard data in a formatted manner
- Managing filter state internally

Intended usage:
    from backend.services.leaderboard_service import LeaderboardService

    leaderboard = LeaderboardService()
    leaderboard.update_country_filter(['US', 'KR'])
    data = await leaderboard.get_leaderboard_data()
"""

from typing import Any, Dict, List, Optional
from functools import lru_cache
import time

from src.backend.services.countries_service import CountriesService
from src.backend.services.races_service import RacesService
from src.backend.db.db_reader_writer import DatabaseReader, Database


# Global cache for leaderboard data with timestamp
_leaderboard_cache = {"data": None, "timestamp": 0, "ttl": 60}  # Cache for 60 seconds


class LeaderboardService:
    """Service for handling leaderboard data operations with integrated filter management."""

    def __init__(
        self,
        *,
        db: Database,
        country_service: CountriesService,
        race_service: RacesService,
    ) -> None:
        # Services
        self.country_service = country_service
        self.race_service = race_service
        self.db_reader = DatabaseReader(db)

        # Filter state
        self.current_page: int = 1
        self.country_filter: List[str] = []
        self.race_filter: Optional[List[str]] = None
        self.best_race_only: bool = False
        self.country_page1_selection: List[str] = []
        self.country_page2_selection: List[str] = []

    def update_country_filter(
        self, page1_selection: List[str], page2_selection: List[str]
    ) -> None:
        """Update country filter from both page selections."""
        self.country_page1_selection = page1_selection
        self.country_page2_selection = page2_selection
        self.country_filter = page1_selection + page2_selection
        self.current_page = 1  # Reset to first page when filter changes

    def update_race_filter(self, race_selection: Optional[List[str]]) -> None:
        """Update race filter."""
        self.race_filter = race_selection
        self.current_page = 1  # Reset to first page when filter changes

    def toggle_best_race_only(self) -> None:
        """Toggle best race only mode."""
        self.best_race_only = not self.best_race_only
        self.current_page = 1  # Reset to first page when filter changes

    def clear_all_filters(self) -> None:
        """Clear all filters and reset to default state."""
        self.race_filter = None
        self.country_filter = []
        self.country_page1_selection = []
        self.country_page2_selection = []
        self.best_race_only = False
        self.current_page = 1

    def set_page(self, page: int) -> None:
        """Set current page."""
        self.current_page = page

    def _get_cached_leaderboard_data(self) -> List[Dict]:
        """
        Get leaderboard data from cache or database.

        Cache is global and shared across all LeaderboardService instances.
        This dramatically reduces database load for frequently-accessed leaderboard data.

        Returns:
            List of player dictionaries with all data
        """
        current_time = time.time()

        # Check if cache is valid
        if (
            _leaderboard_cache["data"] is not None
            and current_time - _leaderboard_cache["timestamp"]
            < _leaderboard_cache["ttl"]
        ):
            print(
                f"[Leaderboard Cache] HIT - Age: {current_time - _leaderboard_cache['timestamp']:.1f}s"
            )
            return _leaderboard_cache["data"]

        # Cache miss or expired - fetch from database
        print("[Leaderboard Cache] MISS - Fetching from database...")
        all_players = []

        # If filtering by specific race(s), query each race
        if self.race_filter:
            for race in self.race_filter:
                race_players = self.db_reader.get_leaderboard_1v1(
                    race=race, limit=10000  # Large limit to get all players
                )
                all_players.extend(race_players)
        else:
            # Get all players regardless of race
            all_players = self.db_reader.get_leaderboard_1v1(limit=10000)

        # Update cache
        _leaderboard_cache["data"] = all_players
        _leaderboard_cache["timestamp"] = current_time
        print(f"[Leaderboard Cache] Updated - Cached {len(all_players)} players")

        return all_players

    async def get_leaderboard_data(self, page_size: int = 20) -> Dict[str, Any]:
        """
        Get leaderboard data with current filters applied.

        Uses in-memory caching to reduce database load. Cache expires after 60 seconds.

        Args:
            page_size: Number of items per page (default: 20)

        Returns:
            Dictionary containing players, pagination info, and totals
        """
        # Get data from database (with caching)
        all_players = self._get_cached_leaderboard_data()

        # Convert database format to expected format
        formatted_players = []
        for player in all_players:
            formatted_players.append(
                {
                    "player_id": player.get("player_name", "Unknown"),
                    "mmr": player.get("mmr", 0),
                    "race": player.get("race", "Unknown"),
                    "country": player.get("country", "Unknown"),
                    "discord_uid": player.get("discord_uid"),
                }
            )

        # Apply filters
        filtered_players = self._apply_filters(formatted_players)

        # Sort by MMR (descending)
        filtered_players.sort(key=lambda x: x["mmr"], reverse=True)

        # Calculate pagination
        total_players = len(filtered_players)
        total_pages = max(1, (total_players + page_size - 1) // page_size)

        # Get page data
        start_idx = (self.current_page - 1) * page_size
        end_idx = start_idx + page_size
        page_players = filtered_players[start_idx:end_idx]

        return {
            "players": page_players,
            "total_pages": total_pages,
            "current_page": self.current_page,
            "total_players": total_players,
        }

    def _apply_filters(self, players: List[Dict]) -> List[Dict]:
        """Apply all current filters to the player data."""
        filtered_players = players.copy()

        # Filter by country
        if self.country_filter:
            filtered_players = [
                p for p in filtered_players if p["country"] in self.country_filter
            ]

        # Filter by race
        if self.race_filter:
            filtered_players = [
                p for p in filtered_players if p["race"] in self.race_filter
            ]

        # Apply best race only filtering if enabled
        if self.best_race_only:
            # Group by player_id and keep only the highest MMR entry for each player
            player_best_races = {}
            for player in filtered_players:
                player_id = player["player_id"]
                if (
                    player_id not in player_best_races
                    or player["mmr"] > player_best_races[player_id]["mmr"]
                ):
                    player_best_races[player_id] = player
            filtered_players = list(player_best_races.values())

        return filtered_players

    def get_button_states(self, total_pages: int) -> Dict[str, bool]:
        """Get button states based on current page and total pages."""
        return {
            "previous_disabled": self.current_page <= 1,
            "next_disabled": self.current_page >= total_pages,
            "best_race_only_disabled": False,
        }

    def get_filter_info(self) -> Dict[str, Any]:
        """Get filter information as structured data."""
        filter_info = {
            "race_filter": self.race_filter,
            "country_filter": self.country_filter,
            "best_race_only": self.best_race_only,
        }

        # Add formatted race names if race filter is active
        if self.race_filter:
            if isinstance(self.race_filter, list):
                race_order = self.race_service.get_race_order()
                ordered_races = [
                    race for race in race_order if race in self.race_filter
                ]
                filter_info["race_names"] = [
                    self.race_service.format_race_name(race) for race in ordered_races
                ]
            else:
                filter_info["race_names"] = [
                    self.race_service.format_race_name(self.race_filter)
                ]

        # Add formatted country names if country filter is active
        if self.country_filter:
            country_names = self.country_service.get_ordered_country_names(
                self.country_filter
            )
            filter_info["country_names"] = country_names

        return filter_info

    def get_leaderboard_data_formatted(
        self, players: List[Dict], page_size: int = 20
    ) -> List[Dict[str, Any]]:
        """Get leaderboard data formatted for display."""
        if not players:
            return []

        formatted_players = []
        for i, player in enumerate(players, 1):
            rank = (self.current_page - 1) * page_size + i
            # Round MMR to integer for display
            mmr_value = player.get("mmr", 0)
            mmr_display = (
                int(round(mmr_value)) if isinstance(mmr_value, (int, float)) else 0
            )

            formatted_players.append(
                {
                    "rank": rank,
                    "player_id": player.get("player_id", "Unknown"),
                    "mmr": mmr_display,
                    "race": self.race_service.format_race_name(
                        player.get("race", "Unknown")
                    ),
                    "country": player.get("country", "Unknown"),
                }
            )

        return formatted_players

    def get_pagination_info(
        self, total_pages: int, total_players: int
    ) -> Dict[str, Any]:
        """Get pagination information as structured data."""
        return {
            "current_page": self.current_page,
            "total_pages": total_pages,
            "total_players": total_players,
        }

    @staticmethod
    def invalidate_cache() -> None:
        """
        Invalidate the leaderboard cache.

        Call this when MMR values change (e.g., after a match is completed)
        to ensure the leaderboard reflects the latest data.
        """
        _leaderboard_cache["data"] = None
        _leaderboard_cache["timestamp"] = 0
        print("[Leaderboard Cache] Invalidated")
