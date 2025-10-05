"""Regions service backed by ``regions.json`` configuration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.backend.services.base_config_service import BaseConfigService


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
        return sorted(self.get_residential_regions(), key=lambda entry: entry.get("name", ""))

    def search_regions(self, query: str, limit: int = 25) -> List[Dict[str, Any]]:
        return self.search_by_name(query, limit=limit)

    # ------------------------------------------------------------------
    # Backwards compatibility helpers
    # ------------------------------------------------------------------
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

    def get_region_from_code(self, code: str) -> str:
        return self.get_region_name(code)

    def get_code_from_region(self, name: str) -> str:
        return self.get_region_code(name)

    def get_all_regions(self) -> List[Dict[str, Any]]:
        return self.get_residential_regions()
"""
Regions service.

This module defines the RegionsService class, which contains methods for:
- Loading region data from regions.json
- Managing region filtering and pagination
- Providing region data for UI components
- Fast lookup functionality for regions

Intended usage:
    from backend.services.regions_service import RegionsService

    regions_service = RegionsService()
    regions = regions_service.get_residential_regions()
"""

import json
from typing import List, Dict, Optional, Tuple, Any


class RegionsService:
    """Service for managing region configuration data."""
    
    def __init__(self, config_path: str = "data/misc/regions.json"):
        self.config_path = config_path
        self._regions_cache = None
        self._residential_regions_cache = None
        self._game_servers_cache = None
        self._game_regions_cache = None
        
        # Fast lookup dictionaries
        self._code_to_name = None
        self._name_to_code = None
        self._region_dict = None
    
    def get_regions(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all regions data (residential_regions, game_servers, game_regions)."""
        if self._regions_cache is None:
            self._load_regions()
        return self._regions_cache
    
    def get_residential_regions(self) -> List[Dict[str, Any]]:
        """Get residential regions."""
        if self._residential_regions_cache is None:
            self._load_residential_regions()
        return self._residential_regions_cache
    
    def get_game_servers(self) -> List[Dict[str, Any]]:
        """Get game servers."""
        if self._game_servers_cache is None:
            self._load_game_servers()
        return self._game_servers_cache
    
    def get_game_regions(self) -> List[Dict[str, Any]]:
        """Get game regions."""
        if self._game_regions_cache is None:
            self._load_game_regions()
        return self._game_regions_cache
    
    def _load_regions(self):
        """Load regions from configuration file."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._regions_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._regions_cache = {
                "residential_regions": [],
                "game_servers": [],
                "game_regions": []
            }
    
    def _load_residential_regions(self):
        """Load residential regions from configuration file."""
        regions = self.get_regions()
        self._residential_regions_cache = regions.get("residential_regions", [])
        self._build_lookup_dicts()
    
    def _load_game_servers(self):
        """Load game servers from configuration file."""
        regions = self.get_regions()
        self._game_servers_cache = regions.get("game_servers", [])
    
    def _load_game_regions(self):
        """Load game regions from configuration file."""
        regions = self.get_regions()
        self._game_regions_cache = regions.get("game_regions", [])
    
    def _build_lookup_dicts(self):
        """Build fast lookup dictionaries for residential regions."""
        if self._residential_regions_cache is None:
            return
        
        self._code_to_name = {r["code"]: r["name"] for r in self._residential_regions_cache}
        self._name_to_code = {r["name"]: r["code"] for r in self._residential_regions_cache}
        self._region_dict = {r['code']: r for r in self._residential_regions_cache}
    
    def get_region_by_code(self, region_code: str) -> Optional[Dict[str, Any]]:
        """Get region data by code."""
        if self._region_dict is None:
            self._load_residential_regions()
        return self._region_dict.get(region_code)
    
    def get_region_name(self, region_code: str) -> str:
        """Get display name for region code."""
        if self._code_to_name is None:
            self._load_residential_regions()
        return self._code_to_name.get(region_code, region_code)
    
    def get_region_code(self, region_name: str) -> str:
        """Get region code from name."""
        if self._name_to_code is None:
            self._load_residential_regions()
        return self._name_to_code.get(region_name, region_name)
    
    def get_region_codes(self) -> List[str]:
        """Get list of all region codes."""
        regions = self.get_residential_regions()
        return [region.get("code") for region in regions if region.get("code")]
    
    def get_region_names(self) -> List[str]:
        """Get list of all region names."""
        regions = self.get_residential_regions()
        return [region.get("name") for region in regions if region.get("name")]
    
    def get_sorted_regions(self) -> List[Dict[str, Any]]:
        """Get all regions sorted by name."""
        regions = self.get_residential_regions()
        return sorted(regions, key=lambda x: x["name"])
    
    def search_regions(self, query: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Search regions by name."""
        regions = self.get_residential_regions()
        query_lower = query.lower()
        results = [
            r for r in regions 
            if query_lower in r['name'].lower()
        ]
        return results[:limit]
    
    def get_region_page_data(self, page: int, page_size: int) -> Tuple[List[Dict], int]:
        """Get paginated region data for UI dropdowns."""
        regions = self.get_residential_regions()
        total_pages = max(1, (len(regions) + page_size - 1) // page_size)
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_regions = regions[start_idx:end_idx]
        
        return page_regions, total_pages
    
    def get_region_names_for_codes(self, region_codes: List[str]) -> List[str]:
        """Get region names for a list of region codes."""
        return [self.get_region_name(code) for code in region_codes]
    
    def get_ordered_region_names(self, region_codes: List[str]) -> List[str]:
        """Get region names in the same order as the dropdown."""
        regions = self.get_residential_regions()
        all_region_codes = [r['code'] for r in regions]
        
        # Filter selected regions and maintain order
        ordered_regions = [code for code in all_region_codes if code in region_codes]
        return self.get_region_names_for_codes(ordered_regions)
    
    # Backward compatibility methods
    def get_region_from_code(self, code: str) -> str:
        """Get region name from code (backward compatibility)."""
        return self.get_region_name(code)
    
    def get_code_from_region(self, name: str) -> str:
        """Get region code from name (backward compatibility)."""
        return self.get_region_code(name)
    
    def get_all_regions(self) -> List[Dict[str, Any]]:
        """Get all regions (backward compatibility)."""
        return self.get_residential_regions().copy()
