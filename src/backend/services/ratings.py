"""Rating calculation service using Elo system."""
from typing import Tuple
import math
from ..db.models import Race, MatchResult


class RatingCalculator:
    """Calculate rating changes using the Elo rating system."""
    
    # K-factor determines how much ratings can change
    K_FACTOR_NEW = 40      # For players with < 30 games
    K_FACTOR_MID = 32      # For players with 30-100 games  
    K_FACTOR_STABLE = 24   # For players with > 100 games
    
    # Initial rating for new players
    INITIAL_RATING = 1500.0
    
    @staticmethod
    def get_k_factor(games_played: int) -> float:
        """Get K-factor based on number of games played."""
        if games_played < 30:
            return RatingCalculator.K_FACTOR_NEW
        elif games_played < 100:
            return RatingCalculator.K_FACTOR_MID
        else:
            return RatingCalculator.K_FACTOR_STABLE
    
    @staticmethod
    def calculate_expected_score(rating_a: float, rating_b: float) -> float:
        """Calculate expected score for player A against player B."""
        return 1.0 / (1.0 + math.pow(10, (rating_b - rating_a) / 400.0))
    
    @staticmethod
    def calculate_rating_change(
        rating_a: float,
        rating_b: float,
        actual_score: float,
        k_factor: float
    ) -> float:
        """Calculate rating change for a player."""
        expected_score = RatingCalculator.calculate_expected_score(rating_a, rating_b)
        return k_factor * (actual_score - expected_score)
    
    @staticmethod
    def calculate_match_ratings(
        player1_rating: float,
        player2_rating: float,
        player1_games: int,
        player2_games: int,
        result: MatchResult
    ) -> Tuple[float, float, float, float]:
        """
        Calculate new ratings after a match.
        
        Returns:
            Tuple of (player1_new_rating, player2_new_rating, 
                     player1_change, player2_change)
        """
        # Get K-factors
        k1 = RatingCalculator.get_k_factor(player1_games)
        k2 = RatingCalculator.get_k_factor(player2_games)
        
        # Determine actual scores based on result
        if result == MatchResult.PLAYER1_WIN:
            score1, score2 = 1.0, 0.0
        elif result == MatchResult.PLAYER2_WIN:
            score1, score2 = 0.0, 1.0
        elif result == MatchResult.DRAW:
            score1, score2 = 0.5, 0.5
        else:  # Cancelled
            return player1_rating, player2_rating, 0.0, 0.0
        
        # Calculate rating changes
        change1 = RatingCalculator.calculate_rating_change(
            player1_rating, player2_rating, score1, k1
        )
        change2 = RatingCalculator.calculate_rating_change(
            player2_rating, player1_rating, score2, k2
        )
        
        # Calculate new ratings
        new_rating1 = player1_rating + change1
        new_rating2 = player2_rating + change2
        
        # Ensure ratings don't go below 0
        new_rating1 = max(0.0, new_rating1)
        new_rating2 = max(0.0, new_rating2)
        
        return new_rating1, new_rating2, change1, change2
    
    @staticmethod
    def get_win_probability(rating_a: float, rating_b: float) -> float:
        """Get probability of player A winning against player B."""
        return RatingCalculator.calculate_expected_score(rating_a, rating_b)
