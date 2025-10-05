from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pytest

from src.backend.services.maps_service import MapsService

TEST_DATA_DIR = Path(__file__).resolve().parents[2] / "test_data"
MAPS_FIXTURE = TEST_DATA_DIR / "maps_sample.json"


TEST_CASES: list[tuple[str, Dict[str, Any]]] = [
    ("map_short_names", {"method": "get_map_short_names", "expected": ["Map1"]}),
    ("map_names", {"method": "get_map_names", "expected": ["Map One"]}),
    ("map_lookup", {"method": "get_map_name", "args": ("Map1",), "expected": "Map One"}),
    (
        "season_one_excluded",
        {
            "method": "get_map_short_names",
            "expected": ["Map1"],
            "negative": "Map2",
        },
    ),
]


@pytest.mark.parametrize("case_name, payload", TEST_CASES)
def test_maps_service(case_name: str, payload: Dict[str, Any]) -> None:
    service = MapsService(str(MAPS_FIXTURE))

    method_name: str = payload["method"]
    method: Callable[..., Any] = getattr(service, method_name)
    args: tuple[Any, ...] = payload.get("args", ())

    result = method(*args)
    expected = payload["expected"]

    if isinstance(result, list) and isinstance(expected, list):
        assert sorted(result) == sorted(expected), case_name
    else:
        assert result == expected, case_name

    negative = payload.get("negative")
    if negative and isinstance(result, list):
        assert negative not in result, f"{case_name}: unexpected value {negative} present"
