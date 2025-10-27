"""Maps service backed by ``maps.json`` configuration."""

from __future__ import annotations

import json
from src.bot import config

from typing import Any, Dict, List, Optional

from src.backend.services.base_config_service import BaseConfigService


class MapsService(BaseConfigService):
    """Service for map-related data."""

    def __init__(self, config_path: str = "data/misc/maps.json") -> None:
        super().__init__(config_path, code_field="name", name_field="name")
        with open(config_path, "r", encoding="utf-8") as f:
            self.maps_data = json.load(f)["maps"]

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
    def get_maps(self) -> list:
        """Get the list of maps for the current season."""
        return self.maps_data.get(config.CURRENT_SEASON, [])

    def get_map_by_name(self, map_name: str) -> Optional[Dict[str, Any]]:
        """Get map data by full name. Primary lookup method."""
        return self.get_by_code(map_name)

    def get_map_names(self) -> list:
        """Get the full names of all maps in the current season."""
        return [map_data["name"] for map_data in self.get_maps()]

    def get_available_maps(self) -> list:
        """Get the full names of all available maps in the current season."""
        return self.get_map_names()

    def get_map_author(self, map_name: str) -> Optional[str]:
        """Return the author for the given map, if available.
        
        Args:
            map_name: Full map name (e.g., "Tokamak LE")
        """
        map_data = self.get_map_by_name(map_name)
        if not map_data:
            return None
        author = map_data.get("author")
        return str(author) if isinstance(author, str) else None

    def get_map_battlenet_link(self, map_name: str, region: str) -> Optional[str]:
        """Return the Battle.net link for the given map and region.

        Args:
            map_name: Full map name (e.g., "Tokamak LE")
            region: Region identifier. Accepts "americas", "europe",
                "asia" or abbreviations "am", "eu", "as" (case-insensitive).
        """
        map_data = self.get_map_by_name(map_name)
        if not map_data:
            return None

        normalized = region.strip().lower() 
        region_key_map = {
            "americas": "am_link",
            "am": "am_link",
            "europe": "eu_link",
            "eu": "eu_link",
            "asia": "as_link",
            "as": "as_link",
        }

        link_key = region_key_map.get(normalized)
        if not link_key:
            return None

        link_value = map_data.get(link_key)
        return str(link_value) if isinstance(link_value, str) and link_value else None

    # ------------------------------------------------------------------
    # DEPRECATED: Short name methods (kept for backwards compatibility)
    # ------------------------------------------------------------------
    def get_map_by_short_name(self, short_name: str) -> Optional[Dict[str, Any]]:
        """DEPRECATED: Use get_map_by_name with full name instead.
        
        This method is kept for backwards compatibility but should not be used
        in new code. It will attempt to find a map by short_name.
        """
        for map_data in self.get_maps():
            if map_data.get("short_name") == short_name:
                return map_data
        return None

    def get_map_name(self, short_name: str) -> str:
        """DEPRECATED: Use full names directly instead.
        
        This method is kept for backwards compatibility. It converts a short name
        to the full name.
        """
        map_data = self.get_map_by_short_name(short_name)
        if not map_data:
            return short_name
        return str(map_data.get("name", short_name))

    def get_short_name_by_full_name(self, full_name: str) -> str:
        """DEPRECATED: Short names are being deprecated.
        
        This method is kept for backwards compatibility. It converts a full name
        to the short name.
        """
        map_data = self.get_map_by_name(full_name)
        if not map_data:
            return full_name
        return str(map_data.get("short_name", full_name))

    def get_map_short_names(self) -> list:
        """DEPRECATED: Use get_map_names instead.
        
        Get the short names of all maps in the current season.
        This method is kept for backwards compatibility.
        """
        return [map_data["short_name"] for map_data in self.get_maps()]
