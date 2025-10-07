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
                [c for c in common_countries if c.get("code") not in ["XX", "ZZ"]],
                key=lambda item: item.get("name", ""),
            )
            # Add "Other" (ZZ) at the end
            other = next((c for c in countries if c.get("code") == "ZZ"), None)
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
        # Include all countries in search results, including XX and ZZ
        return results

    def get_country_by_code(self, country_code: str) -> Optional[Dict[str, Any]]:
        return self.get_by_code(country_code)
