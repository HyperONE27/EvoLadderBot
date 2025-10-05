from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import pytest

from src.backend.services.mmr_service import MMRService


@dataclass(frozen=True)
class MMRTestCase:
    name: str
    player_one_mmr: float
    player_two_mmr: float
    result: int
    expected: Tuple[float, float]


# Expected outcomes calculated using the Elo formula with K=40.
MMR_CASES = [
    MMRTestCase(
        name="even_players_player_one_win",
        player_one_mmr=1500.0,
        player_two_mmr=1500.0,
        result=1,
        expected=(1520.0, 1480.0),
    ),
    MMRTestCase(
        name="rating_advantage_player_two_win",
        player_one_mmr=1700.0,
        player_two_mmr=1500.0,
        result=2,
        expected=(1669.6101229340816, 1530.3898770659184),
    ),
    MMRTestCase(
        name="draw_between_mismatched_players",
        player_one_mmr=1600.0,
        player_two_mmr=1400.0,
        result=0,
        expected=(1589.6101229340816, 1410.3898770659184),
    ),
]


@pytest.mark.parametrize("case", MMR_CASES, ids=lambda case: case.name)
def test_calculate_new_mmr(case: MMRTestCase) -> None:
    service = MMRService()

    outcome = service.calculate_new_mmr(case.player_one_mmr, case.player_two_mmr, case.result)

    assert pytest.approx(outcome.player_one_mmr, rel=1e-6) == case.expected[0]
    assert pytest.approx(outcome.player_two_mmr, rel=1e-6) == case.expected[1]


def test_default_mmr() -> None:
    service = MMRService()
    assert service.default_mmr() == 1500.0
