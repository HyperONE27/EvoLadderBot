"""Countries service backed by ``countries.json`` configuration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.backend.services.base_config_service import BaseConfigService


class CountriesService(BaseConfigService):
    """Service for managing country configuration data."""

    def __init__(self, config_path: str = "data/misc/countries.json") -> None:
        super().__init__(config_path, code_field="code", name_field="name")
        self._common_countries_cache: Optional[List[Dict[str, Any]]] = None

    # ------------------------------------------------------------------
    # Base overrides
    # ------------------------------------------------------------------
    def _process_raw_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        return raw_data if isinstance(raw_data, list) else []

    def _get_default_data(self) -> List[Dict[str, Any]]:
        return []

    def _on_cache_refreshed(self) -> None:
        self._common_countries_cache = None

    def _on_cache_cleared(self) -> None:
        self._common_countries_cache = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_countries(self) -> List[Dict[str, Any]]:
        return list(self.get_data())

    def get_common_countries(self) -> List[Dict[str, Any]]:
        if self._common_countries_cache is None:
            countries = self.get_data()
            common_countries = [c for c in countries if c.get("common", False)]

            common_countries = sorted(
                [c for c in common_countries if c.get("code") != "XX"],
                key=lambda item: item.get("name", ""),
            )
            other = next((c for c in countries if c.get("code") == "XX"), None)
            if other:
                common_countries.append(other)
            self._common_countries_cache = common_countries

        return list(self._common_countries_cache)

    def get_country_page_data(self, page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int]:
        common_countries = self.get_common_countries()
        total_pages = max(1, (len(common_countries) + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        return common_countries[start_idx:end_idx], total_pages

    def get_country_names_for_codes(self, country_codes: List[str]) -> List[str]:
        return [self.get_name_by_code(code) for code in country_codes]

    def get_ordered_country_names(self, country_codes: List[str]) -> List[str]:
        ordered_codes: List[str] = []
        for country in self.get_common_countries():
            code = country.get("code")
            if code in country_codes:
                ordered_codes.append(code)
        return self.get_country_names_for_codes(ordered_codes)

    def get_sorted_countries(self) -> List[Dict[str, Any]]:
        return sorted(self.get_data(), key=lambda entry: entry.get("name", ""))

    def search_countries(self, query: str, limit: int = 25) -> List[Dict[str, Any]]:
        results = self.search_by_name(query, limit=limit)
        return [entry for entry in results if entry.get("code") != "XX"]

    # ------------------------------------------------------------------
    # Backwards compatibility helpers
    # ------------------------------------------------------------------
    def get_country_by_code(self, country_code: str) -> Optional[Dict[str, Any]]:
        return self.get_by_code(country_code)

    def get_country_name(self, country_code: str) -> str:
        return self.get_name_by_code(country_code)

    def get_country_codes(self) -> List[str]:
        return self.get_codes()

    def get_common_country_codes(self) -> List[str]:
        return [country.get("code") for country in self.get_common_countries() if country.get("code")]

    def get_country_from_code(self, code: str) -> str:
        return self.get_country_name(code)

    def get_code_from_country(self, name: str) -> str:
        return self.get_code_by_name(name)
"""
Countries service.

This module defines the CountriesService class, which contains methods for:
- Loading country data from countries.json
- Managing country filtering and pagination
- Providing country data for UI components

Intended usage:
    from backend.services.countries_service import CountriesService

    countries_service = CountriesService()
    countries = countries_service.get_common_countries()
"""

import json
from typing import List, Dict, Optional, Tuple, Any


class CountriesService:
    """Service for managing country configuration data."""
    
    def __init__(self, config_path: str = "data/misc/countries.json"):
        self.config_path = config_path
        self._countries_cache = None
        self._common_countries_cache = None
    
    def get_countries(self) -> List[Dict[str, any]]:
        """Get all countries."""
        if self._countries_cache is None:
            self._load_countries()
        return self._countries_cache
    
    def get_common_countries(self) -> List[Dict[str, any]]:
        """Get common countries (those marked as common=True)."""
        if self._common_countries_cache is None:
            self._load_common_countries()
        return self._common_countries_cache
    
    def _load_countries(self):
        """Load countries from configuration file."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._countries_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._countries_cache = []
    
    def _load_common_countries(self):
        """Load common countries from configuration file."""
        countries = self.get_countries()
        common_countries = [c for c in countries if c.get("common", False)]
        
        # Sort alphabetically by name, but put "Other" at the end
        common_countries = sorted(
            [c for c in common_countries if c['code'] != 'XX'],
            key=lambda x: x['name']
        )
        other = next((c for c in countries if c['code'] == 'XX'), None)
        if other:
            common_countries.append(other)
        
        self._common_countries_cache = common_countries
    
    def get_country_by_code(self, country_code: str) -> Optional[Dict[str, any]]:
        """Get country data by code."""
        countries = self.get_countries()
        for country in countries:
            if country.get("code") == country_code:
                return country
        return None
    
    def get_country_name(self, country_code: str) -> str:
        """Get display name for country code."""
        country = self.get_country_by_code(country_code)
        return country.get("name", country_code) if country else country_code
    
    def get_country_codes(self) -> List[str]:
        """Get list of all country codes."""
        return [country.get("code") for country in self.get_countries() if country.get("code")]
    
    def get_common_country_codes(self) -> List[str]:
        """Get list of common country codes."""
        return [country.get("code") for country in self.get_common_countries() if country.get("code")]
    
    def get_country_page_data(self, page: int, page_size: int) -> Tuple[List[Dict], int]:
        """Get paginated country data for UI dropdowns."""
        common_countries = self.get_common_countries()
        total_pages = max(1, (len(common_countries) + page_size - 1) // page_size)
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_countries = common_countries[start_idx:end_idx]
        
        return page_countries, total_pages
    
    def get_country_names_for_codes(self, country_codes: List[str]) -> List[str]:
        """Get country names for a list of country codes."""
        return [self.get_country_name(code) for code in country_codes]
    
    def get_ordered_country_names(self, country_codes: List[str]) -> List[str]:
        """Get country names in the same order as the dropdown (alphabetical with Other at end)."""
        common_countries = self.get_common_countries()
        all_country_codes = [c['code'] for c in common_countries]
        
        # Filter selected countries and maintain order
        ordered_countries = [code for code in all_country_codes if code in country_codes]
        return self.get_country_names_for_codes(ordered_countries)
    
    def get_sorted_countries(self) -> List[Dict[str, Any]]:
        """Get all countries sorted by name."""
        countries = self.get_countries()
        return sorted(countries, key=lambda x: x["name"])
    
    def search_countries(self, query: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Search countries by name."""
        countries = self.get_countries()
        query_lower = query.lower()
        # Exclude "Other" from search results
        results = [
            c for c in countries 
            if query_lower in c['name'].lower() and c['code'] != 'XX'
        ]
        return results[:limit]
    
    # Backward compatibility methods
    def get_country_from_code(self, code: str) -> str:
        """Get country name from code (backward compatibility)."""
        return self.get_country_name(code)
    
    def get_code_from_country(self, name: str) -> str:
        """Get country code from name (backward compatibility)."""
        countries = self.get_countries()
        for country in countries:
            if country.get("name") == name:
                return country.get("code", name)
        return name
