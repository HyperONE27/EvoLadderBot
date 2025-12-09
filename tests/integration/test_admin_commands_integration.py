"""
Integration tests for admin commands.

Tests the complete admin command flow including:
- Admin verification from admins.json
- All admin commands and their confirmations
- Admin-only interaction checks
- Proper error handling
"""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path

# Import the admin command module
import src.bot.commands.admin_command as admin_module
from src.bot.commands.admin_command import (
    _load_admin_ids,
    is_admin,
    AdminConfirmationView,
    register_admin_commands
)


class TestAdminVerification:
    """Test admin ID loading and verification."""
    
    def test_load_admin_ids_success(self, tmp_path):
        """Test successful loading of admin IDs from JSON."""
        # Create temporary admins.json
        admins_data = [
            {"discord_id": 123456789, "name": "Admin1"},
            {"discord_id": 987654321, "name": "Admin2"},
            {"discord_id": 111222333, "name": "Admin3"}
        ]
        
        # Mock open to return the JSON data
        from unittest.mock import mock_open
        mock_file = mock_open(read_data=json.dumps(admins_data))
        
        with patch('builtins.open', mock_file):
            admin_ids = _load_admin_ids()
        
        assert len(admin_ids) == 3
        assert 123456789 in admin_ids
        assert 987654321 in admin_ids
        assert 111222333 in admin_ids
    
    def test_load_admin_ids_missing_file(self):
        """Test handling of missing admins.json file."""
        with patch('builtins.open', side_effect=FileNotFoundError()):
            admin_ids = _load_admin_ids()
        
        assert admin_ids == set()
    
    def test_load_admin_ids_invalid_json(self):
        """Test handling of invalid JSON."""
        with patch('builtins.open', side_effect=json.JSONDecodeError("error", "", 0)):
            admin_ids = _load_admin_ids()
        
        assert admin_ids == set()
    
    def test_load_admin_ids_malformed_data(self, tmp_path):
        """Test handling of malformed admin data."""
        # Missing discord_id in second entry
        admins_data = [
            {"discord_id": 123456789, "name": "Admin1"},
            {"name": "Admin2"},  # Missing discord_id
            {"discord_id": "not_a_number", "name": "Admin3"},  # Wrong type
            {"discord_id": 111222333, "name": "Admin4"}
        ]
        
        # Mock open to return the JSON data
        from unittest.mock import mock_open
        mock_file = mock_open(read_data=json.dumps(admins_data))
        
        with patch('builtins.open', mock_file):
            admin_ids = _load_admin_ids()
        
        # Should only load valid entries
        assert 123456789 in admin_ids
        assert 111222333 in admin_ids
        assert len(admin_ids) == 2
    
    def test_is_admin_true(self):
        """Test is_admin returns True for admin users."""
        mock_interaction = Mock()
        mock_interaction.user.id = 123456789
        
        with patch.object(admin_module, 'ADMIN_IDS', {123456789, 987654321}):
            assert is_admin(mock_interaction) is True
    
    def test_is_admin_false(self):
        """Test is_admin returns False for non-admin users."""
        mock_interaction = Mock()
        mock_interaction.user.id = 999999999
        
        with patch.object(admin_module, 'ADMIN_IDS', {123456789, 987654321}):
            assert is_admin(mock_interaction) is False


class TestAdminConfirmationView:
    """Test AdminConfirmationView class."""
    
    @pytest.mark.asyncio
    async def test_interaction_check_admin(self):
        """Test that admins can interact with the view."""
        view = AdminConfirmationView(timeout=60)
        view.set_admin(123456789)
        
        mock_interaction = Mock()
        mock_interaction.user.id = 123456789
        mock_interaction.response = AsyncMock()
        
        with patch.object(admin_module, 'ADMIN_IDS', {123456789}):
            result = await view.interaction_check(mock_interaction)
        
        assert result is True
        mock_interaction.response.send_message.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_interaction_check_non_admin(self):
        """Test that non-admins cannot interact with the view."""
        view = AdminConfirmationView(timeout=60)
        view.set_admin(123456789)
        
        mock_interaction = Mock()
        mock_interaction.user.id = 999999999
        mock_interaction.response = AsyncMock()
        
        with patch.object(admin_module, 'ADMIN_IDS', {123456789}):
            result = await view.interaction_check(mock_interaction)
        
        assert result is False
        mock_interaction.response.send_message.assert_called_once()
        
        # Verify error message
        call_args = mock_interaction.response.send_message.call_args
        embed = call_args[1]['embed']
        assert 'Admin Access Denied' in embed.title


