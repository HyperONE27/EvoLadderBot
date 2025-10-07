"""
Integration test for the complete matchmaking flow.

This test simulates the real matchmaking process where players
start with wait_cycles=0 and gradually become matchable.
"""

import pytest
from src.backend.services.matchmaking_service import (
    Matchmaker, Player, QueuePreferences
)


class TestMatchmakingIntegration:
    """Test the complete matchmaking integration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.matchmaker = Matchmaker()
    
    def test_matchmaking_cycle_simulation(self):
        """Test multiple matchmaking cycles to simulate real behavior."""
        # Create two players with both races
        player1 = Player(
            discord_user_id=1,
            user_id="BothPlayer1",
            preferences=QueuePreferences(
                selected_races=["bw_terran", "sc2_zerg"],
                vetoed_maps=[],
                discord_user_id=1,
                user_id="BothPlayer1"
            ),
            bw_mmr=1500,
            sc2_mmr=1600
        )
        
        player2 = Player(
            discord_user_id=2,
            user_id="BothPlayer2",
            preferences=QueuePreferences(
                selected_races=["bw_protoss", "sc2_terran"],
                vetoed_maps=[],
                discord_user_id=2,
                user_id="BothPlayer2"
            ),
            bw_mmr=1400,
            sc2_mmr=1700
        )
        
        # Add players to matchmaker
        self.matchmaker.players = [player1, player2]
        
        # Simulate multiple matchmaking cycles
        for cycle in range(10):
            print(f"\n--- Cycle {cycle} ---")
            
            # Increment wait cycles (this happens in attempt_match)
            for player in self.matchmaker.players:
                player.wait_cycles += 1
            
            # Test categorization
            bw_only, sc2_only, both_races = self.matchmaker.categorize_players()
            print(f"Categorization: BW={len(bw_only)}, SC2={len(sc2_only)}, Both={len(both_races)}")
            
            # Test equalization
            bw_list, sc2_list, remaining_z = self.matchmaker.equalize_lists(bw_only, sc2_only, both_races)
            print(f"After equalization: BW={len(bw_list)}, SC2={len(sc2_list)}, Remaining Z={len(remaining_z)}")
            
            # Test lead side selection
            if len(bw_list) <= len(sc2_list):
                lead_side, follow_side = bw_list, sc2_list
                is_bw_match = True
            else:
                lead_side, follow_side = sc2_list, bw_list
                is_bw_match = False
            
            print(f"Lead side: {len(lead_side)}, Follow side: {len(follow_side)}, is_bw_match: {is_bw_match}")
            
            # Test matching
            matches = self.matchmaker.find_matches(lead_side, follow_side, is_bw_match)
            print(f"Matches found: {len(matches)}")
            
            # Debug MMR differences
            if lead_side and follow_side:
                lead_mmr = lead_side[0].get_effective_mmr(is_bw_match) or 0
                follow_mmr = follow_side[0].get_effective_mmr(not is_bw_match) or 0
                mmr_diff = abs(lead_mmr - follow_mmr)
                max_diff = self.matchmaker.max_diff(lead_side[0].wait_cycles, len(self.matchmaker.players))
                print(f"MMR difference: {mmr_diff}, max_diff: {max_diff}")
                
                if mmr_diff <= max_diff:
                    print("✅ Players should be matchable!")
                else:
                    print("❌ Players not matchable yet")
            
            # If we found matches, break
            if matches:
                print(f"🎉 Match found in cycle {cycle}!")
                break
        
        # Should eventually find a match
        assert len(matches) > 0, "Players should be matchable after sufficient wait cycles"
    
    def test_close_mmr_players_match_immediately(self):
        """Test that players with close MMRs match immediately."""
        # Create players with very close MMRs
        player1 = Player(
            discord_user_id=1,
            user_id="ClosePlayer1",
            preferences=QueuePreferences(
                selected_races=["bw_terran", "sc2_zerg"],
                vetoed_maps=[],
                discord_user_id=1,
                user_id="ClosePlayer1"
            ),
            bw_mmr=1500,
            sc2_mmr=1600
        )
        
        player2 = Player(
            discord_user_id=2,
            user_id="ClosePlayer2",
            preferences=QueuePreferences(
                selected_races=["bw_protoss", "sc2_terran"],
                vetoed_maps=[],
                discord_user_id=2,
                user_id="ClosePlayer2"
            ),
            bw_mmr=1505,  # Very close MMR
            sc2_mmr=1605   # Very close MMR
        )
        
        # Add players to matchmaker
        self.matchmaker.players = [player1, player2]
        
        # Test categorization
        bw_only, sc2_only, both_races = self.matchmaker.categorize_players()
        
        # Test equalization
        bw_list, sc2_list, remaining_z = self.matchmaker.equalize_lists(bw_only, sc2_only, both_races)
        
        # Test lead side selection
        if len(bw_list) <= len(sc2_list):
            lead_side, follow_side = bw_list, sc2_list
            is_bw_match = True
        else:
            lead_side, follow_side = sc2_list, bw_list
            is_bw_match = False
        
        # Test matching
        matches = self.matchmaker.find_matches(lead_side, follow_side, is_bw_match)
        
        # Should match immediately due to close MMRs
        assert len(matches) == 1, "Close MMR players should match immediately"
    
    def test_elastic_window_growth(self):
        """Test that elastic window grows correctly over time."""
        # Test different wait cycles
        test_cases = [
            (0, 2, 125),   # Base case
            (6, 2, 200),   # First growth
            (12, 2, 275),  # Second growth
            (18, 2, 350),  # Third growth
        ]
        
        for wait_cycles, queue_size, expected_max_diff in test_cases:
            actual_max_diff = self.matchmaker.max_diff(wait_cycles, queue_size)
            assert actual_max_diff == expected_max_diff, f"Expected {expected_max_diff}, got {actual_max_diff} for wait_cycles={wait_cycles}, queue_size={queue_size}"
    
    def test_different_queue_sizes(self):
        """Test elastic window with different queue sizes."""
        # Test different queue sizes
        test_cases = [
            (0, 5, 125),   # Small queue
            (0, 8, 100),   # Medium queue
            (0, 15, 75),   # Large queue
        ]
        
        for wait_cycles, queue_size, expected_max_diff in test_cases:
            actual_max_diff = self.matchmaker.max_diff(wait_cycles, queue_size)
            assert actual_max_diff == expected_max_diff, f"Expected {expected_max_diff}, got {actual_max_diff} for wait_cycles={wait_cycles}, queue_size={queue_size}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
