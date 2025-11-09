"""
Test suite for interaction handling refactoring.

Tests the new architecture where:
1. Prune command sends immediate response with disabled buttons
2. Queue command uses persistent channel_id/message_id tracking
3. All backend-initiated notifications use _edit_original_message
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import discord

# Test data
TEST_USER_1 = 218147282875318274
TEST_USER_2 = 354878201232752640


@pytest.fixture
def mock_interaction():
    """Create a mock Discord interaction."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user = Mock()
    interaction.user.id = TEST_USER_1
    interaction.user.name = "TestPlayer1"
    interaction.channel = AsyncMock()
    interaction.channel.id = 1234567890
    interaction.channel.send = AsyncMock()
    interaction.client = Mock()
    interaction.client.user = Mock()
    interaction.client.user.id = 999999999
    
    # Mock response
    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    
    # Mock followup and edit
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.edit_original_response = AsyncMock()
    
    # Mock original_response() to return a message
    mock_message = AsyncMock()
    mock_message.id = 1111111111
    interaction.original_response = AsyncMock(return_value=mock_message)
    
    return interaction


@pytest.mark.asyncio
@patch('src.bot.commands.prune_command.command_guard_service')
@patch('src.bot.commands.prune_command.FlowTracker')
async def test_prune_sends_immediate_response(mock_flow_tracker, mock_guard_service, mock_interaction):
    """Test that /prune sends an immediate 'Analyzing...' response."""
    from src.bot.commands.prune_command import prune_command
    
    # Setup guard service mocks
    mock_player = {"discord_uid": TEST_USER_1, "player_name": "TestPlayer1", "tos_accepted": True}
    mock_guard_service.ensure_player_record = AsyncMock(return_value=mock_player)
    mock_guard_service.require_tos_accepted.return_value = None
    
    # Mock FlowTracker
    mock_flow = Mock()
    mock_flow_tracker.return_value = mock_flow
    
    # Mock channel history to return no messages
    mock_interaction.channel.history = Mock()
    async def mock_history(*args, **kwargs):
        return []
    mock_interaction.channel.history.return_value.__aiter__ = lambda _: mock_history().__aiter__()
    
    # Call the command
    await prune_command(mock_interaction)
    
    # Verify immediate response was sent
    mock_interaction.response.send_message.assert_called_once()
    
    # Verify the response contains "Analyzing" embed
    call_args = mock_interaction.response.send_message.call_args
    assert call_args is not None
    embed = call_args.kwargs.get('embed')
    assert embed is not None
    assert "Analyzing" in embed.title
    
    # Verify buttons were disabled in initial response
    view = call_args.kwargs.get('view')
    assert view is not None
    for item in view.children:
        assert item.disabled is True


@pytest.mark.asyncio
@patch('src.bot.commands.queue_command.guard_service')
@patch('src.bot.commands.queue_command.DataAccessService')
@patch('src.bot.commands.queue_command.matchmaker')
@patch('src.bot.commands.queue_command.notification_service')
@patch('src.bot.commands.queue_command.queue_searching_view_manager')
async def test_queue_captures_message_ids(
    mock_view_manager,
    mock_notification_service,
    mock_matchmaker,
    mock_das,
    mock_guard_service,
    mock_interaction
):
    """Test that queue command captures channel_id and message_id."""
    from src.bot.commands.queue_command import JoinQueueButton
    from src.bot.commands.queue_command import QueueView
    
    # Setup guard service
    mock_player = {"discord_uid": TEST_USER_1, "player_name": "TestPlayer1", "tos_accepted": True}
    mock_guard_service.ensure_player_record = AsyncMock(return_value=mock_player)
    
    # Setup DataAccessService
    mock_data_service = Mock()
    mock_data_service.get_player_preferences.return_value = {
        "last_chosen_races": '["bw_terran"]',
        "last_chosen_vetoes": '[]'
    }
    mock_das.return_value = mock_data_service
    
    # Setup matchmaker
    mock_matchmaker.add_player = AsyncMock()
    
    # Setup view manager
    mock_view_manager.has_view = AsyncMock(return_value=False)
    mock_view_manager.register = AsyncMock()
    
    # Create a QueueView with a race selected
    view = await QueueView.create(
        discord_user_id=TEST_USER_1,
        default_races=["bw_terran"],
        default_maps=[]
    )
    
    # Create the button and attach the view
    button = JoinQueueButton()
    button.view = view
    
    # Mock interaction.response.defer()
    mock_interaction.response.defer = AsyncMock()
    
    # Call the button callback
    await button.callback(mock_interaction)
    
    # Verify edit_original_response was called (to show searching view)
    assert mock_interaction.edit_original_response.called
    
    # Verify original_response() was called to get message ID
    assert mock_interaction.original_response.called


