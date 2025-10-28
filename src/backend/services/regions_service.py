"""Regions service backed by ``regions.json`` configuration."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.backend.services.base_config_service import BaseConfigService


class RegionMappingNotFoundError(Exception):
    """Raised when no server mapping exists for a given region pair."""
    pass


class RegionsService(BaseConfigService):
    """Service for managing region configuration data."""

    def __init__(self, config_path: str = "data/misc/regions.json") -> None:
        super().__init__(config_path, code_field="code", name_field="name")
        self._residential_regions_cache: Optional[List[Dict[str, Any]]] = None
        self._game_servers_cache: Optional[List[Dict[str, Any]]] = None
        self._game_regions_cache: Optional[List[Dict[str, Any]]] = None
        
        self._cross_region_data: List[Dict[str, Any]] = []
        self._cross_region_map: Dict[frozenset, str] = {}
        self._short_name_to_name_map: Dict[str, str] = {}
        self._name_to_short_name_map: Dict[str, str] = {}
        
        self._load_cross_region_data()
        self._build_lookup_maps()

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
    
    def _load_cross_region_data(self) -> None:
        """Load cross-region mapping data from cross_table.json."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(__file__)
        )))
        cross_table_path = os.path.join(base_dir, "data", "misc", "cross_table.json")
        
        if not os.path.exists(cross_table_path):
            raise FileNotFoundError(f"Cross-region mapping file not found: {cross_table_path}")
        
        with open(cross_table_path, 'r', encoding='utf-8') as f:
            self._cross_region_data = json.load(f)
        
        if not isinstance(self._cross_region_data, list):
            raise ValueError("cross_table.json must contain a list of region mappings")
    
    def _build_lookup_maps(self) -> None:
        """Build efficient lookup maps for O(1) access."""
        self._cross_region_map = {}
        for entry in self._cross_region_data:
            region_1 = entry.get("region_1")
            region_2 = entry.get("region_2")
            mapping = entry.get("mapping")
            
            if not region_1 or not region_2 or not mapping:
                continue
            
            key = frozenset([region_1, region_2])
            self._cross_region_map[key] = mapping
        
        game_servers = self.get_game_servers()
        self._short_name_to_name_map = {
            server['short_name']: server['name'] 
            for server in game_servers 
            if 'short_name' in server and 'name' in server
        }
        self._name_to_short_name_map = {
            server['name']: server['short_name'] 
            for server in game_servers 
            if 'short_name' in server and 'name' in server
        }

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
    
    def get_game_server_name_by_short_name(self, short_name: str) -> str:
        """
        Convert a game server short_name to its full name.
        
        Args:
            short_name: The short name of the server (e.g., "US West")
            
        Returns:
            The full server name (e.g., "Western United States")
            
        Raises:
            ValueError: If the short_name is not found
        """
        if short_name not in self._short_name_to_name_map:
            raise ValueError(f"Invalid game server short_name: '{short_name}'")
        return self._short_name_to_name_map[short_name]
    
    def get_game_server_short_name_by_name(self, server_name: str) -> str:
        """
        Convert a game server full name to its short_name.
        
        Args:
            server_name: The full name of the server (e.g., "Western United States")
            
        Returns:
            The short server name (e.g., "US West")
            
        Raises:
            ValueError: If the server_name is not found
        """
        if server_name not in self._name_to_short_name_map:
            raise ValueError(f"Invalid game server name: '{server_name}'")
        return self._name_to_short_name_map[server_name]
    
    def get_game_server_code_by_name(self, server_name: str) -> str:
        """
        Get the game server code by its full name.
        
        Args:
            server_name: The full name of the server (e.g., "Western United States")
            
        Returns:
            The server code (e.g., "USW")
            
        Raises:
            ValueError: If the server_name is not found
        """
        for server in self.get_game_servers():
            if server.get('name') == server_name:
                code = server.get('code')
                if code:
                    return code
        raise ValueError(f"Invalid game server name: '{server_name}'")
    
    def get_match_server(self, region1: str, region2: str) -> str:
        """
        Determine the optimal game server for a match based on player regions.
        
        Args:
            region1: First player's residential region code (e.g., "NAW")
            region2: Second player's residential region code (e.g., "NAE")
            
        Returns:
            The full server name for the match (e.g., "Central United States")
            
        Raises:
            RegionMappingNotFoundError: If no mapping exists for the region pair
            ValueError: If the mapped short_name is invalid
        """
        lookup_key = frozenset([region1, region2])
        short_name = self._cross_region_map.get(lookup_key)
        
        if short_name is None:
            raise RegionMappingNotFoundError(
                f"No server mapping exists for the region pair: ({region1}, {region2})"
            )
        
        server_name = self.get_game_server_name_by_short_name(short_name)
        return server_name
