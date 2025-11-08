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

    def get_races_by_game(self) -> Dict[str, List[Dict[str, Any]]]:
        brood_war: List[Dict[str, Any]] = []
        starcraft2: List[Dict[str, Any]] = []
        for race in self.get_races():
            code = race["code"]
            if code.startswith("bw_"):
                brood_war.append(race)
            elif code.startswith("sc2_"):
                starcraft2.append(race)
        return {"brood_war": brood_war, "starcraft2": starcraft2}

    def get_race_dropdown_groups(self) -> Dict[str, List[Tuple[str, str, str]]]:
        grouped = self.get_races_by_game()
        return {
            "brood_war": [
                (race["name"], race["code"], race.get("description", ""))
                for race in grouped["brood_war"]
            ],
            "starcraft2": [
                (race["name"], race["code"], race.get("description", ""))
                for race in grouped["starcraft2"]
            ],
        }

    def get_race_group_label(self, code: str) -> str:
        if code.startswith("bw_"):
            return "Brood War"
        if code.startswith("sc2_"):
            return "StarCraft II"
        return "Other"

    def get_race_options_for_dropdown(self) -> List[Tuple[str, str, str]]:
        return [
            (race["name"], race["code"], race.get("description", ""))
            for race in self.get_races()
        ]

    def get_race_order(self) -> List[str]:
        return [race.get("code") for race in self.get_races() if race.get("code")]

    def format_race_name(self, race_code: str) -> str:
        return self.get_race_name(race_code)

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
    
    def resolve_race_alias(self, race_string: str) -> Optional[str]:
        """
        Check if a race string is an alias and return the corresponding race code.
        
        This method searches through all races' alias lists to find a match.
        If found, returns the race code. If not found, returns None.
        
        Args:
            race_string: The race string to check (case-sensitive)
            
        Returns:
            The race code if the string is a known alias, None otherwise
        """
        for race in self.get_races():
            aliases = race.get('aliases', [])
            if race_string in aliases:
                return race.get('code')
        return None
    
    def normalize_race_code(self, race_string: str) -> Optional[str]:
        """
        Normalize a race string to a valid race code.
        
        First checks if it's already a valid race code.
        If not, checks if it's an alias and returns the corresponding code.
        
        Args:
            race_string: The race string to normalize
            
        Returns:
            The normalized race code, or None if not recognized
        """
        # First check if it's already a valid code
        if self.get_by_code(race_string) is not None:
            return race_string
        
        # Check if it's an alias
        return self.resolve_race_alias(race_string)