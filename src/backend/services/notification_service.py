"""
Notification service for push-based match notifications.

This service provides a real-time, event-driven communication channel from the
matchmaking backend to individual player frontend components. It eliminates the
need for polling and enables instant match notifications.
"""

import asyncio
from typing import Dict, Optional

from src.backend.services.matchmaking_service import MatchResult
from src.bot.logging_config import log_notifications, LogLevel


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
                log_notifications(LogLevel.WARNING, f"Player {player_id} already subscribed", player_id=player_id)
                return self._player_listeners[player_id]
            
            queue = asyncio.Queue()
            self._player_listeners[player_id] = queue
            log_notifications(LogLevel.INFO, f"Player subscribed", player_id=player_id)
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
                log_notifications(LogLevel.INFO, f"Player unsubscribed", player_id=player_id)
            else:
                log_notifications(LogLevel.WARNING, f"Player was not subscribed", player_id=player_id)
    
    async def publish_match_found(self, match: MatchResult) -> None:
        """
        Publish a match found event to both players.
        
        Args:
            match: The match result containing player IDs and match details
        """
        import time
        start_time = time.perf_counter()
        
        player_1_id = match.player_1_discord_id
        player_2_id = match.player_2_discord_id
        
        async with self._lock:
            # Notify player 1
            if player_1_id in self._player_listeners:
                queue = self._player_listeners[player_1_id]
                await queue.put(match)
                log_notifications(LogLevel.INFO, f"Notified player of match {match.match_id}", player_id=player_1_id)
            else:
                log_notifications(LogLevel.WARNING, f"Player not subscribed when match {match.match_id} found", player_id=player_1_id)
            
            # Notify player 2
            if player_2_id in self._player_listeners:
                queue = self._player_listeners[player_2_id]
                await queue.put(match)
                log_notifications(LogLevel.INFO, f"Notified player of match {match.match_id}", player_id=player_2_id)
            else:
                log_notifications(LogLevel.WARNING, f"Player not subscribed when match {match.match_id} found", player_id=player_2_id)
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        if duration_ms > 10:
            log_notifications(LogLevel.WARNING, f"Match {match.match_id} notification took {duration_ms:.1f}ms")
        else:
            log_notifications(LogLevel.DEBUG, f"Match {match.match_id} notification took {duration_ms:.1f}ms")
    
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
            log_notifications(LogLevel.INFO, "All subscriptions cleared")


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
    log_notifications(LogLevel.INFO, "Global instance initialized")
    return _notification_service


def get_notification_service() -> Optional[NotificationService]:
    """
    Get the global notification service instance.
    
    Returns:
        The global NotificationService instance, or None if not initialized
    """
    return _notification_service

