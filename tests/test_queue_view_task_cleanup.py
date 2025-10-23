"""
Test to verify QueueSearchingView properly cleans up async tasks.

This test ensures that background tasks created by QueueSearchingView
are properly cancelled when the view times out or is cancelled, preventing
memory leaks from uncancelled tasks holding references to view objects.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import discord

# Mock the required dependencies before importing
mock_matchmaker = MagicMock()
mock_matchmaker.is_player_in_queue = AsyncMock(return_value=False)
mock_matchmaker.remove_player = AsyncMock()
mock_matchmaker.get_queue_snapshot = MagicMock(return_value={
    'active_population': 5,
    'bw_only': 2,
    'sc2_only': 2,
    'both_races': 1
})
mock_matchmaker.get_next_matchmaking_time = MagicMock(return_value=1234567890)
mock_matchmaker.MATCH_INTERVAL_SECONDS = 30

mock_notification_service = MagicMock()
mock_notification_service.subscribe = AsyncMock()
mock_notification_service.unsubscribe = AsyncMock()

mock_queue_manager = MagicMock()
mock_queue_manager.has_view = AsyncMock(return_value=False)
mock_queue_manager.unregister = AsyncMock()


@pytest.mark.asyncio
async def test_on_timeout_cancels_tasks():
    """Test that on_timeout properly cancels background tasks."""
    
    with patch('src.bot.commands.queue_command.matchmaker', mock_matchmaker), \
         patch('src.bot.commands.queue_command.notification_service', mock_notification_service), \
         patch('src.bot.commands.queue_command.queue_searching_view_manager', mock_queue_manager):
        
        from src.bot.commands.queue_command import QueueSearchingView
        
        # Create mock player
        mock_player = MagicMock()
        mock_player.discord_user_id = 12345
        mock_player.user_id = 12345
        
        # Track all running tasks before creating view
        tasks_before = set(asyncio.all_tasks())
        
        # Create view with minimal setup
        view = QueueSearchingView(
            original_view=MagicMock(),
            selected_races=["bw_terran"],
            vetoed_maps=[],
            player=mock_player
        )
        
        # Give tasks a moment to start
        await asyncio.sleep(0.01)
        
        # Verify tasks were created
        tasks_after_creation = set(asyncio.all_tasks())
        new_tasks = tasks_after_creation - tasks_before
        assert len(new_tasks) >= 1, "Match task should have been created"
        
        # Verify match_task exists and is not done
        assert view.match_task is not None
        assert not view.match_task.done()
        
        # Call on_timeout
        await view.on_timeout()
        
        # Give cancellation a moment to process
        await asyncio.sleep(0.01)
        
        # Verify match_task was cancelled
        assert view.match_task.done() or view.match_task.cancelled(), \
            "match_task should be done or cancelled after on_timeout"
        
        # Verify no new tasks remain
        tasks_after_timeout = set(asyncio.all_tasks())
        remaining_new_tasks = tasks_after_timeout - tasks_before
        # Filter out the current test coroutine
        remaining_new_tasks = {t for t in remaining_new_tasks if not t.done()}
        
        assert len(remaining_new_tasks) == 0, \
            f"All background tasks should be cancelled, but {len(remaining_new_tasks)} remain"
        
        print("[Test] PASS: on_timeout cancels all background tasks")


@pytest.mark.asyncio
async def test_deactivate_cancels_tasks():
    """Test that deactivate properly cancels both match and status tasks."""
    
    with patch('src.bot.commands.queue_command.matchmaker', mock_matchmaker), \
         patch('src.bot.commands.queue_command.notification_service', mock_notification_service), \
         patch('src.bot.commands.queue_command.queue_searching_view_manager', mock_queue_manager):
        
        from src.bot.commands.queue_command import QueueSearchingView
        
        # Create mock player
        mock_player = MagicMock()
        mock_player.discord_user_id = 12346
        mock_player.user_id = 12346
        
        # Create view
        view = QueueSearchingView(
            original_view=MagicMock(),
            selected_races=["sc2_zerg"],
            vetoed_maps=[],
            player=mock_player
        )
        
        # Start status updates (creates status_task)
        view.start_status_updates()
        
        await asyncio.sleep(0.01)
        
        # Verify both tasks exist
        assert view.match_task is not None
        assert view.status_task is not None
        assert not view.match_task.done()
        assert not view.status_task.done()
        
        # Call deactivate
        view.deactivate()
        
        # Give cancellation a moment
        await asyncio.sleep(0.01)
        
        # Verify both tasks were cancelled
        assert view.match_task is None or view.match_task.done() or view.match_task.cancelled(), \
            "match_task should be cancelled"
        assert view.status_task is None or view.status_task.done() or view.status_task.cancelled(), \
            "status_task should be cancelled"
        
        # Verify is_active flag was set
        assert not view.is_active, "is_active should be False after deactivate"
        
        print("[Test] PASS: deactivate cancels all tasks and sets is_active=False")


@pytest.mark.asyncio
async def test_multiple_views_no_leaks():
    """Test that creating and destroying multiple views doesn't leak tasks."""
    
    with patch('src.bot.commands.queue_command.matchmaker', mock_matchmaker), \
         patch('src.bot.commands.queue_command.notification_service', mock_notification_service), \
         patch('src.bot.commands.queue_command.queue_searching_view_manager', mock_queue_manager):
        
        from src.bot.commands.queue_command import QueueSearchingView
        
        tasks_before = set(asyncio.all_tasks())
        
        # Create and destroy 5 views
        for i in range(5):
            mock_player = MagicMock()
            mock_player.discord_user_id = 10000 + i
            mock_player.user_id = 10000 + i
            
            view = QueueSearchingView(
                original_view=MagicMock(),
                selected_races=["bw_protoss"],
                vetoed_maps=[],
                player=mock_player
            )
            
            await asyncio.sleep(0.01)
            
            # Deactivate the view
            view.deactivate()
            await asyncio.sleep(0.01)
        
        # Check tasks after cleanup
        tasks_after = set(asyncio.all_tasks())
        remaining_tasks = tasks_after - tasks_before
        remaining_tasks = {t for t in remaining_tasks if not t.done()}
        
        assert len(remaining_tasks) == 0, \
            f"Expected 0 remaining tasks, but found {len(remaining_tasks)}"
        
        print("[Test] PASS: Multiple view lifecycles don't leak tasks")


