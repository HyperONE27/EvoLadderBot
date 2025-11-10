"""
Tests for matchmaking priority-based pre-filtering.

This module tests the priority filtering feature that prevents fresh players
from "stealing" matches from long-waiting veterans by filtering excess players
based on wait_cycles before matching begins.
"""

import pytest
from src.backend.services.matchmaking_service import (
    Matchmaker, Player, QueuePreferences
)


def create_player(user_id: str, discord_id: int, bw_mmr: int = None, 
                  sc2_mmr: int = None, wait_cycles: int = 0) -> Player:
    """Helper to create a test player."""
    races = []
    if bw_mmr is not None:
        races.append("bw_terran")
    if sc2_mmr is not None:
        races.append("sc2_zerg")
    
    preferences = QueuePreferences(
        selected_races=races,
        vetoed_maps=[],
        discord_user_id=discord_id,
        user_id=user_id
    )
    
    player = Player(
        discord_user_id=discord_id,
        user_id=user_id,
        preferences=preferences,
        bw_mmr=bw_mmr,
        sc2_mmr=sc2_mmr
    )
    player.wait_cycles = wait_cycles
    return player


class TestPriorityFiltering:
    """Test the priority-based pre-filtering functionality."""
    
    def test_equal_sides_no_filtering(self):
        """Test that no filtering occurs when both sides are equal."""
        matchmaker = Matchmaker()
        
        # Create equal sides (2 vs 2)
        lead_side = [
            create_player("Lead1", 1001, bw_mmr=1500, wait_cycles=0),
            create_player("Lead2", 1002, bw_mmr=1600, wait_cycles=2),
        ]
        follow_side = [
            create_player("Follow1", 2001, sc2_mmr=1550, wait_cycles=5),
            create_player("Follow2", 2002, sc2_mmr=1650, wait_cycles=1),
        ]
        
        filtered_lead, filtered_follow = matchmaker._filter_by_priority(lead_side, follow_side)
        
        # No filtering should occur
        assert len(filtered_lead) == 2
        assert len(filtered_follow) == 2
        assert filtered_lead == lead_side
        assert filtered_follow == follow_side
    
    def test_follow_side_excess_filters_low_priority(self):
        """Test that low-priority follow players are filtered when follow side is larger."""
        matchmaker = Matchmaker()
        
        # Lead has 1, Follow has 3 (excess of 2)
        lead_side = [
            create_player("Lead1", 1001, bw_mmr=1500, wait_cycles=0),
        ]
        follow_side = [
            create_player("Veteran", 2001, sc2_mmr=1700, wait_cycles=10),  # Highest priority
            create_player("MidPriority", 2002, sc2_mmr=1650, wait_cycles=5),
            create_player("Fresh", 2003, sc2_mmr=1550, wait_cycles=0),  # Lowest priority
        ]
        
        filtered_lead, filtered_follow = matchmaker._filter_by_priority(lead_side, follow_side)
        
        # Lead side unchanged
        assert len(filtered_lead) == 1
        assert filtered_lead[0].user_id == "Lead1"
        
        # Follow side filtered to match lead count (1)
        assert len(filtered_follow) == 1
        # Highest priority player should be kept
        assert filtered_follow[0].user_id == "Veteran"
        assert filtered_follow[0].wait_cycles == 10
    
    def test_lead_side_excess_filters_low_priority(self):
        """Test that low-priority lead players are filtered when lead side is larger."""
        matchmaker = Matchmaker()
        
        # Lead has 3, Follow has 1 (excess of 2)
        lead_side = [
            create_player("LeadVeteran", 1001, bw_mmr=1500, wait_cycles=8),  # Highest priority
            create_player("LeadMid", 1002, bw_mmr=1600, wait_cycles=3),
            create_player("LeadFresh", 1003, bw_mmr=1550, wait_cycles=0),  # Lowest priority
        ]
        follow_side = [
            create_player("Follow1", 2001, sc2_mmr=1550, wait_cycles=0),
        ]
        
        filtered_lead, filtered_follow = matchmaker._filter_by_priority(lead_side, follow_side)
        
        # Lead side filtered to match follow count (1)
        assert len(filtered_lead) == 1
        # Highest priority player should be kept
        assert filtered_lead[0].user_id == "LeadVeteran"
        assert filtered_lead[0].wait_cycles == 8
        
        # Follow side unchanged
        assert len(filtered_follow) == 1
        assert filtered_follow[0].user_id == "Follow1"
    
    def test_multiple_excess_keeps_top_priority_players(self):
        """Test filtering with multiple excess players keeps all top priority players."""
        matchmaker = Matchmaker()
        
        # Lead has 2, Follow has 5 (excess of 3)
        lead_side = [
            create_player("Lead1", 1001, bw_mmr=1500, wait_cycles=0),
            create_player("Lead2", 1002, bw_mmr=1600, wait_cycles=2),
        ]
        follow_side = [
            create_player("Follow1", 2001, sc2_mmr=1700, wait_cycles=10),  # Top 1
            create_player("Follow2", 2002, sc2_mmr=1650, wait_cycles=7),   # Top 2
            create_player("Follow3", 2003, sc2_mmr=1550, wait_cycles=3),
            create_player("Follow4", 2004, sc2_mmr=1600, wait_cycles=1),
            create_player("Follow5", 2005, sc2_mmr=1580, wait_cycles=0),
        ]
        
        filtered_lead, filtered_follow = matchmaker._filter_by_priority(lead_side, follow_side)
        
        # Lead unchanged
        assert len(filtered_lead) == 2
        
        # Follow filtered to top 2
        assert len(filtered_follow) == 2
        filtered_ids = {p.user_id for p in filtered_follow}
        assert "Follow1" in filtered_ids  # 10 cycles
        assert "Follow2" in filtered_ids  # 7 cycles
        assert "Follow3" not in filtered_ids  # Filtered out
        assert "Follow4" not in filtered_ids  # Filtered out
        assert "Follow5" not in filtered_ids  # Filtered out
    
    def test_ties_in_wait_cycles_stable_sort(self):
        """Test behavior when multiple players have same wait_cycles."""
        matchmaker = Matchmaker()
        
        # Lead has 1, Follow has 3 with tie in wait_cycles
        lead_side = [
            create_player("Lead1", 1001, bw_mmr=1500, wait_cycles=0),
        ]
        follow_side = [
            create_player("Follow1", 2001, sc2_mmr=1700, wait_cycles=5),
            create_player("Follow2", 2002, sc2_mmr=1650, wait_cycles=5),  # Same priority
            create_player("Follow3", 2003, sc2_mmr=1550, wait_cycles=0),
        ]
        
        filtered_lead, filtered_follow = matchmaker._filter_by_priority(lead_side, follow_side)
        
        # Should keep 1 follow player
        assert len(filtered_follow) == 1
        # Should be one of the 5-cycle players (stable sort, first one encountered)
        assert filtered_follow[0].wait_cycles == 5
        assert filtered_follow[0].user_id in ["Follow1", "Follow2"]
    
    def test_integration_with_matching_scenario(self):
        """Test the actual problem scenario that priority filtering solves."""
        matchmaker = Matchmaker()
        
        # The problematic scenario:
        # Lead has 1 player at 1500 MMR with 0 cycles
        # Follow has 2 players: 1700 MMR with 10 cycles, and 1550 MMR with 0 cycles
        # Without filtering, the 1550 MMR player would match (better fit)
        # With filtering, the veteran (10 cycles) gets first consideration
        
        lead_side = [
            create_player("Alice", 1001, bw_mmr=1500, wait_cycles=0),
        ]
        follow_side = [
            create_player("Bob", 2001, sc2_mmr=1700, wait_cycles=10),  # Veteran
            create_player("Carol", 2002, sc2_mmr=1550, wait_cycles=0),  # Fresh
        ]
        
        # Apply priority filtering
        filtered_lead, filtered_follow = matchmaker._filter_by_priority(lead_side, follow_side)
        
        # Verify veteran is kept
        assert len(filtered_follow) == 1
        assert filtered_follow[0].user_id == "Bob"
        assert filtered_follow[0].wait_cycles == 10
        
        # Carol should be filtered out
        assert "Carol" not in [p.user_id for p in filtered_follow]
    
    def test_all_players_same_priority(self):
        """Test behavior when all excess players have same priority."""
        matchmaker = Matchmaker()
        
        lead_side = [
            create_player("Lead1", 1001, bw_mmr=1500, wait_cycles=0),
        ]
        follow_side = [
            create_player("Follow1", 2001, sc2_mmr=1700, wait_cycles=5),
            create_player("Follow2", 2002, sc2_mmr=1650, wait_cycles=5),
            create_player("Follow3", 2003, sc2_mmr=1550, wait_cycles=5),
        ]
        
        filtered_lead, filtered_follow = matchmaker._filter_by_priority(lead_side, follow_side)
        
        # Should keep 1 player
        assert len(filtered_follow) == 1
        # All have same priority, so stable sort keeps first
        assert filtered_follow[0].wait_cycles == 5
    
    def test_zero_wait_cycles_all_filtered(self):
        """Test that all zero-priority players can be filtered if higher priority exists."""
        matchmaker = Matchmaker()
        
        lead_side = [
            create_player("Lead1", 1001, bw_mmr=1500, wait_cycles=0),
        ]
        follow_side = [
            create_player("Veteran", 2001, sc2_mmr=1700, wait_cycles=1),  # Slightly higher
            create_player("Fresh1", 2002, sc2_mmr=1650, wait_cycles=0),
            create_player("Fresh2", 2003, sc2_mmr=1550, wait_cycles=0),
        ]
        
        filtered_lead, filtered_follow = matchmaker._filter_by_priority(lead_side, follow_side)
        
        # Should keep the veteran
        assert len(filtered_follow) == 1
        assert filtered_follow[0].user_id == "Veteran"
        assert filtered_follow[0].wait_cycles == 1
        
        # Both fresh players filtered
        filtered_ids = [p.user_id for p in filtered_follow]
        assert "Fresh1" not in filtered_ids
        assert "Fresh2" not in filtered_ids
    
    def test_filtering_preserves_player_objects(self):
        """Test that filtering returns the same player objects, not copies."""
        matchmaker = Matchmaker()
        
        lead_side = [
            create_player("Lead1", 1001, bw_mmr=1500, wait_cycles=0),
        ]
        veteran = create_player("Veteran", 2001, sc2_mmr=1700, wait_cycles=10)
        fresh = create_player("Fresh", 2002, sc2_mmr=1550, wait_cycles=0)
        follow_side = [veteran, fresh]
        
        filtered_lead, filtered_follow = matchmaker._filter_by_priority(lead_side, follow_side)
        
        # Should be the exact same object (not a copy)
        assert filtered_follow[0] is veteran
        assert filtered_lead[0] is lead_side[0]