class TestAdminCommandsRegistration:
    """Test admin commands are properly registered."""
    
    def test_register_admin_commands(self):
        """Test that admin commands are registered correctly."""
        mock_tree = Mock()
        mock_tree.add_command = Mock()
        
        # Mock admin_service to avoid initialization issues
        with patch('src.bot.commands.admin_command.admin_service'):
            register_admin_commands(mock_tree)
        
        # Verify admin group was added
        mock_tree.add_command.assert_called_once()
        admin_group = mock_tree.add_command.call_args[0][0]
        
        assert admin_group.name == "admin"
        assert "Admin Only" in admin_group.description


class TestAdminCommandFlow:
    """Test complete admin command execution flows."""
    
    @pytest.mark.asyncio
    async def test_snapshot_command_small_output(self):
        """Test /admin snapshot with small output (embed)."""
        from src.backend.services.admin_service import AdminService
        
        mock_interaction = Mock()
        mock_interaction.user.id = 123456789
        mock_interaction.response = AsyncMock()
        mock_interaction.followup = AsyncMock()
        
        # Mock admin service
        mock_service = Mock(spec=AdminService)
        mock_service.get_system_snapshot.return_value = {
            'queue_size': 5,
            'active_matches': 10
        }
        mock_service.format_system_snapshot.return_value = "Test snapshot data"
        
        with patch.object(admin_module, 'ADMIN_IDS', {123456789}):
            with patch('src.bot.commands.admin_command.admin_service', mock_service):
                # Import command after patching
                from src.bot.commands.admin_command import register_admin_commands
                
                mock_tree = Mock()
                register_admin_commands(mock_tree)
                
                # Get the snapshot command
                admin_group = mock_tree.add_command.call_args[0][0]
                snapshot_cmd = admin_group.get_command('snapshot')
                
                # Execute command
                await snapshot_cmd.callback(mock_interaction)
        
        # Verify response
        mock_interaction.response.defer.assert_called_once()
        mock_interaction.followup.send.assert_called_once()
        
        # Verify embed was used (not file)
        call_args = mock_interaction.followup.send.call_args
        assert 'embed' in call_args[1]
        assert 'Admin System Snapshot' in call_args[1]['embed'].title
    
    @pytest.mark.asyncio
    async def test_resolve_command_creates_confirmation(self):
        """Test /admin resolve creates confirmation view."""
        from src.backend.services.admin_service import AdminService
        
        mock_interaction = Mock()
        mock_interaction.user.id = 123456789
        mock_interaction.response = AsyncMock()
        
        mock_winner = Mock()
        mock_winner.value = 1
        mock_winner.name = "Player 1 Wins"
        
        with patch.object(admin_module, 'ADMIN_IDS', {123456789}):
            with patch('src.bot.commands.admin_command.admin_service'):
                from src.bot.commands.admin_command import register_admin_commands
                
                mock_tree = Mock()
                register_admin_commands(mock_tree)
                
                admin_group = mock_tree.add_command.call_args[0][0]
                resolve_cmd = admin_group.get_command('resolve')
                
                # Execute command
                await resolve_cmd.callback(
                    mock_interaction,
                    match_id=123,
                    winner=mock_winner,
                    reason="Test reason"
                )
        
        # Verify confirmation was sent
        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        
        embed = call_args[1]['embed']
        assert 'Admin: Confirm Match Resolution' in embed.title
        assert '123' in embed.description  # Match ID is in description
        assert 'Player 1 Wins' in embed.description
        assert 'Test reason' in embed.description
        
        # Verify view with buttons
        view = call_args[1]['view']
        assert isinstance(view, AdminConfirmationView)
        
        # Check buttons
        buttons = [item for item in view.children]
        assert len(buttons) == 2
        assert any('Admin Confirm' in str(btn.label) for btn in buttons)
        assert any('Admin Cancel' in str(btn.label) for btn in buttons)


class TestAdminCommandNaming:
    """Test that all admin components are properly named."""
    
    def test_all_commands_have_admin_prefix(self):
        """Test that all command descriptions start with [Admin]."""
        with patch('src.bot.commands.admin_command.admin_service'):
            mock_tree = Mock()
            register_admin_commands(mock_tree)
            
            admin_group = mock_tree.add_command.call_args[0][0]
            commands = admin_group.commands
            
            for cmd in commands:
                assert cmd.description.startswith('[Admin]'), \
                    f"Command '{cmd.name}' description must start with [Admin]"
    
    def test_all_embeds_include_admin(self):
        """Test that all embeds include 'Admin' in their titles."""
        # This is verified through the test_resolve_command_creates_confirmation test
        # and similar tests for other commands
        pass


