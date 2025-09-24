"""
Country configuration service.

This module defines the CountryConfigService class, which contains methods for:
- Loading country data from countries.json
- Managing country filtering and pagination
- Providing country data for UI components

Intended usage:
    from backend.services.country_config_service import CountryConfigService

    country_service = CountryConfigService()
    countries = country_service.get_common_countries()
"""

import json
from typing import List, Dict, Optional, Tuple


class CountryConfigService:
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
        self._common_countries_cache = [c for c in countries if c.get("common", False)]
    
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
