"""
Tests for the NotificationService.
"""

import asyncio
import pytest
from src.backend.infrastructure.notification_service import NotificationService
from src.backend.services.matchmaking_service import MatchResult


@pytest.fixture
def notification_service():
    """Create a fresh notification service for each test."""
    return NotificationService()


@pytest.mark.asyncio
async def test_subscribe_creates_queue(notification_service):
    """Test that subscribing creates a queue for the player."""
    player_id = 12345
    
    queue = await notification_service.subscribe(player_id)
    
    assert isinstance(queue, asyncio.Queue)
    assert notification_service.get_subscriber_count() == 1


@pytest.mark.asyncio
async def test_subscribe_twice_returns_same_queue(notification_service):
    """Test that subscribing twice returns the same queue."""
    player_id = 12345
    
    queue1 = await notification_service.subscribe(player_id)
    queue2 = await notification_service.subscribe(player_id)
    
    assert queue1 is queue2
    assert notification_service.get_subscriber_count() == 1


@pytest.mark.asyncio
async def test_unsubscribe_removes_player(notification_service):
    """Test that unsubscribing removes the player's queue."""
    player_id = 12345
    
    await notification_service.subscribe(player_id)
    assert notification_service.get_subscriber_count() == 1
    
    await notification_service.unsubscribe(player_id)
    assert notification_service.get_subscriber_count() == 0


@pytest.mark.asyncio
async def test_unsubscribe_nonexistent_player(notification_service):
    """Test that unsubscribing a non-existent player doesn't raise an error."""
    player_id = 12345
    
    # Should not raise an exception
    await notification_service.unsubscribe(player_id)


@pytest.mark.asyncio
async def test_publish_match_found_notifies_both_players(notification_service):
    """Test that publishing a match notifies both players."""
    player_1_id = 11111
    player_2_id = 22222
    
    # Subscribe both players
    queue_1 = await notification_service.subscribe(player_1_id)
    queue_2 = await notification_service.subscribe(player_2_id)
    
    # Create a match result
    match = MatchResult(
        match_id=1,
        player_1_discord_id=player_1_id,
        player_2_discord_id=player_2_id,
        player_1_user_id="Player1",
        player_2_user_id="Player2",
        player_1_race="bw_terran",
        player_2_race="sc2_protoss",
        map_choice="TestMap",
        server_choice="US East",
        in_game_channel="scevo123"
    )
    
    # Publish the match
    await notification_service.publish_match_found(match)
    
    # Verify both players received the notification
    assert not queue_1.empty()
    assert not queue_2.empty()
    
    received_1 = await queue_1.get()
    received_2 = await queue_2.get()
    
    assert received_1 == match
    assert received_2 == match


@pytest.mark.asyncio
async def test_publish_match_with_unsubscribed_player(notification_service):
    """Test that publishing a match with an unsubscribed player logs a warning but doesn't crash."""
    player_1_id = 11111
    player_2_id = 22222
    
    # Only subscribe player 1
    queue_1 = await notification_service.subscribe(player_1_id)
    
    # Create a match result with both players
    match = MatchResult(
        match_id=1,
        player_1_discord_id=player_1_id,
        player_2_discord_id=player_2_id,
        player_1_user_id="Player1",
        player_2_user_id="Player2",
        player_1_race="bw_terran",
        player_2_race="sc2_protoss",
        map_choice="TestMap",
        server_choice="US East",
        in_game_channel="scevo123"
    )
    
    # Publish the match (should not crash)
    await notification_service.publish_match_found(match)
    
    # Verify player 1 received the notification
    assert not queue_1.empty()
    received_1 = await queue_1.get()
    assert received_1 == match


@pytest.mark.asyncio
async def test_listener_blocks_until_notification(notification_service):
    """Test that waiting on a queue blocks until a notification is published."""
    player_id = 12345
    
    queue = await notification_service.subscribe(player_id)
    
    match = MatchResult(
        match_id=1,
        player_1_discord_id=player_id,
        player_2_discord_id=99999,
        player_1_user_id="Player1",
        player_2_user_id="Player2",
        player_1_race="bw_terran",
        player_2_race="sc2_protoss",
        map_choice="TestMap",
        server_choice="US East",
        in_game_channel="scevo123"
    )
    
    # Create a task that waits for the notification
    async def wait_for_match():
        return await queue.get()
    
    wait_task = asyncio.create_task(wait_for_match())
    
    # Give the task a moment to start waiting
    await asyncio.sleep(0.01)
    
    # Task should not be done yet
    assert not wait_task.done()
    
    # Publish the match
    await notification_service.publish_match_found(match)
    
    # Wait for the task to complete
    result = await wait_task
    
    # Verify we got the match
    assert result == match


@pytest.mark.asyncio
async def test_clear_all_subscriptions(notification_service):
    """Test that clearing all subscriptions removes all players."""
    # Subscribe multiple players
    await notification_service.subscribe(11111)
    await notification_service.subscribe(22222)
    await notification_service.subscribe(33333)
    
    assert notification_service.get_subscriber_count() == 3
    
    # Clear all
    await notification_service.clear_all_subscriptions()
    
    assert notification_service.get_subscriber_count() == 0


@pytest.mark.asyncio
async def test_multiple_matches_to_same_player(notification_service):
    """Test that a player can receive multiple match notifications in their queue."""
    player_id = 12345
    
    queue = await notification_service.subscribe(player_id)
    
    # Publish two matches
    match1 = MatchResult(
        match_id=1,
        player_1_discord_id=player_id,
        player_2_discord_id=99999,
        player_1_user_id="Player1",
        player_2_user_id="Player2",
        player_1_race="bw_terran",
        player_2_race="sc2_protoss",
        map_choice="TestMap1",
        server_choice="US East",
        in_game_channel="scevo123"
    )
    
    match2 = MatchResult(
        match_id=2,
        player_1_discord_id=player_id,
        player_2_discord_id=88888,
        player_1_user_id="Player1",
        player_2_user_id="Player3",
        player_1_race="bw_zerg",
        player_2_race="sc2_terran",
        map_choice="TestMap2",
        server_choice="US West",
        in_game_channel="scevo456"
    )
    
    await notification_service.publish_match_found(match1)
    await notification_service.publish_match_found(match2)
    
    # Verify both are in the queue
    assert queue.qsize() == 2
    
    received_1 = await queue.get()
    received_2 = await queue.get()
    
    assert received_1 == match1
    assert received_2 == match2

