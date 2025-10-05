from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pytest

from src.backend.services.countries_service import CountriesService

TEST_DATA_DIR = Path(__file__).resolve().parents[2] / "test_data"
COUNTRIES_FIXTURE = TEST_DATA_DIR / "countries_sample.json"


def _page_summary(result: tuple[list[Dict[str, Any]], int]) -> tuple[list[str], int]:
    page, total_pages = result
    return ([entry["code"] for entry in page], total_pages)


def _names_only(result: list[Dict[str, Any]]) -> list[str]:
    return [item["name"] for item in result]


TEST_CASES: list[tuple[str, Dict[str, Any]]] = [
    ("country_codes", {"method": "get_country_codes", "expected": ["US", "GB", "XX", "BR"]}),
    (
        "common_country_codes",
        {"method": "get_common_country_codes", "expected": ["US", "GB", "XX"]},
    ),
    ("country_name_lookup", {"method": "get_country_name", "args": ("BR",), "expected": "Brazil"}),
    (
        "names_for_codes",
        {
            "method": "get_country_names_for_codes",
            "args": (["US", "GB"],),
            "expected": ["United States", "United Kingdom"],
        },
    ),
    (
        "page_data",
        {
            "method": "get_country_page_data",
            "args": (1, 2),
            "transform": _page_summary,
            "expected": (["GB", "US"], 2),
        },
    ),
    (
        "search_countries",
        {
            "method": "search_countries",
            "args": ("United",),
            "transform": _names_only,
            "expected": ["United Kingdom", "United States"],
        },
    ),
]


@pytest.mark.parametrize("case_name, payload", TEST_CASES)
def test_countries_service(case_name: str, payload: Dict[str, Any]) -> None:
    service = CountriesService(str(COUNTRIES_FIXTURE))

    method_name: str = payload["method"]
    method: Callable[..., Any] = getattr(service, method_name)
    args: tuple[Any, ...] = payload.get("args", ())

    result = method(*args)
    transform: Optional[Callable[[Any], Any]] = payload.get("transform")
    if transform is not None:
        result = transform(result)

    expected = payload["expected"]

    if isinstance(result, list) and isinstance(expected, list):
        assert sorted(result) == sorted(expected), case_name
    else:
        assert result == expected, case_name
