"""
Comprehensive tests for matchmaking algorithm optimizations.

Tests the new 7-stage matchmaking algorithm including:
- Smart "both" player assignment
- Priority ordering
- Locally-optimal matching
- Least-squares refinement
- Pressure threshold adjustments
"""

import pytest
from src.backend.services.matchmaking_service import Matchmaker, Player, QueuePreferences
from src.backend.core import config


@pytest.fixture
def matchmaker():
    """Create a fresh matchmaker instance for each test"""
    return Matchmaker()


class TestSkillBiasCalculation:
    """Test the skill bias calculation for 'both' players"""
    
    def test_bw_favoring_player(self, matchmaker):
        """Test player with higher BW MMR"""
        player = Player(
            discord_user_id=1,
            user_id="test1",
            preferences=QueuePreferences(
                selected_races=["bw_zerg", "sc2_terran"],
                vetoed_maps=[],
                discord_user_id=1,
                user_id="test1"
            ),
            bw_mmr=1600,
            sc2_mmr=1400
        )
        
        bias = matchmaker._calculate_skill_bias(player)
        assert bias == 200  # Positive = BW stronger
    
    def test_sc2_favoring_player(self, matchmaker):
        """Test player with higher SC2 MMR"""
        player = Player(
            discord_user_id=2,
            user_id="test2",
            preferences=QueuePreferences(
                selected_races=["bw_protoss", "sc2_zerg"],
                vetoed_maps=[],
                discord_user_id=2,
                user_id="test2"
            ),
            bw_mmr=1300,
            sc2_mmr=1600
        )
        
        bias = matchmaker._calculate_skill_bias(player)
        assert bias == -300  # Negative = SC2 stronger
    
    def test_neutral_player(self, matchmaker):
        """Test player with equal MMRs"""
        player = Player(
            discord_user_id=3,
            user_id="test3",
            preferences=QueuePreferences(
                selected_races=["bw_terran", "sc2_protoss"],
                vetoed_maps=[],
                discord_user_id=3,
                user_id="test3"
            ),
            bw_mmr=1500,
            sc2_mmr=1500
        )
        
        bias = matchmaker._calculate_skill_bias(player)
        assert bias == 0  # Neutral


class TestSmartBothAssignment:
    """Test intelligent 'both' player assignment"""
    
    def test_empty_lists_even_distribution(self, matchmaker):
        """Test even distribution when both BW and SC2 lists are empty"""
        both_players = [
            Player(1, "p1", QueuePreferences(["bw_zerg", "sc2_terran"], [], 1, "p1"), 1600, 1400),
            Player(2, "p2", QueuePreferences(["bw_protoss", "sc2_zerg"], [], 2, "p2"), 1300, 1600),
            Player(3, "p3", QueuePreferences(["bw_terran", "sc2_protoss"], [], 3, "p3"), 1500, 1500),
            Player(4, "p4", QueuePreferences(["bw_zerg", "sc2_terran"], [], 4, "p4"), 1400, 1700),
        ]
        
        bw_list, sc2_list, remaining = matchmaker.equalize_lists([], [], both_players)
        
        # Should split evenly
        assert abs(len(bw_list) - len(sc2_list)) <= 1
        assert len(remaining) == 0
        assert len(bw_list) + len(sc2_list) == 4
    
    def test_balances_population_counts(self, matchmaker):
        """Test that population counts are balanced"""
        bw_only = [Player(i, f"bw{i}", QueuePreferences(["bw_zerg"], [], i, f"bw{i}"), 1500, None) for i in range(2)]
        sc2_only = [Player(i+10, f"sc2{i}", QueuePreferences(["sc2_terran"], [], i+10, f"sc2{i}"), None, 1500) for i in range(5)]
        both = [Player(i+20, f"both{i}", QueuePreferences(["bw_protoss", "sc2_zerg"], [], i+20, f"both{i}"), 1500, 1500) for i in range(4)]
        
        bw_list, sc2_list, remaining = matchmaker.equalize_lists(bw_only, sc2_only, both)
        
        # Should balance: 2 BW + some both ≈ 5 SC2 + some both
        assert abs(len(bw_list) - len(sc2_list)) <= 1
    
    def test_skill_based_assignment(self, matchmaker):
        """Test that skill bias influences assignment"""
        bw_only = []
        sc2_only = []
        both = [
            Player(1, "p1", QueuePreferences(["bw_zerg", "sc2_terran"], [], 1, "p1"), 1700, 1300),  # Strong BW
            Player(2, "p2", QueuePreferences(["bw_protoss", "sc2_zerg"], [], 2, "p2"), 1300, 1700),  # Strong SC2
        ]
        
        bw_list, sc2_list, remaining = matchmaker.equalize_lists(bw_only, sc2_only, both)
        
        # Should have one on each side
        assert len(bw_list) == 1
        assert len(sc2_list) == 1
        
        # The BW-strong player should be in BW list
        bw_player = bw_list[0]
        assert bw_player.bw_mmr > bw_player.sc2_mmr


