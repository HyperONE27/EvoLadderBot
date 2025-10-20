"""
Static data cache service for maps, races, regions, and countries.

Loads static data once at startup to avoid repeated database queries.
Expected impact: 70% reduction in database queries for common operations.
"""

from typing import Dict, List, Optional
import json
import os


class StaticDataCache:
    """In-memory cache for static data that rarely changes."""

    def __init__(self):
        self._maps: Optional[List[Dict]] = None
        self._races: Optional[List[Dict]] = None
        self._regions: Optional[List[Dict]] = None
        self._countries: Optional[List[Dict]] = None
        self._initialized = False

    def initialize(self) -> None:
        """
        Load all static data once at startup.

        Loads from JSON files in data/misc/ directory.
        These files are version-controlled and much faster than database queries.
        """
        if self._initialized:
            print("[Cache] Already initialized, skipping...")
            return

        print("[Cache] Initializing static data cache...")

        try:
            # Load from JSON files (much faster than database)
            self._load_from_json()
            self._initialized = True

            print(f"[Cache] ✓ Loaded {len(self._maps)} maps")
            print(f"[Cache] ✓ Loaded {len(self._races)} races")
            print(f"[Cache] ✓ Loaded {len(self._regions)} regions")
            print(f"[Cache] ✓ Loaded {len(self._countries)} countries")
            print("[Cache] Static data cache ready!")

        except Exception as e:
            print(f"[Cache] ERROR: Failed to initialize cache: {e}")
            raise

    def _load_from_json(self) -> None:
        """Load data from JSON files in data/misc/."""
        base_path = "data/misc"

        with open(os.path.join(base_path, "maps.json"), "r", encoding="utf-8") as f:
            self._maps = json.load(f)

        with open(os.path.join(base_path, "races.json"), "r", encoding="utf-8") as f:
            self._races = json.load(f)

        with open(os.path.join(base_path, "regions.json"), "r", encoding="utf-8") as f:
            self._regions = json.load(f)

        with open(
            os.path.join(base_path, "countries.json"), "r", encoding="utf-8"
        ) as f:
            self._countries = json.load(f)

    # ========== Maps ==========

    def get_maps(self) -> List[Dict]:
        """
        Get all maps.

        Returns:
            List of map dictionaries.
        """
        self._ensure_initialized()
        return self._maps.copy()

    def get_map_by_code(self, code: str) -> Optional[Dict]:
        """
        Get map by code.

        Args:
            code: Map code (e.g., 'GOLDENWALL')

        Returns:
            Map dictionary or None if not found.
        """
        self._ensure_initialized()
        return next((m for m in self._maps if m.get("code") == code), None)

    def get_map_by_name(self, name: str) -> Optional[Dict]:
        """
        Get map by name (case-insensitive).

        Args:
            name: Map name (e.g., 'Golden Wall')

        Returns:
            Map dictionary or None if not found.
        """
        self._ensure_initialized()
        name_lower = name.lower()
        return next(
            (m for m in self._maps if m.get("name", "").lower() == name_lower), None
        )

    # ========== Races ==========

    def get_races(self) -> List[Dict]:
        """
        Get all races.

        Returns:
            List of race dictionaries.
        """
        self._ensure_initialized()
        return self._races.copy()

    def get_race_by_code(self, code: str) -> Optional[Dict]:
        """
        Get race by code.

        Args:
            code: Race code (e.g., 'bw_terran', 'sc2_zerg')

        Returns:
            Race dictionary or None if not found.
        """
        self._ensure_initialized()
        return next((r for r in self._races if r.get("code") == code), None)

    def get_race_by_name(self, name: str) -> Optional[Dict]:
        """
        Get race by name (case-insensitive).

        Args:
            name: Race name (e.g., 'Terran', 'Zerg')

        Returns:
            Race dictionary or None if not found.
        """
        self._ensure_initialized()
        name_lower = name.lower()
        return next(
            (r for r in self._races if r.get("name", "").lower() == name_lower), None
        )

    # ========== Regions ==========

    def get_regions(self) -> List[Dict]:
        """
        Get all regions.

        Returns:
            List of region dictionaries.
        """
        self._ensure_initialized()
        return self._regions.copy()

    def get_region_by_code(self, code: str) -> Optional[Dict]:
        """
        Get region by code.

        Args:
            code: Region code (e.g., 'NA_WEST', 'EU_WEST')

        Returns:
            Region dictionary or None if not found.
        """
        self._ensure_initialized()
        return next((r for r in self._regions if r.get("code") == code), None)

    def get_region_by_name(self, name: str) -> Optional[Dict]:
        """
        Get region by name (case-insensitive).

        Args:
            name: Region name

        Returns:
            Region dictionary or None if not found.
        """
        self._ensure_initialized()
        name_lower = name.lower()
        return next(
            (r for r in self._regions if r.get("name", "").lower() == name_lower), None
        )

    # ========== Countries ==========

    def get_countries(self) -> List[Dict]:
        """
        Get all countries.

        Returns:
            List of country dictionaries.
        """
        self._ensure_initialized()
        return self._countries.copy()

    def get_country_by_code(self, code: str) -> Optional[Dict]:
        """
        Get country by code.

        Args:
            code: Country code (e.g., 'US', 'KR', 'DE')

        Returns:
            Country dictionary or None if not found.
        """
        self._ensure_initialized()
        return next((c for c in self._countries if c.get("code") == code), None)

    def get_country_by_name(self, name: str) -> Optional[Dict]:
        """
        Get country by name (case-insensitive).

        Args:
            name: Country name (e.g., 'United States', 'South Korea')

        Returns:
            Country dictionary or None if not found.
        """
        self._ensure_initialized()
        name_lower = name.lower()
        return next(
            (c for c in self._countries if c.get("name", "").lower() == name_lower),
            None,
        )

    # ========== Utilities ==========

    def _ensure_initialized(self) -> None:
        """Ensure cache is initialized before access."""
        if not self._initialized:
            raise RuntimeError(
                "Cache not initialized. Call static_cache.initialize() at startup."
            )

    def reload(self) -> None:
        """
        Reload all data from files.

        Useful for admin commands to refresh data without restarting bot.
        """
        print("[Cache] Reloading static data...")
        self._initialized = False
        self.initialize()

    def get_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with counts of cached items.
        """
        if not self._initialized:
            return {"initialized": False}

        return {
            "initialized": True,
            "maps": len(self._maps),
            "races": len(self._races),
            "regions": len(self._regions),
            "countries": len(self._countries),
        }


# Global singleton instance
static_cache = StaticDataCache()
