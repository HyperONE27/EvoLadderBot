"""
Queue service for managing matchmaking queue state.

This service is the single source of truth for which players are currently in
the matchmaking queue. It provides centralized state management to prevent race
conditions and inconsistencies.
"""

import asyncio
from typing import Dict, List, Optional

from src.backend.services.matchmaking_service import Player
from src.bot.logging_config import log_queue, LogLevel


class QueueService:
    """
    Manages the matchmaking queue state.
    
    This service tracks which players are currently in the queue and provides
    methods to add, remove, and snapshot the queue state.
    """
    
    def __init__(self):
        """Initialize the queue service."""
        self._queued_players: Dict[int, Player] = {}
        self._lock = asyncio.Lock()
    
    async def add_player(self, player: Player) -> None:
        """
        Add a player to the matchmaking queue.
        
        Args:
            player: The Player object to add to the queue
        """
        async with self._lock:
            if player.discord_user_id in self._queued_players:
                log_queue(LogLevel.WARNING, f"Player {player.discord_user_id} already in queue", player_id=player.discord_user_id)
                return
            
            self._queued_players[player.discord_user_id] = player
            log_queue(LogLevel.INFO, f"Player added to queue (total: {len(self._queued_players)})", player_id=player.discord_user_id)
    
    async def remove_player(self, player_id: int) -> bool:
        """
        Remove a player from the matchmaking queue.
        
        Args:
            player_id: Discord user ID of the player to remove
            
        Returns:
            True if player was removed, False if player was not in queue
        """
        async with self._lock:
            if player_id in self._queued_players:
                del self._queued_players[player_id]
                log_queue(LogLevel.INFO, f"Player removed from queue (total: {len(self._queued_players)})", player_id=player_id)
                return True
            else:
                log_queue(LogLevel.WARNING, f"Player not in queue, cannot remove", player_id=player_id)
                return False
    
    def get_snapshot(self) -> List[Player]:
        """
        Get a snapshot of the current queue.
        
        This is a synchronous method that returns a copy of the current players
        in the queue. This snapshot can be safely used by the matchmaking algorithm
        without holding the lock.
        
        Returns:
            List of Player objects currently in the queue
        """
        # No lock needed - dictionary iteration is atomic in Python
        # We make a copy to prevent external modification
        return list(self._queued_players.values())
    
    async def remove_matched_players(self, player_ids: List[int]) -> int:
        """
        Remove multiple players from the queue after they've been matched.
        
        This is more efficient than calling remove_player multiple times.
        
        Args:
            player_ids: List of Discord user IDs to remove
            
        Returns:
            Number of players actually removed
        """
        async with self._lock:
            removed_count = 0
            for player_id in player_ids:
                if player_id in self._queued_players:
                    del self._queued_players[player_id]
                    removed_count += 1
            
            log_queue(LogLevel.INFO, f"Removed {removed_count} matched players from queue (total: {len(self._queued_players)})")
            return removed_count
    
    def get_queue_size(self) -> int:
        """
        Get the current size of the queue.
        
        Returns:
            Number of players currently in the queue
        """
        return len(self._queued_players)
    
    async def is_player_in_queue(self, player_id: int) -> bool:
        """
        Check if a player is currently in the queue.
        
        Args:
            player_id: Discord user ID to check
            
        Returns:
            True if player is in queue, False otherwise
        """
        async with self._lock:
            return player_id in self._queued_players
    
    async def get_player(self, player_id: int) -> Optional[Player]:
        """
        Get a specific player from the queue.
        
        Args:
            player_id: Discord user ID
            
        Returns:
            The Player object if in queue, None otherwise
        """
        async with self._lock:
            return self._queued_players.get(player_id)
    
    async def clear_queue(self) -> int:
        """
        Clear all players from the queue.
        
        Used primarily for testing and maintenance.
        
        Returns:
            Number of players that were in the queue
        """
        async with self._lock:
            count = len(self._queued_players)
            self._queued_players.clear()
            log_queue(LogLevel.INFO, f"Queue cleared ({count} players removed)")
            return count


# Global queue service instance
_queue_service: Optional[QueueService] = None


def initialize_queue_service() -> QueueService:
    """
    Initialize the global queue service.
    
    Returns:
        Initialized QueueService instance
    """
    global _queue_service
    _queue_service = QueueService()
    log_queue(LogLevel.INFO, "Global instance initialized")
    return _queue_service


def get_queue_service() -> Optional[QueueService]:
    """
    Get the global queue service instance.
    
    Returns:
        The global QueueService instance, or None if not initialized
    """
    return _queue_service

