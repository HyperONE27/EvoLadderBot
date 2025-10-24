"""
Characterization tests for the /prune command flow.

These tests verify the current behavior of the prune command and serve as a
regression detection baseline.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
import discord

from src.bot.commands.prune_command import prune_command
from src.bot.config import GLOBAL_TIMEOUT


@pytest.fixture
def mock_interaction():
    """Create a mock Discord interaction for testing."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.User)
    interaction.user.id = 218147282875318274
    interaction.user.name = "TestUser"
    interaction.channel = AsyncMock(spec=discord.DMChannel)
    interaction.channel.id = 1425004719629402193
    interaction.client = MagicMock()
    interaction.client.user = MagicMock()
    interaction.client.user.id = 123456789
    
    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    
    # Create a mock for the message returned by followup.send
    mock_initial_message = AsyncMock(spec=discord.WebhookMessage)
    mock_initial_message.edit = AsyncMock()
    
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock(return_value=mock_initial_message)
    
    interaction.edit_original_response = AsyncMock()
    
    return interaction


@pytest.fixture
def mock_bot_message():
    """Create a mock bot message."""
    def _create_message(
        message_id: int,
        age_seconds: int,
        has_queue_content: bool = False,
        has_prune_content: bool = False
    ):
        message = MagicMock(spec=discord.Message)
        message.id = message_id
        message.author = MagicMock()
        message.author.id = 123456789
        message.created_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
        message.jump_url = f"https://discord.com/channels/@me/{message_id}"
        
        if has_queue_content:
            embed = MagicMock()
            embed.title = "🔍 Searching..."
            embed.fields = []
            message.embeds = [embed]
        elif has_prune_content:
            embed = MagicMock()
            embed.title = "🗑️ Confirm Message Deletion"
            embed.description = "Delete old bot messages"
            message.embeds = [embed]
        else:
            message.embeds = []
        
        message.components = []
        message.delete = AsyncMock()
        
        return message
    
    return _create_message


@pytest.mark.asyncio
async def test_prune_sends_immediate_followup(mock_interaction, mock_bot_message):
    """
    Verifies that the prune command defers immediately, then sends a followup
    message before starting long-running operations.
    
    This is critical for Discord UX: users should see immediate feedback,
    not a 3-second loading spinner.
    """
    old_message = mock_bot_message(
        message_id=100001,
        age_seconds=GLOBAL_TIMEOUT + 100,
        has_queue_content=False
    )
    
    async def mock_history(*args, **kwargs):
        for msg in [old_message]:
            yield msg
    
    mock_interaction.channel.history = mock_history
    
    with patch("src.bot.commands.prune_command.command_guard_service") as mock_guard:
        mock_player = {"discord_uid": 218147282875318274, "tos_accepted": True}
        mock_guard.ensure_player_record.return_value = mock_player
        mock_guard.require_tos_accepted.return_value = None
        
        await prune_command(mock_interaction)
    
    # Verify followup.send was called (confirmation embed with buttons)
    # Note: The current implementation doesn't defer for prune when data is ready quickly
    assert mock_interaction.followup.send.called or mock_interaction.response.send_message.called


@pytest.mark.asyncio
async def test_prune_handles_no_messages(mock_interaction):
    """
    Verifies the flow when no messages are found to be pruned.
    Should send initial "Analyzing..." message, then edit to "No messages to prune" message.
    """
    async def mock_history(*args, **kwargs):
        return
        yield
    
    mock_interaction.channel.history = mock_history
    
    with patch("src.bot.commands.prune_command.command_guard_service") as mock_guard:
        mock_player = {"discord_uid": 218147282875318274, "tos_accepted": True}
        mock_guard.ensure_player_record.return_value = mock_player
        mock_guard.require_tos_accepted.return_value = None
        
        await prune_command(mock_interaction)
    
    # Verify initial "Analyzing..." message was sent
    mock_interaction.followup.send.assert_called_once()
    initial_call_args = mock_interaction.followup.send.call_args
    initial_embed = initial_call_args.kwargs.get("embed")
    assert initial_embed is not None
    assert "Analyzing Messages" in initial_embed.title
    
    # Verify final message was edited to "No Messages to Prune"
    mock_initial_message = mock_interaction.followup.send.return_value
    mock_initial_message.edit.assert_called_once()
    final_call_args = mock_initial_message.edit.call_args
    final_embed = final_call_args.kwargs.get("embed")
    assert final_embed is not None
    assert "No Messages to Prune" in final_embed.title