class TestLocallyOptimalMatching:
    """Test the locally-optimal candidate-based matching"""
    
    def test_builds_candidate_pairs(self, matchmaker):
        """Test that candidate pairs are built correctly"""
        lead_players = [
            Player(1, "l1", QueuePreferences(["bw_zerg"], [], 1, "l1"), 1500, None),
            Player(2, "l2", QueuePreferences(["bw_protoss"], [], 2, "l2"), 1600, None),
        ]
        follow_players = [
            Player(10, "f1", QueuePreferences(["sc2_terran"], [], 10, "f1"), None, 1520),
            Player(11, "f2", QueuePreferences(["sc2_zerg"], [], 11, "f2"), None, 1580),
        ]
        
        matchmaker.players = lead_players + follow_players  # Set for queue size
        candidates = matchmaker._build_candidate_pairs(lead_players, follow_players, is_bw_match=True)
        
        # Should have 2x2 = 4 candidates (all within default MMR window)
        assert len(candidates) >= 2  # At least some valid pairs
        
        # Each candidate should be a tuple of (score, lead, follow, mmr_diff)
        for candidate in candidates:
            assert len(candidate) == 4
            score, lead, follow, mmr_diff = candidate
            assert isinstance(score, (int, float))
            assert isinstance(lead, Player)
            assert isinstance(follow, Player)
            assert isinstance(mmr_diff, int)
    
    def test_selects_best_matches(self, matchmaker):
        """Test that best matches are selected from candidates"""
        # Create candidates with different scores
        lead1 = Player(1, "l1", QueuePreferences(["bw_zerg"], [], 1, "l1"), 1500, None)
        lead2 = Player(2, "l2", QueuePreferences(["bw_protoss"], [], 2, "l2"), 1600, None)
        follow1 = Player(10, "f1", QueuePreferences(["sc2_terran"], [], 10, "f1"), None, 1510)
        follow2 = Player(11, "f2", QueuePreferences(["sc2_zerg"], [], 11, "f2"), None, 1620)
        
        candidates = [
            (100, lead1, follow1, 10),   # Good match (score 100)
            (400, lead1, follow2, 20),   # Worse match (score 400)
            (400, lead2, follow1, 20),   # Worse match (score 400)
            (400, lead2, follow2, 20),   # Good match (score 400)
        ]
        
        matches = matchmaker._select_matches_from_candidates(candidates)
        
        # Should select the two best matches without reusing players
        assert len(matches) == 2
        
        # Check that lead1-follow1 was selected (best score)
        match_ids = [(m[0].discord_user_id, m[1].discord_user_id) for m in matches]
        assert (1, 10) in match_ids
    
    def test_respects_mmr_windows(self, matchmaker):
        """Test that only valid pairs within MMR windows are considered"""
        lead_players = [Player(1, "l1", QueuePreferences(["bw_zerg"], [], 1, "l1"), 1500, None)]
        lead_players[0].wait_cycles = 0  # Tight MMR window
        
        follow_players = [
            Player(10, "f1", QueuePreferences(["sc2_terran"], [], 10, "f1"), None, 1520),  # Within window
            Player(11, "f2", QueuePreferences(["sc2_zerg"], [], 11, "f2"), None, 2000),    # Outside window
        ]
        
        matchmaker.players = lead_players + follow_players
        candidates = matchmaker._build_candidate_pairs(lead_players, follow_players, is_bw_match=True)
        
        # Should only include the close match
        candidate_follows = [c[2].discord_user_id for c in candidates]
        assert 10 in candidate_follows  # Close player included
        assert 11 not in candidate_follows  # Far player excluded


