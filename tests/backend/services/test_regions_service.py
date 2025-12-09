from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

import pytest

from src.backend.services.regions_service import RegionsService

TEST_DATA_DIR = Path(__file__).resolve().parents[2] / "test_data"
REGIONS_FIXTURE = TEST_DATA_DIR / "regions_sample.json"


def _codes_only(result: list[Dict[str, Any]]) -> list[str]:
    return [item["code"] for item in result]


def _names_only(result: list[Dict[str, Any]]) -> list[str]:
    return [item["name"] for item in result]


def _page_summary(result: tuple[list[Dict[str, Any]], int]) -> tuple[list[str], int]:
    page, total_pages = result
    return (_codes_only(page), total_pages)


TEST_CASES: list[tuple[str, Dict[str, Any]]] = [
    ("region_codes", {"method": "get_residential_regions", "transform": _codes_only, "expected": ["NAW", "EUW"]}),
    ("region_names", {"method": "get_residential_regions", "transform": _names_only, "expected": ["Western North America", "Western Europe"]}),
    ("region_name_lookup", {"method": "get_region_name", "args": ("EUW",), "expected": "Western Europe"}),
    ("all_regions", {"method": "get_all_regions", "transform": _codes_only, "expected": ["NAW", "EUW"]}),
    ("game_servers", {"method": "get_game_servers", "transform": _codes_only, "expected": ["USW", "EUC"]}),
    ("page_data", {"method": "get_region_page_data", "args": (1, 1), "transform": _page_summary, "expected": (["NAW"], 2)}),
]


@pytest.mark.parametrize("case_name, payload", TEST_CASES)
def test_regions_service(case_name: str, payload: Dict[str, Any]) -> None:
    service = RegionsService(str(REGIONS_FIXTURE))

    method_name: str = payload["method"]
    method: Callable[..., Any] = getattr(service, method_name)
    args: tuple[Any, ...] = payload.get("args", ())

    result = method(*args)
    transform = payload.get("transform")
    if transform:
        result = transform(result)

    expected = payload["expected"]
    if isinstance(result, list) and isinstance(expected, list):
        assert sorted(result) == sorted(expected), case_name
    else:
        assert result == expected, case_name
