"""
Tests for the QueueService.
"""

import pytest
from src.backend.services.queue_service import QueueService
from src.backend.services.matchmaking_service import Player, QueuePreferences


def create_test_player(discord_id: int, user_id: str = None) -> Player:
    """Helper to create a test player."""
    if user_id is None:
        user_id = f"Player{discord_id}"
    
    preferences = QueuePreferences(
        selected_races=["bw_terran"],
        vetoed_maps=[],
        discord_user_id=discord_id,
        user_id=user_id
    )
    
    return Player(
        discord_user_id=discord_id,
        user_id=user_id,
        preferences=preferences
    )


@pytest.fixture
def queue_service():
    """Create a fresh queue service for each test."""
    return QueueService()


@pytest.mark.asyncio
async def test_add_player_to_queue(queue_service):
    """Test adding a player to the queue."""
    player = create_test_player(12345)
    
    await queue_service.add_player(player)
    
    assert queue_service.get_queue_size() == 1
    assert await queue_service.is_player_in_queue(12345)


@pytest.mark.asyncio
async def test_add_same_player_twice(queue_service):
    """Test that adding the same player twice doesn't duplicate them."""
    player = create_test_player(12345)
    
    await queue_service.add_player(player)
    await queue_service.add_player(player)
    
    assert queue_service.get_queue_size() == 1


@pytest.mark.asyncio
async def test_remove_player_from_queue(queue_service):
    """Test removing a player from the queue."""
    player = create_test_player(12345)
    
    await queue_service.add_player(player)
    assert queue_service.get_queue_size() == 1
    
    result = await queue_service.remove_player(12345)
    
    assert result is True
    assert queue_service.get_queue_size() == 0
    assert not await queue_service.is_player_in_queue(12345)


@pytest.mark.asyncio
async def test_remove_nonexistent_player(queue_service):
    """Test removing a player that's not in the queue."""
    result = await queue_service.remove_player(99999)
    
    assert result is False


@pytest.mark.asyncio
async def test_get_snapshot(queue_service):
    """Test getting a snapshot of the queue."""
    player1 = create_test_player(11111)
    player2 = create_test_player(22222)
    player3 = create_test_player(33333)
    
    await queue_service.add_player(player1)
    await queue_service.add_player(player2)
    await queue_service.add_player(player3)
    
    snapshot = queue_service.get_snapshot()
    
    assert len(snapshot) == 3
    assert player1 in snapshot
    assert player2 in snapshot
    assert player3 in snapshot


@pytest.mark.asyncio
async def test_snapshot_is_independent(queue_service):
    """Test that modifying a snapshot doesn't affect the queue."""
    player1 = create_test_player(11111)
    player2 = create_test_player(22222)
    
    await queue_service.add_player(player1)
    await queue_service.add_player(player2)
    
    snapshot = queue_service.get_snapshot()
    
    # Modify the snapshot
    snapshot.clear()
    
    # Queue should be unchanged
    assert queue_service.get_queue_size() == 2


@pytest.mark.asyncio
async def test_remove_matched_players(queue_service):
    """Test removing multiple matched players at once."""
    players = [create_test_player(i) for i in range(10)]
    
    for player in players:
        await queue_service.add_player(player)
    
    assert queue_service.get_queue_size() == 10
    
    # Remove players 0, 2, 4, 6, 8
    matched_ids = [0, 2, 4, 6, 8]
    removed_count = await queue_service.remove_matched_players(matched_ids)
    
    assert removed_count == 5
    assert queue_service.get_queue_size() == 5
    
    # Verify the right players were removed
    for player_id in matched_ids:
        assert not await queue_service.is_player_in_queue(player_id)
    
    # Verify the others remain
    for player_id in [1, 3, 5, 7, 9]:
        assert await queue_service.is_player_in_queue(player_id)


@pytest.mark.asyncio
async def test_remove_matched_players_with_nonexistent(queue_service):
    """Test removing matched players where some don't exist."""
    player1 = create_test_player(11111)
    player2 = create_test_player(22222)
    
    await queue_service.add_player(player1)
    await queue_service.add_player(player2)
    
    # Try to remove 3 players, but only 2 exist
    removed_count = await queue_service.remove_matched_players([11111, 22222, 33333])
    
    assert removed_count == 2
    assert queue_service.get_queue_size() == 0


@pytest.mark.asyncio
async def test_get_player(queue_service):
    """Test getting a specific player from the queue."""
    player = create_test_player(12345, "TestPlayer")
    
    await queue_service.add_player(player)
    
    retrieved = await queue_service.get_player(12345)
    
    assert retrieved is not None
    assert retrieved.discord_user_id == 12345
    assert retrieved.user_id == "TestPlayer"


@pytest.mark.asyncio
async def test_get_nonexistent_player(queue_service):
    """Test getting a player that's not in the queue."""
    retrieved = await queue_service.get_player(99999)
    
    assert retrieved is None


@pytest.mark.asyncio
async def test_clear_queue(queue_service):
    """Test clearing the entire queue."""
    players = [create_test_player(i) for i in range(5)]
    
    for player in players:
        await queue_service.add_player(player)
    
    assert queue_service.get_queue_size() == 5
    
    count = await queue_service.clear_queue()
    
    assert count == 5
    assert queue_service.get_queue_size() == 0


@pytest.mark.asyncio
async def test_concurrent_adds(queue_service):
    """Test that concurrent adds don't cause race conditions."""
    import asyncio
    
    async def add_player(player_id):
        player = create_test_player(player_id)
        await queue_service.add_player(player)
    
    # Add 100 players concurrently
    tasks = [add_player(i) for i in range(100)]
    await asyncio.gather(*tasks)
    
    assert queue_service.get_queue_size() == 100


@pytest.mark.asyncio
async def test_concurrent_adds_and_removes(queue_service):
    """Test that concurrent adds and removes don't cause race conditions."""
    import asyncio
    
    async def add_player(player_id):
        player = create_test_player(player_id)
        await queue_service.add_player(player)
    
    async def remove_player(player_id):
        await queue_service.remove_player(player_id)
    
    # Add players 0-99
    add_tasks = [add_player(i) for i in range(100)]
    await asyncio.gather(*add_tasks)
    
    # Remove even-numbered players concurrently
    remove_tasks = [remove_player(i) for i in range(0, 100, 2)]
    await asyncio.gather(*remove_tasks)
    
    # Should have 50 players remaining (odd-numbered)
    assert queue_service.get_queue_size() == 50
    
    # Verify odd-numbered players are still there
    for i in range(1, 100, 2):
        assert await queue_service.is_player_in_queue(i)

