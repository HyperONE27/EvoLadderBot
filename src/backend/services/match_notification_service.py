"""
Match notification service with retry logic.

Ensures players are reliably notified when matches are found,
with exponential backoff and fallback mechanisms.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Optional, Dict
import time

logger = logging.getLogger(__name__)


@dataclass
class MatchNotificationAttempt:
    """Track notification attempts for a match."""
    match_id: int
    player_discord_id: int
    attempts: int = 0
    last_attempt_time: float = 0
    success: bool = False
    error_message: Optional[str] = None


class MatchNotificationService:
    """
    Service for reliably notifying players when matches are found.
    
    Uses aggressive rapid retry logic to ensure notifications are delivered
    immediately. For critical user-facing notifications, we retry fast and often.
    """
    
    # Retry configuration - AGGRESSIVE for critical notifications
    MAX_RETRY_ATTEMPTS = 10  # More attempts
    RETRY_DELAY = 1  # Constant 500ms between retries (no backoff)
    # For critical match notifications, we want rapid retries, not exponential delays
    
    def __init__(self):
        self._pending_notifications: Dict[tuple, MatchNotificationAttempt] = {}
        self._lock = asyncio.Lock()
        self._retry_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        """Start the notification retry service."""
        if self._running:
            return
        
        self._running = True
        self._retry_task = asyncio.create_task(self._retry_loop())
        logger.info("[Match Notification] Service started")
    
    async def stop(self):
        """Stop the notification retry service."""
        self._running = False
        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
        logger.info("[Match Notification] Service stopped")
    
    async def notify_match_found(
        self,
        match_id: int,
        player_discord_id: int,
        notification_callback: Callable[[], asyncio.Future]
    ) -> bool:
        """
        Notify a player that a match was found.
        
        Args:
            match_id: The match ID
            player_discord_id: Discord user ID of the player
            notification_callback: Async function to call to send notification
            
        Returns:
            True if notification succeeded immediately, False if queued for retry
        """
        key = (match_id, player_discord_id)
        
        # Try immediate notification first
        try:
            await notification_callback()
            logger.info(f"[Match Notification] Match {match_id}: Notified player {player_discord_id} successfully")
            return True
        
        except Exception as e:
            logger.warning(f"[Match Notification] Match {match_id}: Failed to notify player {player_discord_id}: {e}")
            
            # Queue for retry
            async with self._lock:
                attempt = MatchNotificationAttempt(
                    match_id=match_id,
                    player_discord_id=player_discord_id,
                    attempts=1,
                    last_attempt_time=time.time(),
                    error_message=str(e)
                )
                self._pending_notifications[key] = attempt
            
            # Store callback for retry
            attempt.callback = notification_callback
            
            logger.info(f"[Match Notification] Match {match_id}: Queued for retry (player {player_discord_id})")
            return False
    
    async def _retry_loop(self):
        """Background loop that retries failed notifications rapidly."""
        while self._running:
            try:
                # Check frequently for critical notifications
                await asyncio.sleep(0.1)  # Check every 100ms for responsiveness
                
                # Get pending notifications that need retry
                to_retry = []
                current_time = time.time()
                
                async with self._lock:
                    for key, attempt in list(self._pending_notifications.items()):
                        if attempt.success:
                            # Clean up successful attempts
                            del self._pending_notifications[key]
                            continue
                        
                        # Check if it's time to retry (constant delay, no backoff)
                        if current_time - attempt.last_attempt_time >= self.RETRY_DELAY:
                            to_retry.append((key, attempt))
                
                # Retry notifications outside the lock
                for key, attempt in to_retry:
                    await self._retry_notification(key, attempt)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Match Notification] Error in retry loop: {e}")
    
    async def _retry_notification(self, key: tuple, attempt: MatchNotificationAttempt):
        """Retry a failed notification."""
        match_id, player_discord_id = key
        
        if attempt.attempts >= self.MAX_RETRY_ATTEMPTS:
            logger.error(
                f"[Match Notification] Match {match_id}: "
                f"Max retry attempts ({self.MAX_RETRY_ATTEMPTS}) reached for player {player_discord_id}"
            )
            async with self._lock:
                self._pending_notifications.pop(key, None)
            return
        
        # Attempt notification
        try:
            if hasattr(attempt, 'callback'):
                await attempt.callback()
            
            # Success!
            logger.info(
                f"[Match Notification] Match {match_id}: "
                f"Notified player {player_discord_id} on retry attempt {attempt.attempts}"
            )
            
            async with self._lock:
                attempt.success = True
                self._pending_notifications.pop(key, None)
        
        except Exception as e:
            # Retry failed, update attempt count
            attempt.attempts += 1
            attempt.last_attempt_time = time.time()
            attempt.error_message = str(e)
            
            logger.warning(
                f"[Match Notification] Match {match_id}: "
                f"Retry {attempt.attempts}/{self.MAX_RETRY_ATTEMPTS} failed for player {player_discord_id}: {e}"
            )
    
    
    async def get_pending_notifications(self, match_id: Optional[int] = None) -> list:
        """
        Get pending notifications for a match or all matches.
        
        Args:
            match_id: Optional match ID to filter by
            
        Returns:
            List of pending notification attempts
        """
        async with self._lock:
            if match_id is None:
                return list(self._pending_notifications.values())
            else:
                return [
                    attempt for (mid, _), attempt in self._pending_notifications.items()
                    if mid == match_id
                ]
    
    async def mark_notification_success(self, match_id: int, player_discord_id: int):
        """Manually mark a notification as successful (e.g., if player responds)."""
        key = (match_id, player_discord_id)
        async with self._lock:
            if key in self._pending_notifications:
                self._pending_notifications[key].success = True
                self._pending_notifications.pop(key, None)
                logger.info(f"[Match Notification] Match {match_id}: Marked player {player_discord_id} as notified")


# Global instance
match_notification_service = MatchNotificationService()
