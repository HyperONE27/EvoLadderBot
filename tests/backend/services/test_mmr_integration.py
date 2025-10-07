"""
Test MMR calculation and database integration.

This module tests that MMR values are properly calculated and updated
in the database when match results are recorded.
"""

import pytest
import json
from unittest.mock import Mock, patch
from src.backend.services.matchmaking_service import Matchmaker
from src.backend.services.mmr_service import MMRService
from src.backend.db.db_reader_writer import DatabaseReader, DatabaseWriter


class TestMMRIntegration:
    """Test MMR calculation and database integration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.matchmaker = Matchmaker()
        self.mmr_service = MMRService()
        self.db_reader = DatabaseReader()
        self.db_writer = DatabaseWriter()
    
    def test_mmr_calculation_basic(self):
        """Test basic MMR calculation."""
        # Test MMR calculation for different scenarios
        p1_mmr = 1500.0
        p2_mmr = 1500.0
        
        # Test player 1 win
        outcome_1 = self.mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, 1)
        assert outcome_1.player_one_mmr > p1_mmr  # Player 1 should gain MMR
        assert outcome_1.player_two_mmr < p2_mmr  # Player 2 should lose MMR
        
        # Test player 2 win
        outcome_2 = self.mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, 2)
        assert outcome_2.player_one_mmr < p1_mmr  # Player 1 should lose MMR
        assert outcome_2.player_two_mmr > p2_mmr  # Player 2 should gain MMR
        
        # Test draw
        outcome_draw = self.mmr_service.calculate_new_mmr(p1_mmr, p2_mmr, 0)
        assert abs(outcome_draw.player_one_mmr - p1_mmr) < 1  # Minimal change for draw
        assert abs(outcome_draw.player_two_mmr - p2_mmr) < 1  # Minimal change for draw
        
        print(f"✅ MMR calculation working correctly")
        print(f"   P1 Win: {p1_mmr} → {outcome_1.player_one_mmr:.1f}")
        print(f"   P2 Win: {p1_mmr} → {outcome_2.player_one_mmr:.1f}")
        print(f"   Draw: {p1_mmr} → {outcome_draw.player_one_mmr:.1f}")
    
    def test_mmr_calculation_skill_difference(self):
        """Test MMR calculation with different skill levels."""
        # High skill vs low skill
        high_mmr = 2000.0
        low_mmr = 1000.0
        
        # High skill player wins (expected)
        outcome_expected = self.mmr_service.calculate_new_mmr(high_mmr, low_mmr, 1)
        high_gain = outcome_expected.player_one_mmr - high_mmr
        low_loss = low_mmr - outcome_expected.player_two_mmr
        
        # High skill player loses (upset)
        outcome_upset = self.mmr_service.calculate_new_mmr(high_mmr, low_mmr, 2)
        high_loss = high_mmr - outcome_upset.player_one_mmr
        low_gain = outcome_upset.player_two_mmr - low_mmr
        
        # Expected win should have smaller MMR changes
        assert abs(high_gain) < abs(high_loss)
        assert abs(low_loss) < abs(low_gain)
        
        print(f"✅ Skill difference MMR calculation working correctly")
        print(f"   Expected win: High +{high_gain:.1f}, Low -{low_loss:.1f}")
        print(f"   Upset win: High -{high_loss:.1f}, Low +{low_gain:.1f}")
    
    def test_database_mmr_update_simulation(self):
        """Test the database MMR update process."""
        # Simulate the process from record_match_result
        discord_uid_1 = 12345
        discord_uid_2 = 67890
        race_1 = "bw_terran"
        race_2 = "sc2_zerg"
        
        # Set up initial MMR values
        initial_mmr_1 = 1500
        initial_mmr_2 = 1600
        
        # Create initial MMR records
        self.db_writer.create_or_update_mmr_1v1(
            discord_uid_1, f"Player{discord_uid_1}", race_1, initial_mmr_1,
            games_played=10, games_won=5, games_lost=5, games_drawn=0
        )
        
        self.db_writer.create_or_update_mmr_1v1(
            discord_uid_2, f"Player{discord_uid_2}", race_2, initial_mmr_2,
            games_played=8, games_won=6, games_lost=2, games_drawn=0
        )
        
        # Simulate match result (Player 1 wins)
        result = 1  # Player 1 wins
        
        # Calculate new MMR values
        mmr_outcome = self.mmr_service.calculate_new_mmr(
            float(initial_mmr_1), float(initial_mmr_2), result
        )
        
        # Update MMR in database
        success_1 = self.db_writer.update_mmr_after_match(
            discord_uid_1, race_1, mmr_outcome.player_one_mmr,
            won=True, lost=False, drawn=False
        )
        
        success_2 = self.db_writer.update_mmr_after_match(
            discord_uid_2, race_2, mmr_outcome.player_two_mmr,
            won=False, lost=True, drawn=False
        )
        
        assert success_1 and success_2
        
        # Verify the updates
        updated_mmr_1 = self.db_reader.get_player_mmr_1v1(discord_uid_1, race_1)
        updated_mmr_2 = self.db_reader.get_player_mmr_1v1(discord_uid_2, race_2)
        
        assert updated_mmr_1 is not None
        assert updated_mmr_2 is not None
        assert updated_mmr_1['mmr'] == mmr_outcome.player_one_mmr
        assert updated_mmr_2['mmr'] == mmr_outcome.player_two_mmr
        
        # Check that game statistics were updated
        assert updated_mmr_1['games_played'] == 11  # 10 + 1
        assert updated_mmr_1['games_won'] == 6       # 5 + 1
        assert updated_mmr_1['games_lost'] == 5      # 5 + 0
        
        assert updated_mmr_2['games_played'] == 9   # 8 + 1
        assert updated_mmr_2['games_won'] == 6      # 6 + 0
        assert updated_mmr_2['games_lost'] == 3     # 2 + 1
        
        print(f"✅ Database MMR update working correctly")
        print(f"   Player 1: {initial_mmr_1} → {updated_mmr_1['mmr']} (won)")
        print(f"   Player 2: {initial_mmr_2} → {updated_mmr_2['mmr']} (lost)")
    
    def test_draw_result_mmr_update(self):
        """Test MMR update for draw results."""
        discord_uid_1 = 11111
        discord_uid_2 = 22222
        race_1 = "bw_protoss"
        race_2 = "sc2_terran"
        
        # Set up initial MMR values
        initial_mmr_1 = 1400
        initial_mmr_2 = 1500
        
        # Create initial MMR records
        self.db_writer.create_or_update_mmr_1v1(
            discord_uid_1, f"Player{discord_uid_1}", race_1, initial_mmr_1,
            games_played=5, games_won=2, games_lost=3, games_drawn=0
        )
        
        self.db_writer.create_or_update_mmr_1v1(
            discord_uid_2, f"Player{discord_uid_2}", race_2, initial_mmr_2,
            games_played=7, games_won=4, games_lost=3, games_drawn=0
        )
        
        # Simulate draw result
        result = 0  # Draw
        
        # Calculate new MMR values
        mmr_outcome = self.mmr_service.calculate_new_mmr(
            float(initial_mmr_1), float(initial_mmr_2), result
        )
        
        # Update MMR in database
        success_1 = self.db_writer.update_mmr_after_match(
            discord_uid_1, race_1, mmr_outcome.player_one_mmr,
            won=False, lost=False, drawn=True
        )
        
        success_2 = self.db_writer.update_mmr_after_match(
            discord_uid_2, race_2, mmr_outcome.player_two_mmr,
            won=False, lost=False, drawn=True
        )
        
        assert success_1 and success_2
        
        # Verify the updates
        updated_mmr_1 = self.db_reader.get_player_mmr_1v1(discord_uid_1, race_1)
        updated_mmr_2 = self.db_reader.get_player_mmr_1v1(discord_uid_2, race_2)
        
        assert updated_mmr_1 is not None
        assert updated_mmr_2 is not None
        
        # Check that game statistics were updated for draw
        assert updated_mmr_1['games_drawn'] == 1  # 0 + 1
        assert updated_mmr_2['games_drawn'] == 1  # 0 + 1
        
        print(f"✅ Draw result MMR update working correctly")
        print(f"   Player 1: {initial_mmr_1} → {updated_mmr_1['mmr']} (drawn)")
        print(f"   Player 2: {initial_mmr_2} → {updated_mmr_2['mmr']} (drawn)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
