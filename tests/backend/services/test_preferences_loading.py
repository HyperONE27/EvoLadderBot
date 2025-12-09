"""
Test preferences loading functionality.

This module tests that user preferences are properly loaded from the database
when the /queue command is called.
"""

import pytest
import json
from unittest.mock import Mock, patch
from src.backend.db.db_reader_writer import DatabaseReader, DatabaseWriter


class TestPreferencesLoading:
    """Test preferences loading from database."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.db_reader = DatabaseReader()
        self.db_writer = DatabaseWriter()
    
    def test_load_existing_preferences(self):
        """Test loading existing preferences from database."""
        discord_uid = 12345
        races = ["bw_terran", "sc2_zerg"]
        vetoes = ["Arkanoid", "Khione"]
        
        # First, save some preferences
        races_payload = json.dumps(races)
        vetoes_payload = json.dumps(vetoes)
        
        self.db_writer.update_preferences_1v1(
            discord_uid=discord_uid,
            last_chosen_races=races_payload,
            last_chosen_vetoes=vetoes_payload
        )
        
        # Now load them back
        preferences = self.db_reader.get_preferences_1v1(discord_uid)
        
        assert preferences is not None
        assert preferences['discord_uid'] == discord_uid
        
        # Parse the JSON strings back to lists
        loaded_races = json.loads(preferences['last_chosen_races'])
        loaded_vetoes = json.loads(preferences['last_chosen_vetoes'])
        
        assert loaded_races == races
        assert loaded_vetoes == vetoes
        
        print(f"✅ Successfully loaded preferences for user {discord_uid}")
        print(f"   Races: {loaded_races}")
        print(f"   Vetoes: {loaded_vetoes}")
    
    def test_load_nonexistent_preferences(self):
        """Test loading preferences for user with no saved preferences."""
        discord_uid = 99999  # Non-existent user
        
        preferences = self.db_reader.get_preferences_1v1(discord_uid)
        
        assert preferences is None
        print(f"✅ Correctly returned None for non-existent user {discord_uid}")
    
    def test_preferences_parsing_simulation(self):
        """Test the preferences parsing logic from queue_command.py."""
        # Simulate the logic from queue_command.py
        discord_uid = 12345
        
        # Mock user preferences from database
        user_preferences = {
            'discord_uid': discord_uid,
            'last_chosen_races': '["bw_terran", "sc2_zerg"]',
            'last_chosen_vetoes': '["Arkanoid", "Khione"]'
        }
        
        # This is the logic from queue_command.py
        if user_preferences:
            try:
                default_races = json.loads(user_preferences.get('last_chosen_races', '[]'))
                default_maps = json.loads(user_preferences.get('last_chosen_vetoes', '[]'))
            except (json.JSONDecodeError, TypeError):
                default_races = []
                default_maps = []
        else:
            default_races = []
            default_maps = []
        
        # Verify parsing
        assert default_races == ["bw_terran", "sc2_zerg"]
        assert default_maps == ["Arkanoid", "Khione"]
        
        print(f"✅ Successfully parsed preferences for user {discord_uid}")
        print(f"   Default races: {default_races}")
        print(f"   Default maps: {default_maps}")
    
    def test_preferences_parsing_with_invalid_json(self):
        """Test preferences parsing with invalid JSON (should fallback to empty)."""
        # Mock user preferences with invalid JSON
        user_preferences = {
            'discord_uid': 12345,
            'last_chosen_races': 'invalid json',
            'last_chosen_vetoes': '["Arkanoid", "Khione"]'
        }
        
        # This is the logic from queue_command.py
        if user_preferences:
            try:
                default_races = json.loads(user_preferences.get('last_chosen_races', '[]'))
                default_maps = json.loads(user_preferences.get('last_chosen_vetoes', '[]'))
            except (json.JSONDecodeError, TypeError):
                default_races = []
                default_maps = []
        else:
            default_races = []
            default_maps = []
        
        # Verify fallback to empty defaults
        assert default_races == []
        assert default_maps == []
        
        print(f"✅ Successfully handled invalid JSON with fallback to empty defaults")
    
    def test_preferences_parsing_with_missing_fields(self):
        """Test preferences parsing with missing fields (should use defaults)."""
        # Mock user preferences with missing fields
        user_preferences = {
            'discord_uid': 12345,
            'last_chosen_races': None,
            'last_chosen_vetoes': None
        }
        
        # This is the logic from queue_command.py
        if user_preferences:
            try:
                default_races = json.loads(user_preferences.get('last_chosen_races', '[]'))
                default_maps = json.loads(user_preferences.get('last_chosen_vetoes', '[]'))
            except (json.JSONDecodeError, TypeError):
                default_races = []
                default_maps = []
        else:
            default_races = []
            default_maps = []
        
        # Verify fallback to empty defaults
        assert default_races == []
        assert default_maps == []
        
        print(f"✅ Successfully handled missing fields with fallback to empty defaults")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
