"""Races service backed by ``races.json`` configuration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.backend.services.base_config_service import BaseConfigService


class RacesService(BaseConfigService):
    """Service for managing race configuration data."""

    def __init__(self, config_path: str = "data/misc/races.json") -> None:
        super().__init__(config_path, code_field="code", name_field="name")

    # ------------------------------------------------------------------
    # Base overrides
    # ------------------------------------------------------------------
    def _process_raw_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        if isinstance(raw_data, dict):
            return list(raw_data.get("races", []))
        if isinstance(raw_data, list):
            return list(raw_data)
        return []

    def _get_default_data(self) -> List[Dict[str, Any]]:
        return []

    def _get_lookup_iterable(self) -> List[Dict[str, Any]]:
        return self.get_races()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_races(self) -> List[Dict[str, Any]]:
        return list(self.get_data())

    def get_race_options_for_dropdown(self) -> List[Tuple[str, str, str]]:
        return [
            (race.get("name", ""), race.get("code", ""), race.get("description", ""))
            for race in self.get_races()
        ]

    def get_race_order(self) -> List[str]:
        return [race.get("code") for race in self.get_races() if race.get("code")]

    def format_race_name(self, race_code: str) -> str:
        return self.get_race_name(race_code)

    # ------------------------------------------------------------------
    # Backwards compatibility helpers
    # ------------------------------------------------------------------
    def get_race_by_code(self, race_code: str) -> Optional[Dict[str, Any]]:
        return self.get_by_code(race_code)

    def get_race_name(self, race_code: str) -> str:
        return self.get_name_by_code(race_code)

    def get_race_short_name(self, race_code: str) -> str:
        entry = self.get_by_code(race_code)
        if entry is None:
            return race_code
        return entry.get("short_name", race_code)

    def get_race_codes(self) -> List[str]:
        return self.get_codes()

    def get_race_names(self) -> List[str]:
        return self.get_names()
"""
Races service.

This module defines the RacesService class, which contains methods for:
- Loading race configuration from races.json
- Providing race data for UI components
- Formatting race names consistently

Intended usage:
    from backend.services.races_service import RacesService

    races_service = RacesService()
    races = races_service.get_races()
"""

import json
from typing import List, Dict, Optional, Tuple, Any


class RacesService:
    """Service for managing race configuration data."""
    
    def __init__(self, config_path: str = "data/misc/races.json"):
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
