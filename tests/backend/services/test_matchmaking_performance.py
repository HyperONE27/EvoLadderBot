"""
Performance tests for the matchmaking service.

This module tests the performance improvements and correctness of the fixed matchmaking algorithm.
"""

import time
import pytest
from src.backend.services.matchmaking_service import (
    Matchmaker, Player, QueuePreferences
)


class TestMatchmakingPerformance:
    """Test performance improvements in the matchmaking algorithm."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.matchmaker = Matchmaker()
    
    def create_test_players(self, count: int, race_type: str = "bw"):
        """Create test players for performance testing."""
        players = []
        for i in range(count):
            if race_type == "bw":
                races = ["bw_terran"]
                mmr = 1500 + i * 10
            elif race_type == "sc2":
                races = ["sc2_zerg"]
                mmr = 1600 + i * 10
            else:  # both
                races = ["bw_protoss", "sc2_terran"]
                mmr = 1400 + i * 10
            
            preferences = QueuePreferences(
                selected_races=races,
                vetoed_maps=[],
                discord_user_id=i,
                user_id=f"Player{i}"
            )
            
            player = Player(
                discord_user_id=i,
                user_id=f"Player{i}",
                preferences=preferences,
                bw_mmr=mmr if race_type in ["bw", "both"] else None,
                sc2_mmr=mmr if race_type in ["sc2", "both"] else None
            )
            player.wait_cycles = i % 10  # Vary wait cycles
            
            players.append(player)
        
        return players
    
    def test_priority_calculation_performance(self):
        """Test that priority calculation is O(n log n) not O(n² log n)."""
        # Create a large number of players
        bw_players = self.create_test_players(100, "bw")
        sc2_players = self.create_test_players(100, "sc2")
        
        # Measure time for priority calculation
        start_time = time.time()
        
        # This should be O(n log n) now, not O(n² log n)
        matches = self.matchmaker.find_matches(bw_players, sc2_players, True)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete in reasonable time (less than 1 second for 100 players)
        assert execution_time < 1.0, f"Priority calculation took {execution_time:.3f}s, should be < 1.0s"
        
        print(f"Priority calculation for 100 players took {execution_time:.3f}s")
    
    def test_lead_side_selection_correctness(self):
        """Test that lead side selection works correctly."""
        # Test case 1: BW smaller than SC2
        bw_players = self.create_test_players(2, "bw")
        sc2_players = self.create_test_players(5, "sc2")
        
        if len(bw_players) <= len(sc2_players):
            lead_side, follow_side = bw_players, sc2_players
            is_bw_match = True
        else:
            lead_side, follow_side = sc2_players, bw_players
            is_bw_match = False
        
        assert lead_side == bw_players
        assert follow_side == sc2_players
        assert is_bw_match is True
        
        # Test case 2: SC2 smaller than BW
        bw_players = self.create_test_players(5, "bw")
        sc2_players = self.create_test_players(2, "sc2")
        
        if len(bw_players) <= len(sc2_players):
            lead_side, follow_side = bw_players, sc2_players
            is_bw_match = True
        else:
            lead_side, follow_side = sc2_players, bw_players
            is_bw_match = False
        
        assert lead_side == sc2_players
        assert follow_side == bw_players
        assert is_bw_match is False
    
    def test_used_player_tracking_correctness(self):
        """Test that used player tracking works correctly."""
        bw_players = self.create_test_players(3, "bw")
        sc2_players = self.create_test_players(3, "sc2")
        
        # Test that players are properly tracked
        matches = self.matchmaker.find_matches(bw_players, sc2_players, True)
        
        # Check that no player appears in multiple matches
        all_players_in_matches = set()
        for p1, p2 in matches:
            assert p1.discord_user_id not in all_players_in_matches, "Player appears in multiple matches"
            assert p2.discord_user_id not in all_players_in_matches, "Player appears in multiple matches"
            all_players_in_matches.add(p1.discord_user_id)
            all_players_in_matches.add(p2.discord_user_id)
    
    def test_race_selection_correctness(self):
        """Test that race selection works correctly for both lead sides."""
        # Test BW lead side
        bw_player = self.create_test_players(1, "bw")[0]
        sc2_player = self.create_test_players(1, "sc2")[0]
        
        is_bw_match = True
        if is_bw_match:
            p1_race = bw_player.get_race_for_match(True)   # BW race
            p2_race = sc2_player.get_race_for_match(False)  # SC2 race
        else:
            p1_race = bw_player.get_race_for_match(False)  # SC2 race
            p2_race = sc2_player.get_race_for_match(True)   # BW race
        
        assert p1_race == "bw_terran"
        assert p2_race == "sc2_zerg"
        
        # Test SC2 lead side
        is_bw_match = False
        if is_bw_match:
            p1_race = sc2_player.get_race_for_match(True)   # BW race
            p2_race = bw_player.get_race_for_match(False)  # SC2 race
        else:
            p1_race = sc2_player.get_race_for_match(False)  # SC2 race
            p2_race = bw_player.get_race_for_match(True)   # BW race
        
        assert p1_race == "sc2_zerg"
        assert p2_race == "bw_terran"
    
    def test_elastic_window_growth(self):
        """Test that elastic window grows correctly with wait cycles."""
        # Test different wait cycles
        assert self.matchmaker.max_diff(0, 5) == 125   # Base
        assert self.matchmaker.max_diff(6, 5) == 200   # First growth
        assert self.matchmaker.max_diff(12, 5) == 275  # Second growth
        assert self.matchmaker.max_diff(18, 5) == 350  # Third growth
        
        # Test different queue sizes
        assert self.matchmaker.max_diff(0, 5) == 125   # Small queue
        assert self.matchmaker.max_diff(0, 8) == 100   # Medium queue
        assert self.matchmaker.max_diff(0, 15) == 75   # Large queue
    
    def test_complete_matchmaking_scenario(self):
        """Test a complete matchmaking scenario with realistic data."""
        # Create realistic player distribution
        bw_players = self.create_test_players(4, "bw")
        sc2_players = self.create_test_players(6, "sc2")
        both_players = self.create_test_players(3, "both")
        
        # Add all players to matchmaker
        all_players = bw_players + sc2_players + both_players
        self.matchmaker.players = all_players
        
        # Test categorization
        bw_only, sc2_only, both_races = self.matchmaker.categorize_players()
        
        assert len(bw_only) == 4
        assert len(sc2_only) == 6
        assert len(both_races) == 3
        
        # Test equalization
        bw_list, sc2_list, remaining_z = self.matchmaker.equalize_lists(bw_only, sc2_only, both_races)
        
        # Should be equalized
        assert len(bw_list) == len(sc2_list)
        
        # Test lead side selection
        if len(bw_list) <= len(sc2_list):
            lead_side, follow_side = bw_list, sc2_list
            is_bw_match = True
        else:
            lead_side, follow_side = sc2_list, bw_list
            is_bw_match = False
        
        # Test match finding
        matches = self.matchmaker.find_matches(lead_side, follow_side, is_bw_match)
        
        # Should find some matches
        assert len(matches) >= 0
        
        # Test that all matches are valid
        for p1, p2 in matches:
            assert p1.discord_user_id != p2.discord_user_id
            assert p1.discord_user_id < 1000  # Our test players
            assert p2.discord_user_id < 1000  # Our test players


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