class TestLeastSquaresRefinement:
    """Test least-squares match refinement"""
    
    def test_improves_match_quality(self, matchmaker):
        """Test that refinement reduces squared error"""
        # Create matches with improvable quality
        p1_lead = Player(1, "l1", QueuePreferences(["bw_zerg"], [], 1, "l1"), 1500, None)
        p2_lead = Player(2, "l2", QueuePreferences(["bw_protoss"], [], 2, "l2"), 1600, None)
        p1_follow = Player(10, "f1", QueuePreferences(["sc2_terran"], [], 10, "f1"), None, 1610)
        p2_follow = Player(11, "f2", QueuePreferences(["sc2_zerg"], [], 11, "f2"), None, 1490)
        
        initial_matches = [(p1_lead, p1_follow), (p2_lead, p2_follow)]
        
        # Calculate initial error: (1500-1610)^2 + (1600-1490)^2 = 12100 + 12100 = 24200
        initial_error = (1500 - 1610) ** 2 + (1600 - 1490) ** 2
        
        # After swap: (1500-1490)^2 + (1600-1610)^2 = 100 + 100 = 200
        expected_error = (1500 - 1490) ** 2 + (1600 - 1610) ** 2
        
        assert expected_error < initial_error  # Swap should improve
        
        refined_matches = matchmaker._refine_matches_least_squares(initial_matches, is_bw_match=True)
        
        # Should have swapped follow players
        assert len(refined_matches) == 2
        # Check if swap occurred by verifying MMR differences improved
        refined_error = 0
        for lead, follow in refined_matches:
            lead_mmr = lead.bw_mmr
            follow_mmr = follow.sc2_mmr
            refined_error += (lead_mmr - follow_mmr) ** 2
        
        assert refined_error < initial_error
    
    def test_respects_mmr_windows_during_refinement(self, matchmaker):
        """Test that swaps respect MMR windows"""
        p1_lead = Player(1, "l1", QueuePreferences(["bw_zerg"], [], 1, "l1"), 1500, None)
        p1_lead.wait_cycles = 0  # Very tight window
        
        p2_lead = Player(2, "l2", QueuePreferences(["bw_protoss"], [], 2, "l2"), 1600, None)
        p2_lead.wait_cycles = 0
        
        # Use follow players within reasonable range
        p1_follow = Player(10, "f1", QueuePreferences(["sc2_terran"], [], 10, "f1"), None, 1510)
        p2_follow = Player(11, "f2", QueuePreferences(["sc2_zerg"], [], 11, "f2"), None, 1590)
        
        initial_matches = [(p1_lead, p1_follow), (p2_lead, p2_follow)]
        
        refined_matches = matchmaker._refine_matches_least_squares(initial_matches, is_bw_match=True)
        
        # Verify all matches still respect windows after refinement
        matchmaker.players = [p1_lead, p2_lead, p1_follow, p2_follow]  # Set for queue size
        for lead, follow in refined_matches:
            lead_mmr = lead.bw_mmr
            follow_mmr = follow.sc2_mmr
            max_diff = matchmaker.max_diff(lead.wait_cycles)
            assert abs(lead_mmr - follow_mmr) <= max_diff
    
    def test_handles_small_match_lists(self, matchmaker):
        """Test refinement handles edge cases"""
        # Empty list
        assert matchmaker._refine_matches_least_squares([], is_bw_match=True) == []
        
        # Single match
        p1 = Player(1, "l1", QueuePreferences(["bw_zerg"], [], 1, "l1"), 1500, None)
        p2 = Player(2, "f1", QueuePreferences(["sc2_terran"], [], 2, "f1"), None, 1520)
        single_match = [(p1, p2)]
        
        refined = matchmaker._refine_matches_least_squares(single_match, is_bw_match=True)
        assert len(refined) == 1
        assert refined[0] == single_match[0]


