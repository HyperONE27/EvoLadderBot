"""Maps service backed by ``maps.json`` configuration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.backend.services.base_config_service import BaseConfigService


class MapsService(BaseConfigService):
    """Service for managing map configuration data."""

    def __init__(self, config_path: str = "data/misc/maps.json") -> None:
        super().__init__(config_path, code_field="short_name", name_field="name")

    # ------------------------------------------------------------------
    # Base overrides
    # ------------------------------------------------------------------
    def _process_raw_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        if isinstance(raw_data, dict):
            maps_data = raw_data.get("maps", {})
            if isinstance(maps_data, dict):
                season_0 = maps_data.get("season_0")
                return list(season_0) if isinstance(season_0, list) else []
            if isinstance(maps_data, list):
                return list(maps_data)
        elif isinstance(raw_data, list):
            return list(raw_data)
        return []

    def _get_default_data(self) -> List[Dict[str, Any]]:
        return []

    def _get_lookup_iterable(self) -> List[Dict[str, Any]]:
        return self.get_maps()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_maps(self) -> List[Dict[str, Any]]:
        return list(self.get_data())

    def get_map_by_short_name(self, short_name: str) -> Optional[Dict[str, Any]]:
        return self.get_by_code(short_name)

    def get_map_name(self, short_name: str) -> str:
        return self.get_name_by_code(short_name)

    def get_map_short_names(self) -> List[str]:
        return self.get_codes()

    def get_map_names(self) -> List[str]:
        return self.get_names()
"""
Maps service.

This module defines the MapsService class, which contains methods for:
- Loading map configuration from maps.json
- Providing map data for UI components

Intended usage:
    from backend.services.maps_service import MapsService

    maps_service = MapsService()
    maps = maps_service.get_maps()
"""

import json
from typing import List, Dict, Optional


class MapsService:
    """Service for managing map configuration data."""
    
    def __init__(self, config_path: str = "data/misc/maps.json"):
        self.config_path = config_path
        self._maps_cache = None
    
    def get_maps(self) -> List[Dict[str, str]]:
        """Get all available ladder maps."""
        if self._maps_cache is None:
            self._load_maps()
        return self._maps_cache
    
    def _load_maps(self):
        """Load maps from configuration file."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                maps_data = config.get("maps", {})
                # Handle the new structure with seasons
                if isinstance(maps_data, dict) and "season_0" in maps_data:
                    self._maps_cache = maps_data["season_0"]
                elif isinstance(maps_data, list):
                    self._maps_cache = maps_data
                else:
                    self._maps_cache = []
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            self._maps_cache = []
    
    def get_map_by_short_name(self, short_name: str) -> Optional[Dict[str, str]]:
        """Get map data by short name."""
        maps = self.get_maps()
        for map_data in maps:
            if map_data.get("short_name") == short_name:
                return map_data
        return None
    
    def get_map_name(self, short_name: str) -> str:
        """Get display name for map short name."""
        map_data = self.get_map_by_short_name(short_name)
        return map_data.get("name", short_name) if map_data else short_name
    
    def get_map_short_names(self) -> List[str]:
        """Get list of all map short names."""
        return [map_data.get("short_name") for map_data in self.get_maps() if map_data.get("short_name")]
    
    def get_map_names(self) -> List[str]:
        """Get list of all map names."""
        return [map_data.get("name") for map_data in self.get_maps() if map_data.get("name")]