@pytest.mark.asyncio
async def test_cancel_button_cleans_up_tasks():
    """Test that clicking Cancel button properly cleans up tasks."""
    
    with patch('src.bot.commands.queue_command.matchmaker', mock_matchmaker), \
         patch('src.bot.commands.queue_command.notification_service', mock_notification_service), \
         patch('src.bot.commands.queue_command.queue_searching_view_manager', mock_queue_manager):
        
        from src.bot.commands.queue_command import QueueSearchingView, CancelQueueButton
        
        # Create mock player
        mock_player = MagicMock()
        mock_player.discord_user_id = 12347
        mock_player.user_id = 12347
        
        # Create view
        original_view = MagicMock()
        original_view.get_embed = MagicMock(return_value=MagicMock())
        
        view = QueueSearchingView(
            original_view=original_view,
            selected_races=["bw_terran"],
            vetoed_maps=[],
            player=mock_player
        )
        
        await asyncio.sleep(0.01)
        
        # Verify task exists
        assert view.match_task is not None
        assert not view.match_task.done()
        
        # Find the cancel button
        cancel_button = None
        for item in view.children:
            if isinstance(item, CancelQueueButton):
                cancel_button = item
                break
        
        assert cancel_button is not None, "Cancel button should exist"
        
        # Mock the interaction
        mock_interaction = AsyncMock()
        mock_interaction.response = AsyncMock()
        mock_interaction.response.edit_message = AsyncMock()
        
        # Simulate clicking the cancel button
        await cancel_button.callback(mock_interaction)
        
        # Give cancellation a moment
        await asyncio.sleep(0.01)
        
        # Verify task was cancelled
        assert view.match_task is None or view.match_task.done() or view.match_task.cancelled(), \
            "match_task should be cancelled after clicking cancel button"
        
        # Verify deactivate was called
        assert not view.is_active, "View should be deactivated"
        
        print("[Test] PASS: Cancel button properly cleans up tasks")


if __name__ == "__main__":
    print("\nRunning Queue View Task Cleanup Tests...")
    print("="*80)
    
    asyncio.run(test_on_timeout_cancels_tasks())
    asyncio.run(test_deactivate_cancels_tasks())
    asyncio.run(test_multiple_views_no_leaks())
    asyncio.run(test_cancel_button_cleans_up_tasks())
    
    print("="*80)
    print("All task cleanup tests PASSED!")
    print("\nNo task leaks detected - all background tasks properly cancelled.")