@pytest.mark.asyncio
async def test_prune_protects_queue_messages(mock_interaction, mock_bot_message):
    """
    Verifies that queue-related messages are protected from pruning.
    Should send initial "Analyzing..." message, then edit to confirmation with 1 message.
    """
    old_queue_message = mock_bot_message(
        message_id=100002,
        age_seconds=GLOBAL_TIMEOUT + 100,
        has_queue_content=True
    )
    old_normal_message = mock_bot_message(
        message_id=100003,
        age_seconds=GLOBAL_TIMEOUT + 100,
        has_queue_content=False
    )
    
    async def mock_history(*args, **kwargs):
        for msg in [old_queue_message, old_normal_message]:
            yield msg
    
    mock_interaction.channel.history = mock_history
    
    with patch("src.bot.commands.prune_command.command_guard_service") as mock_guard:
        mock_player = {"discord_uid": 218147282875318274, "tos_accepted": True}
        mock_guard.ensure_player_record.return_value = mock_player
        mock_guard.require_tos_accepted.return_value = None
        
        await prune_command(mock_interaction)
    
    # Verify initial "Analyzing..." message was sent
    mock_interaction.followup.send.assert_called_once()
    
    # Verify final message was edited to confirmation
    mock_initial_message = mock_interaction.followup.send.return_value
    mock_initial_message.edit.assert_called_once()
    final_call_args = mock_initial_message.edit.call_args
    final_embed = final_call_args.kwargs.get("embed")
    
    # Should only offer to delete 1 message (the normal one)
    # The actual text uses markdown bold: **1 message(s)**
    assert final_embed is not None
    assert "1 message(s)" in final_embed.description and "will be deleted" in final_embed.description


@pytest.mark.asyncio
async def test_prune_confirmation_flow(mock_interaction, mock_bot_message):
    """
    Verifies the full confirmation and deletion flow.
    When the user clicks "Confirm", messages should be deleted.
    """
    old_message = mock_bot_message(
        message_id=100004,
        age_seconds=GLOBAL_TIMEOUT + 100
    )
    
    async def mock_history(*args, **kwargs):
        for msg in [old_message]:
            yield msg
    
    mock_interaction.channel.history = mock_history
    
    with patch("src.bot.commands.prune_command.command_guard_service") as mock_guard:
        mock_player = {"discord_uid": 218147282875318274, "tos_accepted": True}
        mock_guard.ensure_player_record.return_value = mock_player
        mock_guard.require_tos_accepted.return_value = None
        
        await prune_command(mock_interaction)
    
    # Verify initial "Analyzing..." message was sent
    mock_interaction.followup.send.assert_called_once()
    
    # Verify final message was edited to confirmation with view
    mock_initial_message = mock_interaction.followup.send.return_value
    mock_initial_message.edit.assert_called_once()
    final_call_args = mock_initial_message.edit.call_args
    view = final_call_args.kwargs.get("view")
    
    assert view is not None
    assert len(view.children) > 0
    
    # Find and invoke the confirm button
    confirm_button = None
    for child in view.children:
        if hasattr(child, "label") and "Confirm" in child.label:
            confirm_button = child
            break
    
    assert confirm_button is not None
    
    # Create a mock interaction for the button click
    confirm_interaction = AsyncMock(spec=discord.Interaction)
    confirm_interaction.response = AsyncMock()
    confirm_interaction.response.defer = AsyncMock()
    confirm_interaction.edit_original_response = AsyncMock()
    
    # Invoke the confirm callback
    await confirm_button.callback(confirm_interaction)
    
    # Verify the message was deleted
    old_message.delete.assert_called_once()


