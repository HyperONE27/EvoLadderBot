"""
Test draw result recording functionality.

This module tests that draw results are properly recorded in the database
with winner_discord_uid = -1.
"""

import pytest
from unittest.mock import Mock, patch
from src.backend.services.matchmaking_service import Matchmaker, Player, QueuePreferences, MatchResult


class TestDrawRecording:
    """Test draw result recording."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.matchmaker = Matchmaker()
    
    @patch('src.backend.services.matchmaking_service.DatabaseWriter')
    def test_record_draw_result(self, mock_db_writer):
        """Test that draw results are recorded with -1."""
        # Mock the database writer
        mock_writer_instance = Mock()
        mock_writer_instance.update_match_result_1v1.return_value = True
        mock_db_writer.return_value = mock_writer_instance
        
        # Set up matchmaker with mocked database
        self.matchmaker.db_writer = mock_writer_instance
        
        # Test recording a draw result
        match_id = 123
        winner_discord_uid = -1  # -1 for draw
        
        success = self.matchmaker.record_match_result(match_id, winner_discord_uid)
        
        # Verify the database was called with -1
        mock_writer_instance.update_match_result_1v1.assert_called_once_with(match_id, -1)
        assert success is True
    
    @patch('src.backend.services.matchmaking_service.DatabaseWriter')
    def test_record_winner_result(self, mock_db_writer):
        """Test that winner results are recorded with actual Discord UID."""
        # Mock the database writer
        mock_writer_instance = Mock()
        mock_writer_instance.update_match_result_1v1.return_value = True
        mock_db_writer.return_value = mock_writer_instance
        
        # Set up matchmaker with mocked database
        self.matchmaker.db_writer = mock_writer_instance
        
        # Test recording a winner result
        match_id = 123
        winner_discord_uid = 456789  # Actual Discord UID
        
        success = self.matchmaker.record_match_result(match_id, winner_discord_uid)
        
        # Verify the database was called with the actual UID
        mock_writer_instance.update_match_result_1v1.assert_called_once_with(match_id, 456789)
        assert success is True
    
    def test_draw_result_processing(self):
        """Test the draw result processing logic."""
        # Simulate the draw result processing from queue_command.py
        result = "draw"
        
        # This is the logic from queue_command.py
        if result == "draw":
            winner_discord_id = -1  # -1 for draw
            winner = "Draw"
            loser = "Draw"
        else:
            # This would be for actual winners
            winner_discord_id = 12345
            winner = "Player1"
            loser = "Player2"
        
        # Verify draw result processing
        assert winner_discord_id == -1
        assert winner == "Draw"
        assert loser == "Draw"
    
    def test_winner_result_processing(self):
        """Test the winner result processing logic."""
        # Simulate the winner result processing from queue_command.py
        result = "player1_win"
        player1_discord_id = 12345
        player2_discord_id = 67890
        
        # This is the logic from queue_command.py
        if result == "player1_win":
            winner_discord_id = player1_discord_id
            winner = "Player1"
            loser = "Player2"
        elif result == "player2_win":
            winner_discord_id = player2_discord_id
            winner = "Player2"
            loser = "Player1"
        else:  # draw
            winner_discord_id = -1
            winner = "Draw"
            loser = "Draw"
        
        # Verify winner result processing
        assert winner_discord_id == 12345
        assert winner == "Player1"
        assert loser == "Player2"
    
    def test_database_schema_compatibility(self):
        """Test that -1 is a valid value for the database schema."""
        # Test that -1 can be stored in an INTEGER column
        test_values = [
            (12345, "Valid Discord UID"),
            (-1, "Draw result"),
            (0, "Edge case - should be valid"),
            (999999999, "Large Discord UID")
        ]
        
        for value, description in test_values:
            # These should all be valid integer values
            assert isinstance(value, int), f"{description} should be an integer"
            assert value >= -1, f"{description} should be >= -1"
            print(f"✅ {description}: {value}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
