"""
Race configuration service.

This module defines the RaceConfigService class, which contains methods for:
- Loading race configuration from game_config.json
- Providing race data for UI components
- Formatting race names consistently

Intended usage:
    from backend.services.race_config_service import RaceConfigService

    race_service = RaceConfigService()
    races = race_service.get_races()
"""

import json
from typing import List, Dict, Optional, Tuple, Any


class RaceConfigService:
    """Service for managing race configuration data."""
    
    def __init__(self, config_path: str = "data/misc/game_config.json"):
        self.config_path = config_path
        self._races_cache = None
    
    def get_races(self) -> List[Dict[str, str]]:
        """Get all available races."""
        if self._races_cache is None:
            self._load_races()
        return self._races_cache
    
    def _load_races(self):
        """Load races from configuration file."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                self._races_cache = config.get("races", [])
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            self._races_cache = []
    
    def get_race_by_code(self, race_code: str) -> Optional[Dict[str, str]]:
        """Get race data by code."""
        races = self.get_races()
        for race in races:
            if race.get("code") == race_code:
                return race
        return None
    
    def get_race_name(self, race_code: str) -> str:
        """Get display name for race code."""
        race = self.get_race_by_code(race_code)
        return race.get("name", race_code) if race else race_code
    
    def get_race_short_name(self, race_code: str) -> str:
        """Get short name for race code."""
        race = self.get_race_by_code(race_code)
        return race.get("short_name", race_code) if race else race_code
    
    def get_race_codes(self) -> List[str]:
        """Get list of all race codes."""
        return [race.get("code") for race in self.get_races() if race.get("code")]
    
    def get_race_names(self) -> List[str]:
        """Get list of all race names."""
        return [race.get("name") for race in self.get_races() if race.get("name")]
    
    def get_race_options_for_dropdown(self) -> List[Tuple[str, str, str]]:
        """Get race options formatted for dropdown (label, value, description)."""
        races = self.get_races()
        return [(race.get("name", ""), race.get("code", ""), "") for race in races]
    
    def get_race_order(self) -> List[str]:
        """Get race codes in the order they should appear in UI."""
        return [race.get("code") for race in self.get_races() if race.get("code")]
    
    def format_race_name(self, race_code: str) -> str:
        """Format race name using the configuration data."""
        return self.get_race_name(race_code)
