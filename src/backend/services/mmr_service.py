"""
MMR service implementing rating updates using a Elo-based probabilistic model.

The goal of this service is to expose MMR-focused helpers that hide the
underlying rating mathematics. It is intentionally stateless so consumers can
instantiate once and reuse the helper methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class MatchMMROutcome:
    """Container for the updated MMR values after a match."""

    player_one_mmr: int
    player_two_mmr: int


class MMRService:
    """Helper for calculating new MMR values after a match."""

    _DEFAULT_MMR: int = 1500
    _K_FACTOR: int = 40
    _DIVISOR: int = 500

    def calculate_new_mmr(
        self, player_one_mmr: int, player_two_mmr: int, result: int
    ) -> MatchMMROutcome:
        """Return the updated MMR values for both players.

        Args:
            player_one_mmr: Current MMR for player one.
            player_two_mmr: Current MMR for player two.
            result: Match outcome (1 = player one win, 2 = player two win, 0 = draw).

        Returns:
            MatchMMROutcome tuple with the updated MMR values.
        """
        expected_one, expected_two = self._calculate_expected_mmr(
            player_one_mmr, player_two_mmr
        )
        score_one, score_two = self._calculate_actual_scores(result)

        updated_one = self._apply_rating_delta(player_one_mmr, expected_one, score_one)
        updated_two = self._apply_rating_delta(player_two_mmr, expected_two, score_two)

        return MatchMMROutcome(player_one_mmr=updated_one, player_two_mmr=updated_two)

    def default_mmr(self) -> int:
        """Return the default starting MMR value."""

        return self._DEFAULT_MMR

    def calculate_mmr_change(
        self, player_one_mmr: int, player_two_mmr: int, result: int
    ) -> int:
        """Calculate the MMR change for player one.

        Args:
            player_one_mmr: Current MMR for player one.
            player_two_mmr: Current MMR for player two.
            result: Match outcome (1 = player one win, 2 = player two win, 0 = draw).

        Returns:
            MMR change for player one (positive = gained, negative = lost).
        """
        outcome = self.calculate_new_mmr(player_one_mmr, player_two_mmr, result)
        return outcome.player_one_mmr - player_one_mmr

    def _calculate_expected_mmr(
        self, player_one_mmr: int, player_two_mmr: int
    ) -> Tuple[float, float]:
        """Return the expected MMR scores for both players."""

        difference = (player_two_mmr - player_one_mmr) / self._DIVISOR
        expected_one = 1.0 / (1.0 + 10.0**difference)
        expected_two = 1.0 / (1.0 + 10.0**-difference)
        return expected_one, expected_two

    def _calculate_actual_scores(self, result: int) -> Tuple[float, float]:
        """Translate the match outcome into MMR scores."""

        if result == 1:
            return 1.0, 0.0
        if result == 2:
            return 0.0, 1.0
        if result == 0:
            return 0.5, 0.5
        raise ValueError("result must be 0, 1, or 2")

    def round_mmr_change(self, mmr_change: int) -> int:
        """Rounds an MMR change to the nearest integer."""
        return round(mmr_change)

    def _apply_rating_delta(
        self, current_mmr: int, expected_score: float, actual_score: float
    ) -> int:
        """Apply the MMR delta produced by the probabilistic model."""

        return int(
            round(current_mmr + self._K_FACTOR * (actual_score - expected_score))
        )
