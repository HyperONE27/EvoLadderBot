"""
Leaderboard service.

This module defines the LeaderboardService class, which contains methods for:
- Periodically retrieving leaderboard data from the database and storing it perpertually in memory
- Filtering the leaderboard based on provided criteria
- Returning the leaderboard data in a formatted manner
- Managing filter state internally

Intended usage:
    from backend.services.leaderboard_service import LeaderboardService

    leaderboard = LeaderboardService()
    leaderboard.update_country_filter(['US', 'KR'])
    data = await leaderboard.get_leaderboard_data()
"""

import json
import os
from typing import Dict, List, Optional, Any
from src.backend.services.countries_service import CountriesService
from src.backend.services.races_service import RacesService


class LeaderboardService:
    """Service for handling leaderboard data operations with integrated filter management."""
    
    def __init__(self):
        self.data_file_path = "data/misc/leaderboard.json"
        
        # Services
        self.country_service = CountriesService()
        self.race_service = RacesService()
        
        # Filter state
        self.current_page: int = 1
        self.country_filter: List[str] = []
        self.race_filter: Optional[List[str]] = None
        self.best_race_only: bool = False
        self.country_page1_selection: List[str] = []
        self.country_page2_selection: List[str] = []
    
    def update_country_filter(self, page1_selection: List[str], page2_selection: List[str]) -> None:
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
    
    async def get_leaderboard_data(self, page_size: int = 20) -> Dict[str, Any]:
        """
        Get leaderboard data with current filters applied.
        
        Args:
            page_size: Number of items per page (default: 20)
        
        Returns:
            Dictionary containing players, pagination info, and totals
        """
        # Load mock data
        try:
            with open(self.data_file_path, "r") as f:
                all_players = json.load(f)
        except FileNotFoundError:
            return {
                "players": [],
                "total_pages": 1,
                "current_page": self.current_page,
                "total_players": 0
            }
        
        # Apply filters
        filtered_players = self._apply_filters(all_players)
        
        # Sort by ELO (descending)
        filtered_players.sort(key=lambda x: x["elo"], reverse=True)
        
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
            "total_players": total_players
        }
    
    def _apply_filters(self, players: List[Dict]) -> List[Dict]:
        """Apply all current filters to the player data."""
        filtered_players = players.copy()
        
        # Filter by country
        if self.country_filter:
            filtered_players = [p for p in filtered_players if p["country"] in self.country_filter]
        
        # Filter by race
        if self.race_filter:
            filtered_players = [p for p in filtered_players if p["race"] in self.race_filter]
        
        # Apply best race only filtering if enabled
        if self.best_race_only:
            # Group by player_id and keep only the highest ELO entry for each player
            player_best_races = {}
            for player in filtered_players:
                player_id = player["player_id"]
                if player_id not in player_best_races or player["elo"] > player_best_races[player_id]["elo"]:
                    player_best_races[player_id] = player
            filtered_players = list(player_best_races.values())
        
        return filtered_players
    
    def get_button_states(self, total_pages: int) -> Dict[str, bool]:
        """Get button states based on current page and total pages."""
        return {
            "previous_disabled": self.current_page <= 1,
            "next_disabled": self.current_page >= total_pages,
            "best_race_only_disabled": False
        }
    
    def get_filter_info(self) -> Dict[str, Any]:
        """Get filter information as structured data."""
        filter_info = {
            "race_filter": self.race_filter,
            "country_filter": self.country_filter,
            "best_race_only": self.best_race_only
        }
        
        # Add formatted race names if race filter is active
        if self.race_filter:
            if isinstance(self.race_filter, list):
                race_order = self.race_service.get_race_order()
                ordered_races = [race for race in race_order if race in self.race_filter]
                filter_info["race_names"] = [self.race_service.format_race_name(race) for race in ordered_races]
            else:
                filter_info["race_names"] = [self.race_service.format_race_name(self.race_filter)]
        
        # Add formatted country names if country filter is active
        if self.country_filter:
            country_names = self.country_service.get_ordered_country_names(self.country_filter)
            filter_info["country_names"] = country_names
        
        return filter_info
    
    def get_leaderboard_data_formatted(self, players: List[Dict], page_size: int = 20) -> List[Dict[str, Any]]:
        """Get leaderboard data formatted for display."""
        if not players:
            return []
        
        formatted_players = []
        for i, player in enumerate(players, 1):
            rank = (self.current_page - 1) * page_size + i
            formatted_players.append({
                "rank": rank,
                "player_id": player.get('player_id', 'Unknown'),
                "elo": player.get('elo', 0),
                "race": self.race_service.format_race_name(player.get('race', 'Unknown')),
                "country": player.get('country', 'Unknown')
            })
        
        return formatted_players
    
    def get_pagination_info(self, total_pages: int, total_players: int) -> Dict[str, Any]:
        """Get pagination information as structured data."""
        return {
            "current_page": self.current_page,
            "total_pages": total_pages,
            "total_players": total_players
        }