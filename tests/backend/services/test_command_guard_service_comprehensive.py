"""
Comprehensive test suite for CommandGuardService.

Tests authorization checks, player record creation, and guard conditions.
"""

import pytest
from unittest.mock import Mock, MagicMock
from src.backend.services.command_guard_service import CommandGuardService, CommandGuardError


class TestCommandGuardService:
    """Comprehensive test suite for CommandGuardService"""
    
    @pytest.fixture
    def mock_db_reader(self):
        """Mock database reader"""
        return Mock()
    
    @pytest.fixture
    def mock_db_writer(self):
        """Mock database writer"""
        return Mock()
    
    @pytest.fixture
    def mock_user_service(self):
        """Mock user info service"""
        return Mock()
    
    @pytest.fixture
    def guard_service(self, mock_db_reader, mock_db_writer, mock_user_service):
        """Fixture to provide a CommandGuardService instance"""
        return CommandGuardService(mock_db_reader, mock_db_writer, mock_user_service)
    
    def test_ensure_player_record_new_player(self, guard_service, mock_user_service):
        """Test ensure_player_record creates new players correctly"""
        
        test_cases = [
            # (discord_id, discord_username, mock_return_value)
            (123456789, "TestUser", {"discord_uid": 123456789, "discord_username": "TestUser"}),
            (987654321, "AnotherUser", {"discord_uid": 987654321, "discord_username": "AnotherUser"}),
            (111111111, "NewPlayer", {"discord_uid": 111111111, "discord_username": "NewPlayer"}),
        ]
        
        for discord_id, username, expected_return in test_cases:
            mock_user_service.ensure_player_exists.return_value = expected_return
            
            result = guard_service.ensure_player_record(discord_id, username)
            
            assert result == expected_return, \
                f"Failed for user {discord_id}: expected {expected_return}, got {result}"
            mock_user_service.ensure_player_exists.assert_called_with(discord_id, username)
    
    def test_require_setup_complete_valid_players(self, guard_service):
        """Test require_setup_complete with players who have completed setup"""
        
        test_cases = [
            # (player_record)
            ({"setup_complete": True, "tos_agreed": True}),
            ({"setup_complete": True, "tos_agreed": True, "discord_username": "User1"}),
            ({"setup_complete": True, "tos_agreed": True, "player_name": "PlayerOne"}),
        ]
        
        for player_record in test_cases:
            try:
                guard_service.require_setup_complete(player_record)
                # Should not raise an error
            except CommandGuardError:
                pytest.fail(f"Should not raise error for valid player: {player_record}")
    
    def test_require_setup_complete_invalid_players(self, guard_service):
        """Test require_setup_complete raises errors for incomplete setup"""
        
        test_cases = [
            # (player_record, expected_error_substring)
            ({"setup_complete": False, "tos_agreed": True}, "setup"),
            ({"setup_complete": True, "tos_agreed": False}, "Terms of Service"),
            ({"setup_complete": False, "tos_agreed": False}, "setup"),
            ({}, "setup"),
            ({"setup_complete": None, "tos_agreed": True}, "setup"),
            ({"setup_complete": True, "tos_agreed": None}, "Terms of Service"),
        ]
        
        for player_record, expected_error in test_cases:
            with pytest.raises(CommandGuardError) as exc_info:
                guard_service.require_setup_complete(player_record)
            assert expected_error.lower() in str(exc_info.value).lower(), \
                f"Expected error containing '{expected_error}' for {player_record}, got {exc_info.value}"
    
    def test_require_queue_access_valid_players(self, guard_service):
        """Test require_queue_access with players who can queue"""
        
        test_cases = [
            # (player_record)
            ({"setup_complete": True, "tos_agreed": True, "is_banned": False}),
            ({"setup_complete": True, "tos_agreed": True, "is_banned": None}),
            ({"setup_complete": True, "tos_agreed": True}),  # No is_banned field
        ]
        
        for player_record in test_cases:
            try:
                guard_service.require_queue_access(player_record)
                # Should not raise an error
            except CommandGuardError:
                pytest.fail(f"Should not raise error for valid player: {player_record}")
    
    def test_require_queue_access_invalid_players(self, guard_service):
        """Test require_queue_access raises errors appropriately"""
        
        test_cases = [
            # (player_record, expected_error_substring)
            ({"setup_complete": False, "tos_agreed": True, "is_banned": False}, "setup"),
            ({"setup_complete": True, "tos_agreed": False, "is_banned": False}, "Terms of Service"),
            ({"setup_complete": True, "tos_agreed": True, "is_banned": True}, "banned"),
            ({"setup_complete": False, "tos_agreed": False, "is_banned": True}, "setup"),
        ]
        
        for player_record, expected_error in test_cases:
            with pytest.raises(CommandGuardError) as exc_info:
                guard_service.require_queue_access(player_record)
            assert expected_error.lower() in str(exc_info.value).lower(), \
                f"Expected error containing '{expected_error}' for {player_record}, got {exc_info.value}"
    
    def test_check_dm_only_valid_interactions(self, guard_service):
        """Test check_dm_only with valid DM interactions"""
        
        test_cases = [
            # (guild_id, description)
            (None, "Standard DM (None)"),
        ]
        
        for guild_id, description in test_cases:
            mock_interaction = Mock()
            mock_interaction.guild = None if guild_id is None else Mock(id=guild_id)
            
            try:
                guard_service.check_dm_only(mock_interaction)
                # Should not raise an error
            except CommandGuardError:
                pytest.fail(f"Should not raise error for {description}")
    
    def test_check_dm_only_invalid_interactions(self, guard_service):
        """Test check_dm_only raises errors for non-DM interactions"""
        
        test_cases = [
            # (guild_id, description)
            (123456789, "Guild interaction"),
            (987654321, "Another guild"),
            (1, "Minimal guild ID"),
        ]
        
        for guild_id, description in test_cases:
            mock_interaction = Mock()
            mock_interaction.guild = Mock(id=guild_id)
            
            with pytest.raises(CommandGuardError) as exc_info:
                guard_service.check_dm_only(mock_interaction)
            assert "dm" in str(exc_info.value).lower() or "private" in str(exc_info.value).lower(), \
                f"Expected DM error for {description}, got {exc_info.value}"
    
    def test_command_guard_error_creation(self):
        """Test CommandGuardError creation and attributes"""
        
        test_cases = [
            # (title, description, show_help_button)
            ("Setup Required", "Please complete setup first", True),
            ("Access Denied", "You are banned", False),
            ("ToS Required", "Accept Terms of Service", True),
            ("DM Only", "Use this command in DMs", False),
        ]
        
        for title, description, show_help in test_cases:
            error = CommandGuardError(title, description, show_help_button=show_help)
            
            assert error.title == title, f"Title mismatch: expected {title}, got {error.title}"
            assert error.description == description, f"Description mismatch: expected {description}, got {error.description}"
            assert error.show_help_button == show_help, f"Help button mismatch: expected {show_help}, got {error.show_help_button}"
            
            # Check string representation
            error_str = str(error)
            assert title in error_str or description in error_str, \
                f"Error string should contain title or description: {error_str}"

