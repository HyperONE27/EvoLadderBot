"""Maps service backed by ``maps.json`` configuration."""

from __future__ import annotations

import json
from src.bot import config

from typing import Any, Dict, List, Optional

from src.backend.core.base_config_service import BaseConfigService


class MapsService(BaseConfigService):
    """Service for map-related data."""

    def __init__(self, config_path: str = "data/misc/maps.json") -> None:
        super().__init__(config_path, code_field="short_name", name_field="name")
        with open("data/misc/maps.json", "r", encoding="utf-8") as f:
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

    def get_map_by_short_name(self, short_name: str) -> Optional[Dict[str, Any]]:
        return self.get_by_code(short_name)

    def get_map_name(self, short_name: str) -> str:
        return self.get_name_by_code(short_name)

    def get_map_short_names(self) -> list:
        """Get the short names of all maps in the current season."""
        return [map_data["short_name"] for map_data in self.get_maps()]

    def get_map_names(self) -> List[str]:
        return self.get_names()

    def get_available_maps(self) -> list:
        """Get the short names of all available maps in the current season."""
        return self.get_map_short_names()

    def get_map_author(self, short_name: str) -> Optional[str]:
        """Return the author for the given map, if available."""

        map_data = self.get_map_by_short_name(short_name)
        if not map_data:
            return None
        author = map_data.get("author")
        return str(author) if isinstance(author, str) else None

    def get_map_battlenet_link(self, short_name: str, region: str) -> Optional[str]:
        """Return the Battle.net link for the given map and region.

        Args:
            short_name: Map short name.
            region: Region identifier. Accepts "americas", "europe",
                "asia" or abbreviations "am", "eu", "as" (case-insensitive).
        """

        map_data = self.get_map_by_short_name(short_name)
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