class TestPriorityFilteringEdgeCases:
    """Test edge cases for priority filtering."""
    
    def test_empty_lead_side(self):
        """Test behavior with empty lead side."""
        matchmaker = Matchmaker()
        
        lead_side = []
        follow_side = [
            create_player("Follow1", 2001, sc2_mmr=1700, wait_cycles=5),
        ]
        
        filtered_lead, filtered_follow = matchmaker._filter_by_priority(lead_side, follow_side)
        
        # Both should be empty (can't match with 0 on one side)
        assert len(filtered_lead) == 0
        assert len(filtered_follow) == 0
    
    def test_empty_follow_side(self):
        """Test behavior with empty follow side."""
        matchmaker = Matchmaker()
        
        lead_side = [
            create_player("Lead1", 1001, bw_mmr=1500, wait_cycles=0),
        ]
        follow_side = []
        
        filtered_lead, filtered_follow = matchmaker._filter_by_priority(lead_side, follow_side)
        
        # Both should be empty (can't match with 0 on one side)
        assert len(filtered_lead) == 0
        assert len(filtered_follow) == 0
    
    def test_both_sides_empty(self):
        """Test behavior with both sides empty."""
        matchmaker = Matchmaker()
        
        lead_side = []
        follow_side = []
        
        filtered_lead, filtered_follow = matchmaker._filter_by_priority(lead_side, follow_side)
        
        assert len(filtered_lead) == 0
        assert len(filtered_follow) == 0
    
    def test_large_excess(self):
        """Test filtering with very large excess (10 vs 1)."""
        matchmaker = Matchmaker()
        
        lead_side = [
            create_player("Lead1", 1001, bw_mmr=1500, wait_cycles=0),
        ]
        follow_side = [
            create_player(f"Follow{i}", 2000+i, sc2_mmr=1500+i*10, wait_cycles=10-i)
            for i in range(10)
        ]
        
        filtered_lead, filtered_follow = matchmaker._filter_by_priority(lead_side, follow_side)
        
        # Should keep only 1 follow player (the one with highest wait_cycles)
        assert len(filtered_follow) == 1
        assert filtered_follow[0].wait_cycles == 10
        assert filtered_follow[0].user_id == "Follow0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

