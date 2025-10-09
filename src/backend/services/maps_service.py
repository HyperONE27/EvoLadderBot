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

    def get_available_maps(self) -> List[str]:
        """Get list of available map short names."""
        return self.get_map_short_names()
