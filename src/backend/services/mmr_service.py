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

    player_one_mmr: float
    player_two_mmr: float


class MMRService:
    """Helper for calculating new MMR values after a match."""

    _DEFAULT_MMR: float = 1500.0
    _K_FACTOR: float = 40.0

    def calculate_new_mmr(self, player_one_mmr: float, player_two_mmr: float, result: int) -> MatchMMROutcome:
        """Return the updated MMR values for both players.

        Args:
            player_one_mmr: Current MMR for player one.
            player_two_mmr: Current MMR for player two.
            result: Match outcome (1 = player one win, 2 = player two win, 0 = draw).

        Returns:
            MatchMMROutcome tuple with the updated MMR values.
        """
        expected_one, expected_two = self._calculate_expected_mmr(player_one_mmr, player_two_mmr)
        score_one, score_two = self._calculate_actual_scores(result)

        updated_one = self._apply_rating_delta(player_one_mmr, expected_one, score_one)
        updated_two = self._apply_rating_delta(player_two_mmr, expected_two, score_two)

        return MatchMMROutcome(player_one_mmr=updated_one, player_two_mmr=updated_two)

    def default_mmr(self) -> float:
        """Return the default starting MMR value."""

        return self._DEFAULT_MMR

    def calculate_mmr_change(self, player_one_mmr: float, player_two_mmr: float, result: int) -> float:
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

    def _calculate_expected_mmr(self, player_one_mmr: float, player_two_mmr: float) -> Tuple[float, float]:
        """Return the expected MMR scores for both players."""

        difference = (player_two_mmr - player_one_mmr) / 400.0
        expected_one = 1.0 / (1.0 + 10.0 ** difference)
        expected_two = 1.0 / (1.0 + 10.0 ** -difference)
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

    def _apply_rating_delta(self, current_mmr: float, expected_score: float, actual_score: float) -> float:
        """Apply the MMR delta produced by the probabilistic model."""

        return current_mmr + self._K_FACTOR * (actual_score - expected_score)