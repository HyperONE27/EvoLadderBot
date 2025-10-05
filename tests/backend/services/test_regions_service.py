from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

import pytest

from src.backend.services.regions_service import RegionsService

TEST_DATA_DIR = Path(__file__).resolve().parents[2] / "test_data"
REGIONS_FIXTURE = TEST_DATA_DIR / "regions_sample.json"


TEST_CASES: list[tuple[str, Dict[str, Any]]] = [
    ("region_codes", {"method": "get_region_codes", "expected": ["NAW", "EUW"]}),
    ("region_names", {"method": "get_region_names", "expected": ["Western North America", "Western Europe"]}),
    ("region_name_lookup", {"method": "get_region_name", "args": ("EUW",), "expected": "Western Europe"}),
    ("all_regions", {"method": "get_all_regions", "expected": [{"code": "NAW", "name": "Western North America"}, {"code": "EUW", "name": "Western Europe"}]}),
    ("game_servers", {"method": "get_game_servers", "expected": [{"code": "USW", "name": "Western United States", "region_code": "AM"}, {"code": "EUC", "name": "Central Europe", "region_code": "EU"}]}),
    ("page_data", {"method": "get_region_page_data", "args": (1, 1), "expected": ([{"code": "NAW", "name": "Western North America"}], 2)}),
]


@pytest.mark.parametrize("case_name, payload", TEST_CASES)
def test_regions_service(case_name: str, payload: Dict[str, Any]) -> None:
    service = RegionsService(str(REGIONS_FIXTURE))

    method_name: str = payload["method"]
    method: Callable[..., Any] = getattr(service, method_name)
    args: tuple[Any, ...] = payload.get("args", ())

    result = method(*args)
    expected = payload["expected"]

    if isinstance(result, list) and isinstance(expected, list):
        assert sorted(result, key=str) == sorted(expected, key=str), case_name
    else:
        assert result == expected, case_name
