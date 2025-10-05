from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

import pytest

from src.backend.services.races_service import RacesService

TEST_DATA_DIR = Path(__file__).resolve().parents[2] / "test_data"
RACES_FIXTURE = TEST_DATA_DIR / "races_sample.json"


TEST_CASES: list[tuple[str, Dict[str, Any]]] = [
    ("race_codes", {"method": "get_race_codes", "expected": ["sc2_terran", "sc2_zerg"]}),
    ("race_names", {"method": "get_race_names", "expected": ["SC2 Terran", "SC2 Zerg"]}),
    ("race_name_lookup", {"method": "get_race_name", "args": ("sc2_zerg",), "expected": "SC2 Zerg"}),
    ("race_short_name", {"method": "get_race_short_name", "args": ("sc2_terran",), "expected": "Terran"}),
    (
        "dropdown_options",
        {
            "method": "get_race_options_for_dropdown",
            "expected": [("SC2 Terran", "sc2_terran", ""), ("SC2 Zerg", "sc2_zerg", "")],
        },
    ),
]


@pytest.mark.parametrize("case_name, payload", TEST_CASES)
def test_races_service(case_name: str, payload: Dict[str, Any]) -> None:
    service = RacesService(str(RACES_FIXTURE))

    method_name: str = payload["method"]
    method: Callable[..., Any] = getattr(service, method_name)
    args: tuple[Any, ...] = payload.get("args", ())

    result = method(*args)
    expected = payload["expected"]

    if isinstance(result, list) and isinstance(expected, list):
        assert sorted(result) == sorted(expected), case_name
    else:
        assert result == expected, case_name
