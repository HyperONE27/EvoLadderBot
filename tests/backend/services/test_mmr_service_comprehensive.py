"""
Comprehensive test suite for MMRService.

Tests ELO rating calculations, edge cases, and mathematical properties.
"""

import pytest
import math
from src.backend.services.mmr_service import MMRService, MatchMMROutcome


class TestMMRService:
    """Comprehensive test suite for MMRService"""
    
    @pytest.fixture
    def mmr_service(self):
        """Fixture to provide an MMRService instance"""
        return MMRService()
    
    def test_calculate_new_mmr_equal_ratings(self, mmr_service):
        """Test MMR calculation when players have equal ratings"""
        
        test_cases = [
            # (p1_mmr, p2_mmr, result, expected_p1_change_approx, expected_p2_change_approx)
            (1500, 1500, 1, 20, -20),  # P1 wins, equal MMR -> +20/-20
            (1500, 1500, 2, -20, 20),  # P2 wins, equal MMR -> -20/+20
            (1500, 1500, 0, 0, 0),     # Draw, equal MMR -> 0/0
            (1000, 1000, 1, 20, -20),  # Different MMR level, same result
            (2000, 2000, 1, 20, -20),
            (1200, 1200, 2, -20, 20),
            (1800, 1800, 0, 0, 0),
        ]
        
        for p1_mmr, p2_mmr, result, expected_p1_change, expected_p2_change in test_cases:
            outcome = mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, result)
            actual_p1_change = outcome.player_one_mmr - p1_mmr
            actual_p2_change = outcome.player_two_mmr - p2_mmr
            
            assert abs(actual_p1_change - expected_p1_change) <= 1, \
                f"P1 change failed for equal ratings ({p1_mmr} vs {p2_mmr}, result={result}): " \
                f"expected ~{expected_p1_change}, got {actual_p1_change}"
            assert abs(actual_p2_change - expected_p2_change) <= 1, \
                f"P2 change failed for equal ratings ({p1_mmr} vs {p2_mmr}, result={result}): " \
                f"expected ~{expected_p2_change}, got {actual_p2_change}"
    
    def test_calculate_new_mmr_unequal_ratings(self, mmr_service):
        """Test MMR calculation when players have different ratings (upset vs expected)"""
        
        test_cases = [
            # (p1_mmr, p2_mmr, result, p1_should_gain_more_than_equal)
            # Underdog wins (gets more than 20)
            (1400, 1600, 1, True),   # Lower rated player wins -> gains more than 20
            (1200, 1800, 1, True),   # Big underdog wins -> gains much more
            (1000, 2000, 1, True),   # Massive upset
            # Favorite wins (gets less than 20)
            (1600, 1400, 1, False),  # Higher rated player wins -> gains less than 20
            (1800, 1200, 1, False),  # Big favorite wins -> gains much less
            (2000, 1000, 1, False),  # Expected blowout
            # Underdog loses (loses less than 20)
            (1400, 1600, 2, False),  # Lower rated player loses -> loses less than 20
            (1200, 1800, 2, False),  # Big underdog loses -> loses much less
            # Favorite loses (loses more than 20)
            (1600, 1400, 2, True),   # Higher rated player loses -> loses more than 20
            (1800, 1200, 2, True),   # Big favorite loses -> loses much more
        ]
        
        for p1_mmr, p2_mmr, result, should_gain_more in test_cases:
            outcome = mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, result)
            actual_p1_change = outcome.player_one_mmr - p1_mmr
            
            if should_gain_more:
                assert abs(actual_p1_change) > 20, \
                    f"Expected |change| > 20 for ({p1_mmr} vs {p2_mmr}, result={result}), got {actual_p1_change}"
            else:
                assert abs(actual_p1_change) < 20, \
                    f"Expected |change| < 20 for ({p1_mmr} vs {p2_mmr}, result={result}), got {actual_p1_change}"
    
    def test_calculate_new_mmr_conservation_of_rating(self, mmr_service):
        """Test that total MMR is conserved (zero-sum for wins/losses)"""
        
        test_cases = [
            # (p1_mmr, p2_mmr, result)
            (1500, 1500, 1),
            (1500, 1500, 2),
            (1500, 1500, 0),
            (1400, 1600, 1),
            (1400, 1600, 2),
            (1400, 1600, 0),
            (1200, 1800, 1),
            (1200, 1800, 2),
            (1000, 2000, 1),
            (2500, 500, 2),
        ]
        
        for p1_mmr, p2_mmr, result in test_cases:
            outcome = mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, result)
            total_before = p1_mmr + p2_mmr
            total_after = outcome.player_one_mmr + outcome.player_two_mmr
            
            # Allow for rounding error of up to 1 point total
            assert abs(total_before - total_after) <= 1, \
                f"MMR not conserved for ({p1_mmr} vs {p2_mmr}, result={result}): " \
                f"before={total_before}, after={total_after}, diff={total_after - total_before}"
    
    def test_calculate_new_mmr_draw_symmetry(self, mmr_service):
        """Test that draws result in symmetric MMR changes"""
        
        test_cases = [
            # (p1_mmr, p2_mmr)
            (1500, 1500),
            (1400, 1600),
            (1200, 1800),
            (1000, 2000),
            (1700, 1300),
        ]
        
        for p1_mmr, p2_mmr in test_cases:
            outcome = mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, 0)
            p1_change = outcome.player_one_mmr - p1_mmr
            p2_change = outcome.player_two_mmr - p2_mmr
            
            # For draws, the changes should be opposite and equal in magnitude
            assert p1_change == -p2_change, \
                f"Draw not symmetric for ({p1_mmr} vs {p2_mmr}): " \
                f"p1_change={p1_change}, p2_change={p2_change}"
    
    def test_calculate_new_mmr_boundary_values(self, mmr_service):
        """Test MMR calculation at extreme boundary values"""
        
        test_cases = [
            # (p1_mmr, p2_mmr, result, description)
            (0, 0, 1, "Both at 0"),
            (0, 0, 2, "Both at 0"),
            (0, 0, 0, "Both at 0 draw"),
            (0, 3000, 1, "Minimum vs maximum upset"),
            (3000, 0, 2, "Maximum vs minimum upset"),
            (0, 1500, 1, "0 beats average"),
            (3000, 1500, 2, "3000 loses to average"),
            (1, 1, 1, "Both at 1"),
            (5000, 5000, 1, "Both very high"),
        ]
        
        for p1_mmr, p2_mmr, result, description in test_cases:
            try:
                outcome = mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, result)
                # Check that results are reasonable integers
                assert isinstance(outcome.player_one_mmr, int), f"P1 MMR not int: {description}"
                assert isinstance(outcome.player_two_mmr, int), f"P2 MMR not int: {description}"
                # Check that MMR doesn't change by more than K_FACTOR (40)
                assert abs(outcome.player_one_mmr - p1_mmr) <= 40, \
                    f"P1 change > 40 for {description}: {outcome.player_one_mmr - p1_mmr}"
                assert abs(outcome.player_two_mmr - p2_mmr) <= 40, \
                    f"P2 change > 40 for {description}: {outcome.player_two_mmr - p2_mmr}"
            except Exception as e:
                pytest.fail(f"Failed for {description}: {e}")
    
    def test_calculate_mmr_change(self, mmr_service):
        """Test the calculate_mmr_change helper method"""
        
        test_cases = [
            # (p1_mmr, p2_mmr, result, expected_sign)
            (1500, 1500, 1, 1),   # Win -> positive
            (1500, 1500, 2, -1),  # Loss -> negative
            (1500, 1500, 0, 0),   # Draw equal -> zero
            (1400, 1600, 1, 1),   # Underdog win -> positive
            (1400, 1600, 2, -1),  # Underdog loss -> negative
            (1600, 1400, 1, 1),   # Favorite win -> positive
            (1600, 1400, 2, -1),  # Favorite loss -> negative
        ]
        
        for p1_mmr, p2_mmr, result, expected_sign in test_cases:
            change = mmr_service.calculate_mmr_change(p1_mmr, p2_mmr, result)
            
            if expected_sign > 0:
                assert change > 0, f"Expected positive change for ({p1_mmr} vs {p2_mmr}, result={result}), got {change}"
            elif expected_sign < 0:
                assert change < 0, f"Expected negative change for ({p1_mmr} vs {p2_mmr}, result={result}), got {change}"
            else:
                assert change == 0, f"Expected zero change for ({p1_mmr} vs {p2_mmr}, result={result}), got {change}"
    
    def test_invalid_result_values(self, mmr_service):
        """Test that invalid result values raise appropriate errors"""
        
        test_cases = [
            # (p1_mmr, p2_mmr, invalid_result)
            (1500, 1500, -1),
            (1500, 1500, 3),
            (1500, 1500, 99),
            (1500, 1500, -999),
            (1500, 1500, 1.5),
            (1500, 1500, None),
        ]
        
        for p1_mmr, p2_mmr, invalid_result in test_cases:
            with pytest.raises((ValueError, TypeError)):
                mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, invalid_result)
    
    def test_default_mmr(self, mmr_service):
        """Test the default MMR value"""
        assert mmr_service.default_mmr() == 1500
    
    def test_round_mmr_change(self, mmr_service):
        """Test MMR change rounding"""
        
        test_cases = [
            # (mmr_change, expected_rounded)
            (0, 0),
            (1, 1),
            (-1, -1),
            (10, 10),
            (-10, -10),
            (15.4, 15),
            (15.5, 16),
            (15.6, 16),
            (-15.4, -15),
            (-15.5, -16),
            (-15.6, -16),
            (0.1, 0),
            (0.5, 0),  # Python rounds to nearest even
            (1.5, 2),  # Python rounds to nearest even
            (2.5, 2),  # Python rounds to nearest even
        ]
        
        for mmr_change, expected in test_cases:
            result = mmr_service.round_mmr_change(mmr_change)
            assert result == expected, \
                f"Rounding failed for {mmr_change}: expected {expected}, got {result}"
    
    def test_expected_score_calculation(self, mmr_service):
        """Test the expected score calculation (internal method via full calculation)"""
        
        test_cases = [
            # (p1_mmr, p2_mmr, expected_p1_win_probability_range)
            (1500, 1500, (0.49, 0.51)),  # Equal -> ~50%
            (1600, 1400, (0.63, 0.65)),  # +200 MMR -> ~64%
            (1700, 1300, (0.75, 0.77)),  # +400 MMR -> ~76%
            (1400, 1600, (0.35, 0.37)),  # -200 MMR -> ~36%
            (2000, 1500, (0.84, 0.86)),  # +500 MMR -> ~85%
            (1500, 2000, (0.14, 0.16)),  # -500 MMR -> ~15%
        ]
        
        for p1_mmr, p2_mmr, (min_prob, max_prob) in test_cases:
            # Calculate expected by looking at draw outcome
            # If they draw, p1 gets +X, which tells us expected score
            outcome = mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, 0)
            p1_change = outcome.player_one_mmr - p1_mmr
            
            # Change = K * (actual - expected)
            # For draw: actual = 0.5
            # Change = 40 * (0.5 - expected)
            # expected = 0.5 - (change / 40)
            expected_score = 0.5 - (p1_change / 40)
            
            assert min_prob <= expected_score <= max_prob, \
                f"Expected score out of range for ({p1_mmr} vs {p2_mmr}): " \
                f"expected {min_prob}-{max_prob}, got {expected_score:.3f}"
    
    def test_mmr_outcome_immutability(self, mmr_service):
        """Test that MatchMMROutcome is immutable (frozen dataclass)"""
        outcome = mmr_service.calculate_new_mmr(1500, 1500, 1)
        
        with pytest.raises(AttributeError):
            outcome.player_one_mmr = 9999
        
        with pytest.raises(AttributeError):
            outcome.player_two_mmr = 9999
    
    def test_consistent_results(self, mmr_service):
        """Test that the same inputs always produce the same outputs"""
        
        test_cases = [
            (1500, 1500, 1),
            (1400, 1600, 2),
            (1200, 1800, 0),
        ]
        
        for p1_mmr, p2_mmr, result in test_cases:
            outcome1 = mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, result)
            outcome2 = mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, result)
            
            assert outcome1.player_one_mmr == outcome2.player_one_mmr, \
                f"Inconsistent P1 result for ({p1_mmr} vs {p2_mmr}, result={result})"
            assert outcome1.player_two_mmr == outcome2.player_two_mmr, \
                f"Inconsistent P2 result for ({p1_mmr} vs {p2_mmr}, result={result})"
    
    def test_large_mmr_differences(self, mmr_service):
        """Test behavior with very large MMR differences"""
        
        test_cases = [
            # (p1_mmr, p2_mmr, result, description)
            (3000, 0, 1, "3000 beats 0"),
            (0, 3000, 2, "0 loses to 3000"),
            (3000, 0, 2, "3000 loses to 0 (massive upset)"),
            (0, 3000, 1, "0 beats 3000 (massive upset)"),
            (2500, 500, 1, "2500 beats 500"),
            (500, 2500, 2, "500 loses to 2500"),
        ]
        
        for p1_mmr, p2_mmr, result, description in test_cases:
            outcome = mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, result)
            p1_change = outcome.player_one_mmr - p1_mmr
            
            # Verify change is within K_FACTOR bounds
            assert -40 <= p1_change <= 40, \
                f"Change out of bounds for {description}: {p1_change}"
            
            # Verify result is reasonable
            assert outcome.player_one_mmr >= 0, f"P1 MMR negative for {description}"
            assert outcome.player_two_mmr >= 0, f"P2 MMR negative for {description}"