@pytest.mark.asyncio
async def test_match_found_view_no_last_interaction_dependency():
    """Test that MatchFoundView doesn't require last_interaction for backend notifications."""
    from src.bot.commands.queue_command import MatchFoundView
    from src.backend.services.matchmaking_service import MatchResult
    
    # Create a mock match result
    match_result = MatchResult(
        match_id=1,
        player_1_discord_id=TEST_USER_1,
        player_2_discord_id=TEST_USER_2,
        player_1_user_id="Player1",
        player_2_user_id="Player2",
        player_1_race="bw_terran",
        player_2_race="bw_protoss",
        map_choice="Destination",
        server_choice="US-WEST",
        in_game_channel="TestChannel"
    )
    
    # Disable the completion callback registration for this test
    match_result.register_completion_callback = lambda x: None
    
    # Create view
    view = MatchFoundView(match_result, is_player1=True)
    
    # Set channel and message_id (simulating propagation)
    view.channel = AsyncMock()
    view.channel.send = AsyncMock()
    view.original_message_id = 12345
    
    # Mock _edit_original_message to simulate successful edit
    view._edit_original_message = AsyncMock(return_value=True)
    
    # Simulate abort notification from backend (no interaction available)
    await view.handle_completion_notification("abort", {"match_id": 1, "match_data": {}})
    
    # Verify _edit_original_message was called (using persistent IDs, not interaction)
    assert view._edit_original_message.called
    
    # Verify channel.send was called for follow-up (using channel, not interaction.followup)
    assert view.channel.send.called


@pytest.mark.asyncio
@patch('src.backend.services.matchmaking_service.DataAccessService')
@patch('src.backend.services.matchmaking_service.match_completion_service')
async def test_abort_triggers_completion_check(mock_completion_service, mock_das):
    """Test that aborting a match triggers completion check for both players."""
    from src.backend.services.matchmaking_service import matchmaker
    
    # Setup DataAccessService
    mock_data_service = Mock()
    mock_data_service.abort_match = AsyncMock(return_value=True)
    mock_das.return_value = mock_data_service
    
    # Setup completion service
    mock_completion_service.check_match_completion = AsyncMock()
    
    # Abort a match
    success = await matchmaker.abort_match(match_id=1, player_discord_uid=TEST_USER_1)
    
    # Verify abort was successful
    assert success is True
    
    # Verify data service abort was called
    mock_data_service.abort_match.assert_called_once_with(1, TEST_USER_1)
    
    # Give asyncio time to schedule the completion check task
    await asyncio.sleep(0.1)
    
    # Verify completion check was triggered
    # Note: asyncio.create_task schedules the task, so we need to wait
    assert mock_completion_service.check_match_completion.called


@pytest.mark.asyncio
async def test_all_terminal_states_use_same_pattern():
    """Test that abort, complete, and conflict all use the same _edit_original_message pattern."""
    from src.bot.commands.queue_command import MatchFoundView
    from src.backend.services.matchmaking_service import MatchResult
    
    # Create a mock match result
    match_result = MatchResult(
        match_id=1,
        player_1_discord_id=TEST_USER_1,
        player_2_discord_id=TEST_USER_2,
        player_1_user_id="Player1",
        player_2_user_id="Player2",
        player_1_race="bw_terran",
        player_2_race="bw_protoss",
        map_choice="Destination",
        server_choice="US-WEST",
        in_game_channel="TestChannel"
    )
    
    # Disable callback registration
    match_result.register_completion_callback = lambda x: None
    
    # Test each terminal state
    for status in ["abort", "complete", "conflict"]:
        # Create fresh view for each test
        view = MatchFoundView(match_result, is_player1=True)
        view.channel = AsyncMock()
        view.channel.send = AsyncMock()
        view.original_message_id = 12345
        view._edit_original_message = AsyncMock(return_value=True)
        
        # Prepare test data based on status
        if status == "complete":
            data = {
                "match_id": 1,
                "match_result_raw": 1,
                "p1_mmr_change": 15,
                "p2_mmr_change": -15,
                "p1_info": {"country": "US", "player_name": "Player1"},
                "p2_info": {"country": "US", "player_name": "Player2"},
                "p1_name": "Player1",
                "p2_name": "Player2",
                "p1_race": "bw_terran",
                "p2_race": "bw_protoss",
                "player_1_discord_uid": TEST_USER_1,
                "player_2_discord_uid": TEST_USER_2,
                "p1_current_mmr": 1500,
                "p2_current_mmr": 1500
            }
        else:
            data = {"match_id": 1, "match_data": {}}
        
        # Simulate notification
        await view.handle_completion_notification(status, data)
        
        # Verify _edit_original_message was called for all terminal states
        assert view._edit_original_message.called, f"_edit_original_message not called for {status}"
        
        # Verify no reliance on last_interaction
        # (The test passes if it doesn't raise an AttributeError)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

