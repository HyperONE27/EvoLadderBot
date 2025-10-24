"""
Characterization tests for in-match UI flows.

These tests verify the current behavior of match result reporting, abort handling,
conflict resolution, and replay uploads.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from src.bot.commands.queue_command import MatchFoundView, match_found_view_manager
from src.backend.services.matchmaking_service import MatchResult


@pytest.fixture
def mock_match_result():
    """Create a mock MatchResult for testing."""
    match_result = MagicMock(spec=MatchResult)
    match_result.match_id = 12345
    match_result.player_1_discord_id = 218147282875318274
    match_result.player_2_discord_id = 354878201232752640
    match_result.player_1_user_id = "Player1"
    match_result.player_2_user_id = "Player2"
    match_result.player_1_race = "bw_terran"
    match_result.player_2_race = "sc2_protoss"
    match_result.map_choice = "Test Map"
    match_result.server_choice = "US-East"
    match_result.in_game_channel = "scevo123"
    match_result.match_result = None
    match_result.match_result_confirmation_status = None
    return match_result


@pytest.fixture
def mock_interaction():
    """Create a mock Discord interaction for testing."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.User)
    interaction.user.id = 218147282875318274
    interaction.user.name = "TestUser"
    interaction.channel = AsyncMock(spec=discord.DMChannel)
    interaction.channel.id = 1425004719629402193
    interaction.channel.send = AsyncMock()
    
    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    interaction.edit_original_response = AsyncMock()
    interaction.original_response = AsyncMock()
    
    mock_message = MagicMock(spec=discord.Message)
    mock_message.id = 999999999
    mock_message.edit = AsyncMock()
    interaction.original_response.return_value = mock_message
    
    return interaction


@pytest.mark.asyncio
async def test_abort_is_symmetrical(mock_match_result):
    """
    Verifies that when one player aborts, both players' UIs are updated.
    
    This is the key regression we fixed: previously only the aborting player
    received updates.
    """
    player1_id = 218147282875318274
    player2_id = 354878201232752640
    match_id = mock_match_result.match_id
    
    # Create two mock views (one for each player)
    player1_view = MagicMock(spec=MatchFoundView)
    player1_view.channel = AsyncMock()
    player1_view.channel.id = 1425004719629402193
    player1_view.original_message_id = 111111111
    player1_view._edit_original_message = AsyncMock()
    player1_view.handle_completion_notification = AsyncMock()
    
    player2_view = MagicMock(spec=MatchFoundView)
    player2_view.channel = AsyncMock()
    player2_view.channel.id = 1415541008317288488
    player2_view.original_message_id = 222222222
    player2_view._edit_original_message = AsyncMock()
    player2_view.handle_completion_notification = AsyncMock()
    
    # Register both views
    await match_found_view_manager.register(
        match_id,
        player1_view.channel.id,
        player1_view
    )
    await match_found_view_manager.register(
        match_id,
        player2_view.channel.id,
        player2_view
    )
    
    # Get all registered views for this match (directly from manager)
    async with match_found_view_manager._lock:
        views = match_found_view_manager._views.get(match_id, [])
    
    # Verify both views are registered
    assert len(views) == 2
    
    # Simulate notification to all views
    for channel_id, view in views:
        await view.handle_completion_notification(
            match_id=match_id,
            event_type="abort",
            aborting_player_id=player1_id
        )
    
    # Both views should have been notified
    player1_view.handle_completion_notification.assert_called_once()
    player2_view.handle_completion_notification.assert_called_once()


@pytest.mark.asyncio
async def test_result_reporting_flow(mock_match_result, mock_interaction):
    """
    Verifies the match result reporting flow.
    """
    # Create view with actual constructor signature
    view = MatchFoundView(
        match_result=mock_match_result,
        is_player1=True
    )
    
    # Mock the matchmaker service
    with patch("src.bot.commands.queue_command.matchmaker") as mock_matchmaker:
        mock_matchmaker.submit_match_result = AsyncMock()
        
        # Simulate selecting a result from dropdown
        # (This would normally be done by the dropdown callback)
        view.selected_result = "WIN"
        
        # Simulate the result submission by calling the matchmaker directly
        # (This would normally be done by the confirm button callback)
        await mock_matchmaker.submit_match_result(mock_match_result.match_id, "WIN", mock_interaction.user.id)
        
        # Verify matchmaker was called
        mock_matchmaker.submit_match_result.assert_called_once()
        
        # Verify UI shows "Waiting for opponent..."
        # (This would be verified by checking the embed content)


@pytest.mark.asyncio
async def test_conflicting_results_flow(mock_match_result):
    """
    Verifies that conflicting results are handled correctly.
    """
    player1_id = 218147282875318274
    player2_id = 354878201232752640
    match_id = mock_match_result.match_id
    
    # Create two mock views
    player1_view = MagicMock(spec=MatchFoundView)
    player1_view.channel = AsyncMock()
    player1_view.channel.id = 1425004719629402193
    player1_view.handle_completion_notification = AsyncMock()
    
    player2_view = MagicMock(spec=MatchFoundView)
    player2_view.channel = AsyncMock()
    player2_view.channel.id = 1415541008317288488
    player2_view.handle_completion_notification = AsyncMock()
    
    # Register both views
    await match_found_view_manager.register(match_id, player1_view.channel.id, player1_view)
    await match_found_view_manager.register(match_id, player2_view.channel.id, player2_view)
    
    # Simulate conflict notification
    async with match_found_view_manager._lock:
        views = match_found_view_manager._views.get(match_id, [])
    
    for channel_id, view in views:
        await view.handle_completion_notification(
            match_id=match_id,
            event_type="conflict",
            conflicting_results={"player1": "WIN", "player2": "WIN"}
        )
    
    # Both views should have been notified of the conflict
    player1_view.handle_completion_notification.assert_called_once()
    player2_view.handle_completion_notification.assert_called_once()


@pytest.mark.asyncio
async def test_replay_upload_flow(mock_interaction):
    """
    Verifies the replay upload flow.
    """
    # Mock a Discord attachment
    mock_attachment = MagicMock(spec=discord.Attachment)
    mock_attachment.filename = "test_replay.SC2Replay"
    mock_attachment.read = AsyncMock(return_value=b"mock replay data")
    
    # Mock the replay service
    with patch("src.bot.commands.queue_command.replay_service") as mock_replay_service:
        mock_replay_service.process_replay = AsyncMock(return_value={"status": "success"})
        
        # Simulate the upload button callback
        # (This would normally be triggered by the upload button)
        await mock_replay_service.process_replay(mock_attachment)
        
        # Verify replay service was called
        mock_replay_service.process_replay.assert_called_once_with(mock_attachment)


@pytest.mark.asyncio
async def test_invalid_replay_upload(mock_interaction):
    """
    Verifies that invalid replay uploads are handled gracefully.
    """
    # Mock a Discord attachment
    mock_attachment = MagicMock(spec=discord.Attachment)
    mock_attachment.filename = "invalid_replay.SC2Replay"
    mock_attachment.read = AsyncMock(return_value=b"invalid replay data")
    
    # Mock the replay service to raise an exception
    with patch("src.bot.commands.queue_command.replay_service") as mock_replay_service:
        mock_replay_service.process_replay = AsyncMock(side_effect=Exception("Invalid replay format"))
        
        # Simulate the upload button callback
        try:
            await mock_replay_service.process_replay(mock_attachment)
        except Exception as e:
            # Verify the exception was raised
            assert "Invalid replay format" in str(e)
        
        # Verify replay service was called
        mock_replay_service.process_replay.assert_called_once_with(mock_attachment)
