"""
Test the fix for the basic case where only both-races players are in queue.

This test verifies that players with both BW and SC2 races can be matched
when there are no BW-only or SC2-only players in the queue.
"""

import pytest
from src.backend.services.matchmaking_service import (
    Matchmaker, Player, QueuePreferences
)


class TestBothRacesFix:
    """Test the fix for both-races players matching."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.matchmaker = Matchmaker()
    
    def test_both_races_only_matching(self):
        """Test that players with both races can be matched when no BW-only or SC2-only players exist."""
        # Create two players with both BW and SC2 races
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
        
        # Test categorization
        bw_only, sc2_only, both_races = self.matchmaker.categorize_players()
        
        assert len(bw_only) == 0
        assert len(sc2_only) == 0
        assert len(both_races) == 2
        
        # Test equalization - this should distribute both players
        bw_list, sc2_list, remaining_z = self.matchmaker.equalize_lists(bw_only, sc2_only, both_races)
        
        # Should have distributed the players
        assert len(bw_list) == 1
        assert len(sc2_list) == 1
        assert len(remaining_z) == 0
        
        # Test lead side selection
        if len(bw_list) <= len(sc2_list):
            lead_side, follow_side = bw_list, sc2_list
            is_bw_match = True
        else:
            lead_side, follow_side = sc2_list, bw_list
            is_bw_match = False
        
        # Should be able to find matches
        matches = self.matchmaker.find_matches(lead_side, follow_side, is_bw_match)
        
        # Should find a match
        assert len(matches) == 1
        
        # Verify the match is valid
        p1, p2 = matches[0]
        assert p1.discord_user_id != p2.discord_user_id
        assert p1.discord_user_id in [1, 2]
        assert p2.discord_user_id in [1, 2]
    
    def test_mixed_scenario(self):
        """Test a mixed scenario with some BW-only, SC2-only, and both-races players."""
        # Create mixed player set
        bw_player = Player(
            discord_user_id=1,
            user_id="BWPlayer",
            preferences=QueuePreferences(
                selected_races=["bw_terran"],
                vetoed_maps=[],
                discord_user_id=1,
                user_id="BWPlayer"
            ),
            bw_mmr=1500
        )
        
        sc2_player = Player(
            discord_user_id=2,
            user_id="SC2Player",
            preferences=QueuePreferences(
                selected_races=["sc2_zerg"],
                vetoed_maps=[],
                discord_user_id=2,
                user_id="SC2Player"
            ),
            sc2_mmr=1600
        )
        
        both_player1 = Player(
            discord_user_id=3,
            user_id="BothPlayer1",
            preferences=QueuePreferences(
                selected_races=["bw_protoss", "sc2_terran"],
                vetoed_maps=[],
                discord_user_id=3,
                user_id="BothPlayer1"
            ),
            bw_mmr=1400,
            sc2_mmr=1700
        )
        
        both_player2 = Player(
            discord_user_id=4,
            user_id="BothPlayer2",
            preferences=QueuePreferences(
                selected_races=["bw_zerg", "sc2_protoss"],
                vetoed_maps=[],
                discord_user_id=4,
                user_id="BothPlayer2"
            ),
            bw_mmr=1300,
            sc2_mmr=1800
        )
        
        # Add all players
        self.matchmaker.players = [bw_player, sc2_player, both_player1, both_player2]
        
        # Test categorization
        bw_only, sc2_only, both_races = self.matchmaker.categorize_players()
        
        assert len(bw_only) == 1
        assert len(sc2_only) == 1
        assert len(both_races) == 2
        
        # Test equalization
        bw_list, sc2_list, remaining_z = self.matchmaker.equalize_lists(bw_only, sc2_only, both_races)
        
        # Should equalize to 2 each
        assert len(bw_list) == 2
        assert len(sc2_list) == 2
        assert len(remaining_z) == 0
        
        # Test matching
        if len(bw_list) <= len(sc2_list):
            lead_side, follow_side = bw_list, sc2_list
            is_bw_match = True
        else:
            lead_side, follow_side = sc2_list, bw_list
            is_bw_match = False
        
        matches = self.matchmaker.find_matches(lead_side, follow_side, is_bw_match)
        
        # Should find matches
        assert len(matches) >= 0
        
        # Verify all matches are valid
        matched_players = set()
        for p1, p2 in matches:
            assert p1.discord_user_id != p2.discord_user_id
            assert p1.discord_user_id not in matched_players
            assert p2.discord_user_id not in matched_players
            matched_players.add(p1.discord_user_id)
            matched_players.add(p2.discord_user_id)
    
    def test_edge_case_empty_lists(self):
        """Test edge case where all lists are empty."""
        bw_only, sc2_only, both_races = [], [], []
        
        bw_list, sc2_list, remaining_z = self.matchmaker.equalize_lists(bw_only, sc2_only, both_races)
        
        assert len(bw_list) == 0
        assert len(sc2_list) == 0
        assert len(remaining_z) == 0
    
    def test_edge_case_only_one_both_player(self):
        """Test edge case where there's only one both-races player."""
        both_player = Player(
            discord_user_id=1,
            user_id="BothPlayer",
            preferences=QueuePreferences(
                selected_races=["bw_terran", "sc2_zerg"],
                vetoed_maps=[],
                discord_user_id=1,
                user_id="BothPlayer"
            ),
            bw_mmr=1500,
            sc2_mmr=1600
        )
        
        bw_only, sc2_only, both_races = [], [], [both_player]
        
        bw_list, sc2_list, remaining_z = self.matchmaker.equalize_lists(bw_only, sc2_only, both_races)
        
        # Should distribute the single player
        assert len(bw_list) == 1
        assert len(sc2_list) == 0
        assert len(remaining_z) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