class TestPressureThresholds:
    """Test that new pressure thresholds work correctly"""
    
    def test_new_thresholds_trigger_correctly(self, matchmaker):
        """Test that balanced thresholds trigger correctly"""
        # Test low pressure (below 0.10)
        queue_size = 3
        effective_pop = 30
        pressure = matchmaker._calculate_queue_pressure(queue_size, effective_pop)
        
        # Should be 0.8 * 3 / 30 = 0.08 (below 0.10, so LOW)
        assert pressure < config.MM_MODERATE_PRESSURE_THRESHOLD
        
        # Test moderate pressure (0.10-0.20)
        queue_size = 5
        effective_pop = 30
        pressure = matchmaker._calculate_queue_pressure(queue_size, effective_pop)
        
        # Should be 0.8 * 5 / 30 = 0.133 (above 0.10, below 0.20, so MODERATE)
        assert pressure >= config.MM_MODERATE_PRESSURE_THRESHOLD
        assert pressure < config.MM_HIGH_PRESSURE_THRESHOLD
        
        # Test high pressure (above 0.20)
        queue_size = 10
        effective_pop = 30
        pressure = matchmaker._calculate_queue_pressure(queue_size, effective_pop)
        
        # Should be 0.8 * 10 / 30 = 0.267 (above 0.20, so HIGH)
        assert pressure >= config.MM_HIGH_PRESSURE_THRESHOLD
    
    def test_pressure_affects_mmr_windows(self, matchmaker):
        """Test that pressure changes MMR window parameters with balanced configuration"""
        matchmaker.players = [None] * 10  # Mock 10 players
        matchmaker.recent_activity = {i: 0 for i in range(30)}  # Mock 30 active
        
        # Pressure = 0.8 * 10 / 30 = 0.267, which is >= 0.20 (HIGH threshold)
        # Should use HIGH pressure params
        max_diff_0_cycles = matchmaker.max_diff(0)
        
        # Verify it uses HIGH params (75, 25)
        assert max_diff_0_cycles == config.MM_HIGH_PRESSURE_PARAMS[0]


class TestEndToEndOptimization:
    """Test the complete optimized matching flow"""
    
    def test_complete_matching_cycle(self, matchmaker):
        """Test a complete matching cycle with all optimizations"""
        # Create a realistic queue
        bw_players = [
            Player(i, f"bw{i}", QueuePreferences(["bw_zerg"], [], i, f"bw{i}"), 1500 + i*10, None)
            for i in range(3)
        ]
        sc2_players = [
            Player(i+10, f"sc2{i}", QueuePreferences(["sc2_terran"], [], i+10, f"sc2{i}"), None, 1500 + i*10)
            for i in range(3)
        ]
        both_players = [
            Player(20, "both1", QueuePreferences(["bw_protoss", "sc2_zerg"], [], 20, "both1"), 1600, 1400),
            Player(21, "both2", QueuePreferences(["bw_terran", "sc2_protoss"], [], 21, "both2"), 1400, 1600),
        ]
        
        all_players = bw_players + sc2_players + both_players
        
        # Categorize
        bw_only, sc2_only, both = matchmaker.categorize_players(all_players)
        
        # Equalize
        bw_list, sc2_list, remaining = matchmaker.equalize_lists(bw_only, sc2_only, both)
        
        # Should be balanced
        assert abs(len(bw_list) - len(sc2_list)) <= 1
        
        # Find matches
        matchmaker.players = all_players  # Set for queue size
        matchmaker.recent_activity = {p.discord_user_id: 0 for p in all_players}
        
        if len(bw_list) <= len(sc2_list):
            lead, follow = bw_list, sc2_list
            is_bw = True
        else:
            lead, follow = sc2_list, bw_list
            is_bw = False
        
        matches = matchmaker.find_matches(lead, follow, is_bw)
        
        # Should find some matches
        assert len(matches) > 0
        
        # Refine
        refined_matches = matchmaker._refine_matches_least_squares(matches, is_bw)
        
        # Should have same or better quality
        assert len(refined_matches) == len(matches)
        
        # Verify all matches are valid
        for p1, p2 in refined_matches:
            assert p1 != p2
            assert p1.discord_user_id != p2.discord_user_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