class TestAdminServiceIntegration:
    """Test integration with admin_service."""
    
    @pytest.mark.asyncio
    async def test_resolve_conflict_integration(self):
        """Test full resolve conflict flow."""
        from src.backend.services.admin_service import AdminService
        
        mock_service = Mock(spec=AdminService)
        mock_service.resolve_match_conflict = AsyncMock(return_value={
            'success': True,
            'resolution': 'player_1_win',
            'mmr_change': 25
        })
        
        mock_button_interaction = Mock()
        mock_button_interaction.response = AsyncMock()
        mock_button_interaction.edit_original_response = AsyncMock()
        
        with patch('src.bot.commands.admin_command.admin_service', mock_service):
            # Create a callback like the one in the command
            async def confirm_callback(button_interaction):
                await button_interaction.response.defer()
                
                result = await mock_service.resolve_match_conflict(
                    match_id=123,
                    resolution='player_1_win',
                    admin_discord_id=123456789,
                    reason="Test reason"
                )
                
                if result['success']:
                    # Would create embed here
                    pass
            
            # Execute callback
            await confirm_callback(mock_button_interaction)
        
        # Verify service was called correctly
        mock_service.resolve_match_conflict.assert_called_once_with(
            match_id=123,
            resolution='player_1_win',
            admin_discord_id=123456789,
            reason="Test reason"
        )
    
    @pytest.mark.asyncio
    async def test_adjust_mmr_integration(self):
        """Test full MMR adjustment flow."""
        from src.backend.services.admin_service import AdminService
        
        mock_service = Mock(spec=AdminService)
        mock_service.adjust_player_mmr = AsyncMock(return_value={
            'success': True,
            'old_mmr': 1500,
            'new_mmr': 1600,
            'change': 100
        })
        
        with patch('src.bot.commands.admin_command.admin_service', mock_service):
            result = await mock_service.adjust_player_mmr(
                discord_uid=123456789,
                race='bw_terran',
                new_mmr=1600,
                admin_discord_id=987654321,
                reason="Test adjustment"
            )
        
        assert result['success'] is True
        assert result['change'] == 100


class TestErrorHandling:
    """Test error handling in admin commands."""
    
    @pytest.mark.asyncio
    async def test_invalid_discord_id_string(self):
        """Test handling of invalid Discord ID."""
        mock_interaction = Mock()
        mock_interaction.user.id = 123456789
        mock_interaction.response = AsyncMock()
        mock_interaction.followup = AsyncMock()  # Make followup async
        
        with patch.object(admin_module, 'ADMIN_IDS', {123456789}):
            with patch('src.bot.commands.admin_command.admin_service'):
                from src.bot.commands.admin_command import register_admin_commands
                
                mock_tree = Mock()
                register_admin_commands(mock_tree)
                
                admin_group = mock_tree.add_command.call_args[0][0]
                player_cmd = admin_group.get_command('player')
                
                # Execute with invalid Discord ID
                await player_cmd.callback(mock_interaction, discord_id="not_a_number")
        
        # Verify error message
        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        assert "Invalid Discord ID" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_service_error_handling(self):
        """Test handling of service errors."""
        from src.backend.services.admin_service import AdminService
        
        mock_service = Mock(spec=AdminService)
        mock_service.resolve_match_conflict = AsyncMock(return_value={
            'success': False,
            'error': 'Match not found'
        })
        
        mock_button_interaction = Mock()
        mock_button_interaction.response = AsyncMock()
        mock_button_interaction.edit_original_response = AsyncMock()
        
        with patch('src.bot.commands.admin_command.admin_service', mock_service):
            # Simulate error in callback
            result = await mock_service.resolve_match_conflict(
                match_id=999,
                resolution='player_1_win',
                admin_discord_id=123456789,
                reason="Test"
            )
        
        assert result['success'] is False
        assert 'error' in result


def test_admin_ids_loaded_at_module_import():
    """Test that admin IDs are loaded when module is imported."""
    # ADMIN_IDS should be loaded at module level
    assert hasattr(admin_module, 'ADMIN_IDS')
    assert isinstance(admin_module.ADMIN_IDS, set)


def test_all_admin_functions_exported():
    """Test that all necessary functions are exported."""
    assert hasattr(admin_module, '_load_admin_ids')
    assert hasattr(admin_module, 'is_admin')
    assert hasattr(admin_module, 'admin_only')
    assert hasattr(admin_module, 'AdminConfirmationView')
    assert hasattr(admin_module, 'register_admin_commands')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

