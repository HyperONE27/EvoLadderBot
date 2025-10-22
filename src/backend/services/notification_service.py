"""
Notification service for push-based match notifications.

This service provides a real-time, event-driven communication channel from the
matchmaking backend to individual player frontend components. It eliminates the
need for polling and enables instant match notifications.
"""

import asyncio
import logging
from typing import Dict, Optional

from src.backend.services.matchmaking_service import MatchResult

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Manages push-based notifications for match events.
    
    Each player who joins the queue subscribes to notifications via an asyncio.Queue.
    When a match is found, the service pushes the result to both players' queues.
    """
    
    def __init__(self):
        """Initialize the notification service."""
        self._player_listeners: Dict[int, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
    
    async def subscribe(self, player_id: int) -> asyncio.Queue:
        """
        Subscribe a player to match notifications.
        
        Args:
            player_id: Discord user ID of the player
            
        Returns:
            An asyncio.Queue that will receive match notifications for this player
        """
        async with self._lock:
            if player_id in self._player_listeners:
                logger.warning(f"[NotificationService] Player {player_id} already subscribed")
                return self._player_listeners[player_id]
            
            queue = asyncio.Queue()
            self._player_listeners[player_id] = queue
            logger.info(f"[NotificationService] Player {player_id} subscribed")
            return queue
    
    async def unsubscribe(self, player_id: int) -> None:
        """
        Unsubscribe a player from match notifications.
        
        Args:
            player_id: Discord user ID of the player
        """
        async with self._lock:
            if player_id in self._player_listeners:
                del self._player_listeners[player_id]
                logger.info(f"[NotificationService] Player {player_id} unsubscribed")
            else:
                logger.warning(f"[NotificationService] Player {player_id} was not subscribed")
    
    async def publish_match_found(self, match: MatchResult) -> None:
        """
        Publish a match found event to both players.
        
        Args:
            match: The match result containing player IDs and match details
        """
        player_1_id = match.player_1_discord_id
        player_2_id = match.player_2_discord_id
        
        async with self._lock:
            # Notify player 1
            if player_1_id in self._player_listeners:
                queue = self._player_listeners[player_1_id]
                await queue.put(match)
                logger.info(f"[NotificationService] Notified player {player_1_id} of match {match.match_id}")
            else:
                logger.warning(f"[NotificationService] Player {player_1_id} not subscribed when match {match.match_id} found")
            
            # Notify player 2
            if player_2_id in self._player_listeners:
                queue = self._player_listeners[player_2_id]
                await queue.put(match)
                logger.info(f"[NotificationService] Notified player {player_2_id} of match {match.match_id}")
            else:
                logger.warning(f"[NotificationService] Player {player_2_id} not subscribed when match {match.match_id} found")
    
    def get_subscriber_count(self) -> int:
        """
        Get the current number of subscribed players.
        
        Returns:
            Number of players currently subscribed to notifications
        """
        return len(self._player_listeners)
    
    async def clear_all_subscriptions(self) -> None:
        """
        Clear all subscriptions. Used primarily for testing and cleanup.
        """
        async with self._lock:
            self._player_listeners.clear()
            logger.info("[NotificationService] All subscriptions cleared")


# Global notification service instance
_notification_service: Optional[NotificationService] = None


def initialize_notification_service() -> NotificationService:
    """
    Initialize the global notification service.
    
    Returns:
        Initialized NotificationService instance
    """
    global _notification_service
    _notification_service = NotificationService()
    logger.info("[NotificationService] Global instance initialized")
    return _notification_service


def get_notification_service() -> Optional[NotificationService]:
    """
    Get the global notification service instance.
    
    Returns:
        The global NotificationService instance, or None if not initialized
    """
    return _notification_service

