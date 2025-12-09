"""
Test preferences writing functionality.

This module tests that user preferences are properly written to the database.
"""

import pytest
import json
from unittest.mock import Mock, patch
from src.backend.db.db_reader_writer import DatabaseWriter


class TestPreferencesWriting:
    """Test preferences writing to database."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.db_writer = DatabaseWriter()
    
    def test_update_preferences_both_fields(self):
        """Test updating preferences with both races and vetoes."""
        discord_uid = 12345
        races = ["bw_terran", "sc2_zerg"]
        vetoes = ["Arkanoid", "Khione"]
        
        races_payload = json.dumps(races)
        vetoes_payload = json.dumps(vetoes)
        
        # Test the method
        result = self.db_writer.update_preferences_1v1(
            discord_uid=discord_uid,
            last_chosen_races=races_payload,
            last_chosen_vetoes=vetoes_payload
        )
        
        assert result is True
        print(f"✅ Updated preferences for user {discord_uid}")
        print(f"   Races: {races_payload}")
        print(f"   Vetoes: {vetoes_payload}")
    
    def test_update_preferences_races_only(self):
        """Test updating preferences with races only."""
        discord_uid = 67890
        races = ["bw_protoss"]
        
        races_payload = json.dumps(races)
        
        # Test the method
        result = self.db_writer.update_preferences_1v1(
            discord_uid=discord_uid,
            last_chosen_races=races_payload,
            last_chosen_vetoes=None
        )
        
        assert result is True
        print(f"✅ Updated preferences for user {discord_uid}")
        print(f"   Races: {races_payload}")
        print(f"   Vetoes: None")
    
    def test_update_preferences_vetoes_only(self):
        """Test updating preferences with vetoes only."""
        discord_uid = 11111
        vetoes = ["Pylon", "Khione"]
        
        vetoes_payload = json.dumps(vetoes)
        
        # Test the method
        result = self.db_writer.update_preferences_1v1(
            discord_uid=discord_uid,
            last_chosen_races=None,
            last_chosen_vetoes=vetoes_payload
        )
        
        assert result is True
        print(f"✅ Updated preferences for user {discord_uid}")
        print(f"   Races: None")
        print(f"   Vetoes: {vetoes_payload}")
    
    def test_update_preferences_no_fields(self):
        """Test updating preferences with no fields (should return False)."""
        discord_uid = 22222
        
        # Test the method
        result = self.db_writer.update_preferences_1v1(
            discord_uid=discord_uid,
            last_chosen_races=None,
            last_chosen_vetoes=None
        )
        
        assert result is False
        print(f"✅ Correctly returned False for no fields update")
    
    def test_persist_preferences_simulation(self):
        """Test the persist_preferences method logic."""
        # Simulate the logic from queue_command.py
        discord_user_id = 12345
        selected_races = ["bw_terran", "sc2_zerg"]
        vetoed_maps = ["Arkanoid", "Khione"]
        
        # This is what happens in persist_preferences
        races_payload = json.dumps(selected_races)
        vetoes_payload = json.dumps(vetoed_maps)
        
        print(f"🎮 Simulating persist_preferences for user {discord_user_id}")
        print(f"   Selected races: {selected_races}")
        print(f"   Vetoed maps: {vetoed_maps}")
        print(f"   Races payload: {races_payload}")
        print(f"   Vetoes payload: {vetoes_payload}")
        
        # Test the database call
        result = self.db_writer.update_preferences_1v1(
            discord_uid=discord_user_id,
            last_chosen_races=races_payload,
            last_chosen_vetoes=vetoes_payload
        )
        
        assert result is True
        print(f"✅ Database update successful: {result}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