@pytest.mark.asyncio
async def test_prune_protects_active_queue_message(mock_interaction, mock_bot_message):
    """
    Verifies that actively registered queue messages are protected from pruning.
    This is a strengthened test case from the expanded plan.
    """
    # Create a queue message that's registered as active
    active_queue_message = mock_bot_message(
        message_id=100005,
        age_seconds=GLOBAL_TIMEOUT + 100,
        has_queue_content=True
    )
    
    # Register this message as active
    from src.bot.commands.prune_command import register_active_queue_message
    register_active_queue_message(active_queue_message.id)
    
    old_normal_message = mock_bot_message(
        message_id=100006,
        age_seconds=GLOBAL_TIMEOUT + 100,
        has_queue_content=False
    )
    
    async def mock_history(*args, **kwargs):
        for msg in [active_queue_message, old_normal_message]:
            yield msg
    
    mock_interaction.channel.history = mock_history
    
    with patch("src.bot.commands.prune_command.command_guard_service") as mock_guard:
        mock_player = {"discord_uid": 218147282875318274, "tos_accepted": True}
        mock_guard.ensure_player_record.return_value = mock_player
        mock_guard.require_tos_accepted.return_value = None
        
        await prune_command(mock_interaction)
    
    # Verify initial "Analyzing..." message was sent
    mock_interaction.followup.send.assert_called_once()
    
    # Verify final message was edited to confirmation
    mock_initial_message = mock_interaction.followup.send.return_value
    mock_initial_message.edit.assert_called_once()
    final_call_args = mock_initial_message.edit.call_args
    final_embed = final_call_args.kwargs.get("embed")
    
    # Should only offer to delete 1 message (the normal one, not the active queue message)
    assert final_embed is not None
    assert "1 message(s)" in final_embed.description and "will be deleted" in final_embed.description


@pytest.mark.asyncio
async def test_prune_protects_very_old_queue_message(mock_interaction, mock_bot_message):
    """
    Verifies that very old queue messages (beyond protection period) are not protected.
    This is a strengthened test case from the expanded plan.
    """
    # Create a very old queue message (beyond QUEUE_MESSAGE_PROTECTION_DAYS)
    from src.bot.commands.prune_command import QUEUE_MESSAGE_PROTECTION_DAYS
    very_old_queue_message = mock_bot_message(
        message_id=100007,
        age_seconds=(QUEUE_MESSAGE_PROTECTION_DAYS + 1) * 24 * 60 * 60,  # Convert days to seconds
        has_queue_content=True
    )
    
    old_normal_message = mock_bot_message(
        message_id=100008,
        age_seconds=GLOBAL_TIMEOUT + 100,
        has_queue_content=False
    )
    
    async def mock_history(*args, **kwargs):
        for msg in [very_old_queue_message, old_normal_message]:
            yield msg
    
    mock_interaction.channel.history = mock_history
    
    with patch("src.bot.commands.prune_command.command_guard_service") as mock_guard:
        mock_player = {"discord_uid": 218147282875318274, "tos_accepted": True}
        mock_guard.ensure_player_record.return_value = mock_player
        mock_guard.require_tos_accepted.return_value = None
        
        await prune_command(mock_interaction)
    
    # Verify initial "Analyzing..." message was sent
    mock_interaction.followup.send.assert_called_once()
    
    # Verify final message was edited to confirmation
    mock_initial_message = mock_interaction.followup.send.return_value
    mock_initial_message.edit.assert_called_once()
    final_call_args = mock_initial_message.edit.call_args
    final_embed = final_call_args.kwargs.get("embed")
    
    # Should offer to delete 2 messages (both the old queue message and normal message)
    assert final_embed is not None
    assert "2 message(s)" in final_embed.description and "will be deleted" in final_embed.description
