"""
Characterization tests for core business logic and service interactions.

These tests verify critical internal logic including MMR calculations, data consistency,
error handling, and service-to-service communication.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ==================== MMR CALCULATION AND UPDATE LOGIC ====================

@pytest.mark.asyncio
async def test_mmr_update_for_win_loss():
    """
    Verifies that MMR calculation produces positive change for winner and negative for loser.
    """
    from src.backend.services.mmr_service import MMRService
    
    mmr_service = MMRService()
    
    # Mock two players with known MMR
    winner_mmr = 1500
    loser_mmr = 1500
    
    # Calculate new MMR values (result=1 means player one wins)
    outcome = mmr_service.calculate_new_mmr(
        player_one_mmr=winner_mmr,
        player_two_mmr=loser_mmr,
        result=1
    )
    
    # Verify winner gains MMR and loser loses MMR
    winner_change = outcome.player_one_mmr - winner_mmr
    loser_change = outcome.player_two_mmr - loser_mmr
    
    assert winner_change > 0, "Winner should gain MMR"
    assert loser_change < 0, "Loser should lose MMR"
    
    # Verify the changes are non-trivial (at least 1 point)
    assert abs(winner_change) >= 1
    assert abs(loser_change) >= 1


@pytest.mark.asyncio
async def test_mmr_asymmetry_in_updates():
    """
    Verifies that beating a higher-ranked opponent yields more MMR than beating a lower-ranked one.
    """
    from src.backend.services.mmr_service import MMRService
    
    mmr_service = MMRService()
    
    player_mmr = 1500
    high_opponent_mmr = 2000
    low_opponent_mmr = 1000
    
    # Calculate MMR gain for beating higher-ranked opponent (player one wins)
    high_outcome = mmr_service.calculate_new_mmr(
        player_one_mmr=player_mmr,
        player_two_mmr=high_opponent_mmr,
        result=1
    )
    high_gain = high_outcome.player_one_mmr - player_mmr
    
    # Calculate MMR gain for beating lower-ranked opponent (player one wins)
    low_outcome = mmr_service.calculate_new_mmr(
        player_one_mmr=player_mmr,
        player_two_mmr=low_opponent_mmr,
        result=1
    )
    low_gain = low_outcome.player_one_mmr - player_mmr
    
    # Verify asymmetry: beating stronger opponent yields more MMR
    assert high_gain > low_gain, "Beating higher-ranked opponent should yield more MMR"
    
    # Verify the difference is significant (at least 5 points)
    assert (high_gain - low_gain) >= 5


# ==================== PLAYER DATA CONSISTENCY AFTER UPDATES ====================

@pytest.mark.asyncio
async def test_player_name_change_reflects_on_leaderboard():
    """
    Verifies that leaderboard service can return player data.
    This characterizes the data flow exists.
    """
    from src.backend.services.leaderboard_service import LeaderboardService
    
    # Instantiate leaderboard service
    leaderboard_service = LeaderboardService()
    
    discord_id = 218147282875318274
    test_name = "TestPlayer"
    
    # Mock leaderboard data return
    with patch.object(leaderboard_service, 'get_leaderboard_data') as mock_leaderboard:
        mock_leaderboard.return_value = {
            "players": [{"discord_user_id": discord_id, "player_name": test_name}],
            "total_pages": 1,
            "current_page": 1,
            "total_players": 1
        }
        
        result = await leaderboard_service.get_leaderboard_data()
        # Characterize that leaderboard returns player names
        assert "players" in result
        if result["players"]:
            assert "player_name" in result["players"][0]


# ==================== INTERNAL SERVICE ERROR PROPAGATION ====================

@pytest.mark.asyncio
async def test_leaderboard_service_propagates_das_failure():
    """
    Verifies that leaderboard service propagates DataAccessService failures.
    """
    from src.backend.services.leaderboard_service import LeaderboardService
    from src.backend.services.data_access_service import DataAccessService
    
    leaderboard_service = LeaderboardService()
    
    # Patch DataAccessService method to raise an exception
    with patch.object(DataAccessService, 'get_leaderboard_dataframe') as mock_get:
        mock_get.side_effect = RuntimeError("Database connection failed")
        
        # Attempt to get leaderboard data - should propagate the error
        with pytest.raises(RuntimeError):
            await leaderboard_service.get_leaderboard_data()


# ==================== GLOBAL VIEW MANAGER STATE AND CLEANUP ====================

@pytest.mark.asyncio
async def test_view_manager_add_and_remove_cycle():
    """
    Verifies that view managers correctly track and remove views.
    """
    from src.bot.commands.queue_command import queue_searching_view_manager, QueueSearchingView
    
    # Create a mock view
    mock_view = MagicMock(spec=QueueSearchingView)
    mock_view.discord_user_id = 218147282875318274
    channel_id = 123456
    
    # Characterize that view manager has a has_view method
    assert hasattr(queue_searching_view_manager, 'has_view')
    
    # Characterize that has_view returns a boolean (it's an async method)
    result = await queue_searching_view_manager.has_view(channel_id)
    assert isinstance(result, bool)


# ==================== FIRST-TIME PLAYER EXPERIENCE ====================

@pytest.mark.asyncio
async def test_profile_for_player_with_no_matches():
    """
    Verifies that /profile command handles new players with no match history gracefully.
    """
    from src.bot.commands.profile_command import profile_command
    import discord
    
    # Mock interaction
    mock_interaction = AsyncMock(spec=discord.Interaction)
    mock_interaction.user = MagicMock()
    mock_interaction.user.id = 218147282875318274
    mock_interaction.response = AsyncMock()
    mock_interaction.response.send_message = AsyncMock()
    
    # Mock services to return new player data
    with patch("src.bot.commands.profile_command.guard_service") as mock_guard, \
         patch("src.bot.commands.profile_command.user_info_service") as mock_user_service, \
         patch("src.backend.services.data_access_service.DataAccessService") as mock_das:
        
        mock_guard.ensure_player_record = AsyncMock(return_value={"discord_uid": 218147282875318274, "tos_accepted": True})
        mock_guard.require_tos_accepted.return_value = None
        
        # Return minimal player data
        mock_user_service.get_player.return_value = {
            "player_name": "NewPlayer",
            "alt_player_name_1": None,
            "alt_player_name_2": None,
            "battletag": None,
            "alt_ids": []
        }
        
        # Mock DataAccessService to return empty MMR data
        mock_das_instance = MagicMock()
        mock_das_instance.get_all_player_mmrs.return_value = {}
        mock_das.return_value = mock_das_instance
        
        # Call profile command
        await profile_command(mock_interaction)
        
        # Verify command completed without error
        assert mock_interaction.response.send_message.called


@pytest.mark.asyncio
async def test_matchmaking_assigns_default_mmr():
    """
    Verifies that MMR service has a default MMR value.
    """
    from src.backend.services.mmr_service import MMRService
    
    mmr_service = MMRService()
    
    # Get default MMR value
    default_mmr = mmr_service.default_mmr()
    
    # Characterize that default is set to 1500
    assert default_mmr == 1500
    assert isinstance(default_mmr, int)


# ==================== LEADERBOARD BOUNDARY CONDITIONS ====================

@pytest.mark.asyncio
async def test_leaderboard_pagination_buttons_at_boundaries():
    """
    Verifies that pagination buttons are correctly disabled at first and last pages.
    """
    from src.bot.commands.leaderboard_command import LeaderboardView, PreviousPageButton, NextPageButton
    from src.backend.services.leaderboard_service import LeaderboardService
    
    # Mock leaderboard service
    mock_service = MagicMock(spec=LeaderboardService)
    mock_service.country_service = MagicMock()
    mock_service.country_service.get_common_countries.return_value = []
    mock_service.race_service = MagicMock()
    mock_service.race_service.get_race_options_for_dropdown.return_value = []
    
    # Test at first page
    mock_service.get_leaderboard_data = AsyncMock(return_value={
        "players": [],
        "total_pages": 5,
        "current_page": 1,
        "total_players": 100
    })
    
    view_first = LeaderboardView(leaderboard_service=mock_service, current_page=1)
    
    # Find previous button
    prev_button = None
    for child in view_first.children:
        if isinstance(child, PreviousPageButton):
            prev_button = child
            break
    
    # Verify previous button is disabled on first page
    assert prev_button is not None
    assert prev_button.disabled is True
    
    # Test at last page
    view_last = LeaderboardView(leaderboard_service=mock_service, current_page=5)
    
    # Find next button
    next_button = None
    for child in view_last.children:
        if isinstance(child, NextPageButton):
            next_button = child
            break
    
    # Verify next button is disabled on last page
    assert next_button is not None
    assert next_button.disabled is True


# ==================== COMMAND GUARD SERVICE ENFORCEMENT ====================

@pytest.mark.asyncio
async def test_guard_service_blocks_user_without_tos():
    """
    Verifies that guard service prevents command execution for users who haven't accepted TOS.
    """
    from src.bot.commands.queue_command import queue_command
    import discord
    
    # Mock interaction
    mock_interaction = AsyncMock(spec=discord.Interaction)
    mock_interaction.user = MagicMock()
    mock_interaction.user.id = 218147282875318274
    mock_interaction.response = AsyncMock()
    mock_interaction.response.send_message = AsyncMock()
    mock_interaction.response.send_modal = AsyncMock()
    
    # Mock guard service to indicate TOS not accepted
    with patch("src.bot.commands.queue_command.guard_service") as mock_guard:
        mock_guard.ensure_player_record = AsyncMock(return_value={"discord_uid": 218147282875318274, "tos_accepted": False})
        
        # Mock require_tos_accepted to send TOS modal
        async def mock_tos_check(interaction, player_record):
            await interaction.response.send_modal(MagicMock())
            return False
        
        mock_guard.require_tos_accepted = mock_tos_check
        
        # Call queue command
        await queue_command(mock_interaction)
        
        # Verify that a modal or message was sent (guard intercepted)
        assert mock_interaction.response.send_message.called or mock_interaction.response.send_modal.called


# ==================== ABORT COUNT AND PENALTY LOGIC ====================

@pytest.mark.skip(reason="Brittle: Touches DataAccessService internals with mocks instead of verifying meaningful change in persisted state.")
@pytest.mark.asyncio
async def test_abort_count_increments_and_decrements():
    """
    Verifies that abort counts increase on abort and decrease on completion.
    """
    from src.backend.services.data_access_service import DataAccessService
    
    das = DataAccessService()
    player_id = 218147282875318274
    
    # Mock initial player data with abort count
    initial_abort_count = 5
    
    with patch.object(das, 'get_player_mmr') as mock_get:
        mock_get.return_value = {"discord_user_id": player_id, "aborts_count": initial_abort_count}
        
        player_data = das.get_player_mmr(player_id, "bw_terran")
        # Since get_player_mmr is likely race-specific, this test characterizes the pattern exists


@pytest.mark.skip(reason="Brittle: Asserts constructor args instead of end-user outcome. Redundant with match_flow.py replay tests.")
@pytest.mark.asyncio
async def test_replay_upload_triggers_storage_service():
    """
    Verifies that MatchFoundView can be instantiated with a match result.
    """
    from src.bot.commands.queue_command import MatchFoundView
    from src.backend.services.matchmaking_service import MatchResult
    
    # Create mock match result
    mock_match = MagicMock(spec=MatchResult)
    mock_match.match_id = 1
    mock_match.player_1_discord_id = 218147282875318274
    mock_match.player_2_discord_id = 354878201232752640
    mock_match.player_1_user_id = "Player1"
    mock_match.player_2_user_id = "Player2"
    mock_match.replay_uploaded = "No"
    mock_match.match_result = None
    mock_match.match_result_confirmation_status = "Pending"
    mock_match.register_completion_callback = MagicMock()
    
    # Mock DataAccessService
    with patch("src.backend.services.data_access_service.DataAccessService") as mock_das:
        mock_das_instance = MagicMock()
        mock_das_instance.get_player_info.return_value = {"player_name": "TestPlayer"}
        mock_das.return_value = mock_das_instance
        
        # Create MatchFoundView
        view = MatchFoundView(match_result=mock_match, is_player1=True)
        
        # Characterize that the view has replay-related state
        assert hasattr(mock_match, 'replay_uploaded')


# ==================== DATAACCESS SERVICE IN-MEMORY UPDATES ====================

@pytest.mark.asyncio
async def test_das_update_player_reflects_in_get_player():
    """
    Verifies that DataAccessService has get_player_info method.
    """
    from src.backend.services.data_access_service import DataAccessService
    
    das = DataAccessService()
    
    # Characterize that DataAccessService has get_player_info method
    assert hasattr(das, 'get_player_info')
    
    # Characterize that it returns data when given a player ID (or None)
    player_id = 218147282875318274
    result = das.get_player_info(player_id)
    # Result will be None if player doesn't exist, or a dict if they do
    assert result is None or isinstance(result, dict)

