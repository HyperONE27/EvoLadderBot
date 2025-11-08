"""Mods service backed by ``mods.json`` configuration."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from src.backend.services.base_config_service import BaseConfigService


class ModsService(BaseConfigService):
    """Service for mod-related data and cache handle validation."""

    def __init__(self, config_path: str = "data/misc/mods.json") -> None:
        super().__init__(config_path, code_field="name", name_field="name")
        with open(config_path, "r", encoding="utf-8") as f:
            self.mod_data = json.load(f)

    def _process_raw_data(self, raw_data: Any) -> Dict[str, Any]:
        if isinstance(raw_data, dict):
            return raw_data
        return {}

    def _get_default_data(self) -> Dict[str, Any]:
        return {}

    def _get_lookup_iterable(self) -> List[Dict[str, Any]]:
        return [self.mod_data]

    def get_mod_name(self) -> str:
        """Get the mod name."""
        return str(self.mod_data.get("name", "SC: Evo Complete"))

    def get_mod_author(self) -> str:
        """Get the mod author."""
        return str(self.mod_data.get("author", "SCEvoDev"))

    def get_mod_link(self, region: str) -> Optional[str]:
        """
        Get the Battle.net link for the mod based on region.

        Args:
            region: Region identifier. Accepts "americas", "europe",
                "asia" or abbreviations "am", "eu", "as" (case-insensitive).

        Returns:
            Battle.net link for the mod, or None if not found
        """
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

        link_value = self.mod_data.get(link_key)
        return str(link_value) if isinstance(link_value, str) and link_value else None

    def get_handles_for_region(self, region: str) -> Tuple[List[str], List[str]]:
        """
        Get cache handles for a specific region.

        Args:
            region: Region identifier ("am", "eu", "as")

        Returns:
            Tuple of (main_handles, artmod_handles) for the region
        """
        normalized = region.strip().lower()
        region_key_map = {
            "americas": ("am_handles", "am_artmod_handles"),
            "am": ("am_handles", "am_artmod_handles"),
            "europe": ("eu_handles", "eu_artmod_handles"),
            "eu": ("eu_handles", "eu_artmod_handles"),
            "asia": ("as_handles", "as_artmod_handles"),
            "as": ("as_handles", "as_artmod_handles"),
        }

        keys = region_key_map.get(normalized)
        if not keys:
            return ([], [])

        main_key, artmod_key = keys
        main_handles = self.mod_data.get(main_key, [])
        artmod_handles = self.mod_data.get(artmod_key, [])

        return (main_handles, artmod_handles)

    def get_all_known_handles(self) -> Set[str]:
        """
        Get all known cache handles across all regions.

        Returns:
            Set of all known cache handle URLs
        """
        all_handles = set()

        for region in ["am", "eu", "as"]:
            main_handles, artmod_handles = self.get_handles_for_region(region)
            all_handles.update(main_handles)
            all_handles.update(artmod_handles)

        return all_handles

    def validate_cache_handles(self, cache_handles: List[str]) -> Dict[str, Any]:
        """
        Validate cache handles against mod requirements.

        Validation rules:
        1. Must contain ALL handles from one region (am/eu/as)
        2. May optionally contain artmod handles for that region
        3. Must contain exactly 7 unknown handles (not in any known list)

        Args:
            cache_handles: List of cache handle URLs from replay

        Returns:
            Dictionary with validation results:
            {
                "valid": bool,
                "region_detected": Optional[str],
                "message": str,
                "details": {
                    "total_handles": int,
                    "known_handles": int,
                    "unknown_handles": int,
                    "main_handles_found": List[str],
                    "artmod_handles_found": List[str],
                    "missing_handles": List[str]
                }
            }
        """
        cache_handles_set = set(cache_handles)
        all_known = self.get_all_known_handles()

        unknown_handles = cache_handles_set - all_known
        known_handles = cache_handles_set & all_known

        unknown_count = len(unknown_handles)
        known_count = len(known_handles)

        if unknown_count != 7:
            return {
                "valid": False,
                "region_detected": None,
                "message": f"Expected exactly 7 unknown handles, but found {unknown_count}.",
                "details": {
                    "total_handles": len(cache_handles),
                    "known_handles": known_count,
                    "unknown_handles": unknown_count,
                    "main_handles_found": [],
                    "artmod_handles_found": [],
                    "missing_handles": []
                }
            }

        region_detected = None
        for region in ["am", "eu", "as"]:
            main_handles, artmod_handles = self.get_handles_for_region(region)
            main_handles_set = set(main_handles)
            artmod_handles_set = set(artmod_handles)

            main_found = cache_handles_set & main_handles_set
            artmod_found = cache_handles_set & artmod_handles_set

            if main_found == main_handles_set:
                region_detected = region
                missing_handles = main_handles_set - cache_handles_set

                return {
                    "valid": True,
                    "region_detected": region,
                    "message": f"Mod file data signatures correspond to that of the official mod. Region: {region.upper()}",
                    "details": {
                        "total_handles": len(cache_handles),
                        "known_handles": known_count,
                        "unknown_handles": unknown_count,
                        "main_handles_found": list(main_found),
                        "artmod_handles_found": list(artmod_found),
                        "missing_handles": []
                    }
                }

        for region in ["am", "eu", "as"]:
            main_handles, _ = self.get_handles_for_region(region)
            main_handles_set = set(main_handles)
            main_found = cache_handles_set & main_handles_set
            missing_handles = main_handles_set - cache_handles_set

            if len(main_found) > 0:
                return {
                    "valid": False,
                    "region_detected": region,
                    "message": f"Incomplete {region.upper()} region handles. Missing {len(missing_handles)} required handles.",
                    "details": {
                        "total_handles": len(cache_handles),
                        "known_handles": known_count,
                        "unknown_handles": unknown_count,
                        "main_handles_found": list(main_found),
                        "artmod_handles_found": [],
                        "missing_handles": list(missing_handles)
                    }
                }

        return {
            "valid": False,
            "region_detected": None,
            "message": "No recognizable mod handles found. The mod used was likely unofficial.",
            "details": {
                "total_handles": len(cache_handles),
                "known_handles": known_count,
                "unknown_handles": unknown_count,
                "main_handles_found": [],
                "artmod_handles_found": [],
                "missing_handles": []
            }
        }

