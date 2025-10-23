"""Regions service backed by ``regions.json`` configuration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.backend.core.base_config_service import BaseConfigService


class RegionsService(BaseConfigService):
    """Service for managing region configuration data."""

    def __init__(self, config_path: str = "data/misc/regions.json") -> None:
        super().__init__(config_path, code_field="code", name_field="name")
        self._residential_regions_cache: Optional[List[Dict[str, Any]]] = None
        self._game_servers_cache: Optional[List[Dict[str, Any]]] = None
        self._game_regions_cache: Optional[List[Dict[str, Any]]] = None

    # ------------------------------------------------------------------
    # Base overrides
    # ------------------------------------------------------------------
    def _process_raw_data(self, raw_data: Any) -> Dict[str, List[Dict[str, Any]]]:
        if isinstance(raw_data, dict):
            return {
                "residential_regions": list(raw_data.get("residential_regions", [])),
                "game_servers": list(raw_data.get("game_servers", [])),
                "game_regions": list(raw_data.get("game_regions", [])),
            }
        return {
            "residential_regions": [],
            "game_servers": [],
            "game_regions": [],
        }

    def _get_default_data(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "residential_regions": [],
            "game_servers": [],
            "game_regions": [],
        }

    def _on_cache_refreshed(self) -> None:
        self._clear_cached_views()

    def _on_cache_cleared(self) -> None:
        self._clear_cached_views()

    def _get_lookup_iterable(self) -> Sequence[Dict[str, Any]]:
        return self.get_residential_regions()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _clear_cached_views(self) -> None:
        self._residential_regions_cache = None
        self._game_servers_cache = None
        self._game_regions_cache = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_regions(self) -> Dict[str, List[Dict[str, Any]]]:
        return dict(self.get_data())

    def get_residential_regions(self) -> List[Dict[str, Any]]:
        if self._residential_regions_cache is None:
            self._residential_regions_cache = list(self.get_data()["residential_regions"])
        return list(self._residential_regions_cache)

    def get_game_servers(self) -> List[Dict[str, Any]]:
        if self._game_servers_cache is None:
            self._game_servers_cache = list(self.get_data()["game_servers"])
        return list(self._game_servers_cache)

    def get_game_regions(self) -> List[Dict[str, Any]]:
        if self._game_regions_cache is None:
            self._game_regions_cache = list(self.get_data()["game_regions"])
        return list(self._game_regions_cache)

    def get_game_server_by_code(self, server_code: str) -> Optional[Dict[str, Any]]:
        for server in self.get_game_servers():
            if server.get("code") == server_code:
                return server
        return None

    def get_game_region_by_code(self, region_code: str) -> Optional[Dict[str, Any]]:
        for region in self.get_game_regions():
            if region.get("code") == region_code:
                return region
        return None

    def get_game_region_for_server(self, server_code: str) -> Optional[Dict[str, Any]]:
        """Return the game region definition for the provided server code."""

        if not server_code:
            return None

        server = self.get_game_server_by_code(server_code)
        if not server:
            return None

        region_code = server.get("region_code")
        if not region_code:
            return None

        return self.get_game_region_by_code(region_code)

    def format_server_with_region(self, server_code: str) -> str:
        """Return server display string such as 'Western United States (Americas)'"""
        if not server_code:
            return ""

        server = self.get_game_server_by_code(server_code)
        if server is None:
            return server_code

        server_name = server.get("name", server_code)
        region_code = server.get("region_code")
        if not region_code:
            return server_name

        region = self.get_game_region_by_code(region_code)
        region_name = region.get("name", region_code) if region else region_code

        return f"{server_name} ({region_name})"

    def get_random_game_server(self) -> str:
        """Get a random game server code from the available servers."""
        import random
        servers = self.get_game_servers()
        if not servers:
            return "USW"  # Fallback to a default server
        server = random.choice(servers)
        return server["code"]

    def get_region_page_data(self, page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int]:
        residential_regions = self.get_residential_regions()
        total_pages = max(1, (len(residential_regions) + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        return residential_regions[start_idx:end_idx], total_pages

    def get_region_names_for_codes(self, region_codes: List[str]) -> List[str]:
        return [self.get_name_by_code(code) for code in region_codes]

    def get_ordered_region_names(self, region_codes: List[str]) -> List[str]:
        ordered_codes: List[str] = []
        for region in self.get_residential_regions():
            code = region.get("code")
            if code in region_codes:
                ordered_codes.append(code)
        return self.get_region_names_for_codes(ordered_codes)

    def get_sorted_regions(self) -> List[Dict[str, Any]]:
        return sorted(self.get_residential_regions(), key=lambda entry: entry["name"])

    def search_regions(self, query: str, limit: int = 25) -> List[Dict[str, Any]]:
        return self.search_by_name(query, limit=limit)

    def get_region_by_code(self, region_code: str) -> Optional[Dict[str, Any]]:
        return self.get_by_code(region_code)

    def get_region_name(self, region_code: str) -> str:
        return self.get_name_by_code(region_code)

    def get_region_code(self, region_name: str) -> str:
        return self.get_code_by_name(region_name)

    def get_region_codes(self) -> List[str]:
        return self.get_codes()

    def get_region_names(self) -> List[str]:
        return self.get_names()

    def get_all_regions(self) -> List[Dict[str, Any]]:
        return self.get_residential_regions()
