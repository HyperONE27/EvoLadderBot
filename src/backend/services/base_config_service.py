"""Base configuration service abstraction.

This module defines the :class:`BaseConfigService`, which consolidates common
behaviour for services that load structured configuration data from JSON
documents.  Concrete services only need to supply minimal overrides describing
how to interpret the raw JSON payload while inheriting:

* File loading with consistent error handling
* Caching and cache invalidation
* Common lookup helpers (by code/name) with memoisation
* Convenience utilities such as list of codes, names, and fuzzy search

Typical usage::

    from src.backend.services.countries_service import CountriesService

    countries = CountriesService()
    common = countries.get_common_countries()
    usa = countries.get_country_by_code("US")

Concrete subclasses should override :meth:`_process_raw_data` and
:meth:`_get_default_data` to shape the data appropriately, and may override
:meth:`_get_lookup_iterable` when lookups should operate on a subset of the
data (for example, only residential regions within a larger regions payload).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union


class BaseConfigService(ABC):
    """Common helper for JSON-backed configuration services."""

    def __init__(
        self,
        config_path: str,
        *,
        code_field: str = "code",
        name_field: str = "name",
    ) -> None:
        self.config_path = Path(config_path)
        self._cache: Optional[Any] = None
        self._lookup_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._name_lookup_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._code_field = code_field
        self._name_field = name_field

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------
    def get_data(self) -> Any:
        """Return the cached configuration payload, loading it if needed."""

        if self._cache is None:
            self._load_data()
        return self._cache

    def clear_cache(self) -> None:
        """Invalidate all cached data and lookup tables."""

        self._cache = None
        self._lookup_cache.clear()
        self._name_lookup_cache.clear()
        self._on_cache_cleared()

    def _load_data(self) -> None:
        """Load and process the backing JSON configuration."""

        try:
            with self.config_path.open("r", encoding="utf-8") as handle:
                raw_data = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            self._cache = self._get_default_data()
            self._lookup_cache.clear()
            self._name_lookup_cache.clear()
            self._on_load_error(exc)
        else:
            self._cache = self._process_raw_data(raw_data)
            self._lookup_cache.clear()
            self._name_lookup_cache.clear()
            self._on_cache_refreshed()

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------
    def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Return the configuration entry matching *code* if available."""

        if code not in self._lookup_cache:
            entry = self._find_by_code(code)
            self._lookup_cache[code] = entry
        return self._lookup_cache[code]

    def get_name_by_code(self, code: str) -> str:
        """Return the display name for *code*, falling back to the code."""

        entry = self.get_by_code(code)
        if entry is None:
            return code
        return str(entry.get(self._name_field, code))

    def get_code_by_name(self, name: str) -> str:
        """Return the identifier for *name*, falling back to the provided name."""

        if name not in self._name_lookup_cache:
            entry = self._find_by_name(name)
            self._name_lookup_cache[name] = entry
        entry = self._name_lookup_cache[name]
        if entry is None:
            return name
        code_value = entry.get(self._code_field)
        return str(code_value) if code_value is not None else name

    def get_codes(self) -> List[str]:
        """Return a list of all codes provided by the lookup iterable."""

        codes: List[str] = []
        for entry in self._get_lookup_iterable():
            code_value = entry.get(self._code_field)
            if code_value:
                codes.append(str(code_value))
        return codes

    def get_names(self) -> List[str]:
        """Return a list of all display names provided by the lookup iterable."""

        names: List[str] = []
        for entry in self._get_lookup_iterable():
            name_value = entry.get(self._name_field)
            if name_value:
                names.append(str(name_value))
        return names

    def search_by_name(self, query: str, *, limit: int = 25) -> List[Dict[str, Any]]:
        """Perform a case-insensitive search on the display name field."""

        if not query:
            return []

        query_lower = query.lower()
        results: List[Dict[str, Any]] = []
        for entry in self._get_lookup_iterable():
            name_value = entry.get(self._name_field)
            if name_value and query_lower in str(name_value).lower():
                results.append(entry)
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # Hooks for subclasses
    # ------------------------------------------------------------------
    def _get_lookup_iterable(self) -> Sequence[Dict[str, Any]]:
        """Return an iterable used for keyed lookups.

        By default this assumes :meth:`get_data` returns a list of dictionaries.
        Services dealing with nested payloads (for example ``{"races": [...]}``)
        should override this to expose the collection that contains the
        searchable records.
        """

        data = self.get_data()
        return data if isinstance(data, Sequence) else []

    def _on_cache_refreshed(self) -> None:
        """Hook called after successfully refreshing the cache."""

        # Subclasses can override to rebuild derived caches

    def _on_cache_cleared(self) -> None:
        """Hook called after caches are cleared."""

        # Subclasses can override to clear derived caches

    def _on_load_error(self, exc: Exception) -> None:
        """Hook called when loading fails due to *exc*."""

        # Subclasses can override to log errors elsewhere

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _find_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        for entry in self._get_lookup_iterable():
            if entry.get(self._code_field) == code:
                return entry
        return None

    def _find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        for entry in self._get_lookup_iterable():
            if entry.get(self._name_field) == name:
                return entry
        return None

    # ------------------------------------------------------------------
    # Abstract API (must be implemented by subclasses)
    # ------------------------------------------------------------------
    @abstractmethod
    def _process_raw_data(self, raw_data: Any) -> Any:
        """Transform raw JSON data to the format exposed by :meth:`get_data`."""

    @abstractmethod
    def _get_default_data(self) -> Any:
        """Return the default data used when loading fails."""
