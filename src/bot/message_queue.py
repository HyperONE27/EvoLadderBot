"""
Prioritized message queue for Discord API calls.

This module implements a two-tier message queue system that ensures interaction
responses are always prioritized over notifications and admin alerts. All outbound
Discord API calls are routed through this queue to enforce rate limits and maintain
deterministic ordering.

Architecture:
- Interaction Queue (high priority): Slash command responses, followups, edits
- Notification Queue (low priority): Match notifications, admin alerts, channel messages
- Single worker task that always empties interaction queue before touching notifications
- Rate limiting: 40 messages/second (configurable)
- Retry strategy: Re-queue to back on failure (max 3 attempts)

Both queues are unbounded by design; all jobs must eventually be sent. The global rate
limiter ensures throughput control instead of backpressure.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from src.bot.config import DISCORD_MESSAGE_RATE_LIMIT

logger = logging.getLogger(__name__)


@dataclass
class MessageQueueJob:
    """
    A job representing a Discord API call to be executed.
    
    Attributes:
        operation: Zero-argument async callable that returns a fresh coroutine on each
                   invocation. NOT a coroutine object itself - must be callable to
                   support retries.
        future: asyncio.Future for result propagation. The same Future instance is
                reused across all retry attempts so the caller continues to await
                the same object.
        retry_count: Number of retry attempts already made (max 3)
        job_type: "interaction" or "notification" for logging purposes
    """
    operation: Callable[[], Awaitable]
    future: asyncio.Future
    retry_count: int = 0
    job_type: str = "unknown"


class MessageQueue:
    """
    Prioritized message queue for Discord API calls.
    
    Manages two queues with strict priority ordering:
    - Interaction queue: Always processed first
    - Notification queue: Only processed when interaction queue is empty
    
    The worker continuously checks the interaction queue and preempts notification
    processing if new interactions arrive.
    """
    
    def __init__(self):
        """Initialize the message queue with unbounded queues."""
        # Unbounded queues by design - we never drop messages
        self._interaction_queue: asyncio.Queue = asyncio.Queue()
        self._notification_queue: asyncio.Queue = asyncio.Queue()
        
        # Worker state
        self._worker_task: Optional[asyncio.Task] = None
        self._running: bool = False
        
        # Rate limiting state
        self._rate_limit: float = DISCORD_MESSAGE_RATE_LIMIT
        self._min_interval: float = 1.0 / self._rate_limit  # 0.025 seconds for 40 msg/sec
        self._last_send_time: float = 0.0
        
        logger.info(f"[MessageQueue] Initialized with rate limit: {self._rate_limit} msg/sec "
                   f"(min interval: {self._min_interval*1000:.1f}ms)")
    
    async def start(self):
        """Start the worker task."""
        if self._running:
            logger.warning("[MessageQueue] Already running")
            return
        
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("[MessageQueue] Worker task started")
    
    async def stop(self):
        """
        Gracefully stop the worker and drain pending jobs.
        
        This will process all remaining jobs before shutting down.
        """
        if not self._running:
            logger.warning("[MessageQueue] Not running")
            return
        
        logger.info("[MessageQueue] Stopping worker task...")
        self._running = False
        
        if self._worker_task:
            await self._worker_task
            logger.info("[MessageQueue] Worker task stopped")
        
        # Log any remaining jobs
        interaction_remaining = self._interaction_queue.qsize()
        notification_remaining = self._notification_queue.qsize()
        
        if interaction_remaining > 0 or notification_remaining > 0:
            logger.warning(
                f"[MessageQueue] Shutdown with pending jobs: "
                f"{interaction_remaining} interactions, {notification_remaining} notifications"
            )
    
    async def enqueue_interaction(self, operation: Callable[[], Awaitable]) -> asyncio.Future:
        """
        Enqueue an interaction-related Discord API call (high priority).
        
        Args:
            operation: Zero-argument async callable that performs the Discord API call
            
        Returns:
            asyncio.Future that will be resolved with the result or exception
        """
        future = asyncio.Future()
        job = MessageQueueJob(
            operation=operation,
            future=future,
            retry_count=0,
            job_type="interaction"
        )
        await self._interaction_queue.put(job)
        return future
    
    async def enqueue_notification(self, operation: Callable[[], Awaitable]) -> asyncio.Future:
        """
        Enqueue a notification-related Discord API call (low priority).
        
        Args:
            operation: Zero-argument async callable that performs the Discord API call
            
        Returns:
            asyncio.Future that will be resolved with the result or exception
        """
        future = asyncio.Future()
        job = MessageQueueJob(
            operation=operation,
            future=future,
            retry_count=0,
            job_type="notification"
        )
        await self._notification_queue.put(job)
        return future
    
    async def _worker_loop(self):
        """
        Main worker loop that processes jobs with strict priority.
        
        Algorithm:
        1. Always process ALL interactions first
        2. After each notification job, re-check interaction queue before continuing
        3. Small sleep if both queues empty to prevent busy-wait
        """
        logger.info("[MessageQueue] Worker loop started")
        
        while self._running:
            try:
                # ALWAYS process ALL interactions first
                while not self._interaction_queue.empty():
                    job = await self._interaction_queue.get()
                    await self._execute_job(job, "interaction")
                
                # Only touch notifications if interactions are empty
                # After each notification job, re-check interaction queue before continuing
                if not self._notification_queue.empty():
                    job = await self._notification_queue.get()
                    await self._execute_job(job, "notification")
                else:
                    # Small sleep to prevent busy-wait when both queues empty
                    await asyncio.sleep(0.01)
            
            except Exception as e:
                logger.error(f"[MessageQueue] Worker loop error: {e}", exc_info=True)
                await asyncio.sleep(0.1)  # Prevent tight error loop
        
        logger.info("[MessageQueue] Worker loop stopped")
    
    async def _enforce_rate_limit(self):
        """
        Enforce rate limiting using timer-based delays.
        
        This ensures we never exceed DISCORD_MESSAGE_RATE_LIMIT messages per second.
        The delay is calculated based on the time since the last send, not based on
        network I/O wait times.
        """
        now = time.time()
        time_since_last = now - self._last_send_time
        
        if time_since_last < self._min_interval:
            sleep_time = self._min_interval - time_since_last
            await asyncio.sleep(sleep_time)
        
        self._last_send_time = time.time()
    
    async def _execute_job(self, job: MessageQueueJob, queue_type: str):
        """
        Execute a single job with rate limiting and retry logic.
        
        Args:
            job: The job to execute
            queue_type: "interaction" or "notification" for re-queue routing
        """
        # Enforce rate limit BEFORE making the call
        await self._enforce_rate_limit()
        
        try:
            # Call the operation to get a fresh coroutine, then await it
            result = await job.operation()
            
            # Resolve the future with the result
            if not job.future.done():
                job.future.set_result(result)
            
            logger.debug(f"[MessageQueue] {job.job_type} job succeeded (retry: {job.retry_count})")
        
        except Exception as e:
            # Retry logic
            if job.retry_count < 3:
                job.retry_count += 1
                logger.warning(
                    f"[MessageQueue] {job.job_type} job failed (attempt {job.retry_count}/3): {e}. "
                    f"Re-queuing to back..."
                )
                
                # Re-queue to back of same queue (keeps same Future)
                if queue_type == "interaction":
                    await self._interaction_queue.put(job)
                else:
                    await self._notification_queue.put(job)
            else:
                # Max retries exceeded, propagate exception
                logger.error(
                    f"[MessageQueue] {job.job_type} job failed after 3 attempts: {e}",
                    exc_info=True
                )
                
                if not job.future.done():
                    job.future.set_exception(e)
    
    def get_queue_stats(self) -> dict:
        """
        Get current queue statistics for monitoring.
        
        Returns:
            Dict with interaction_count, notification_count, and running status
        """
        return {
            "interaction_count": self._interaction_queue.qsize(),
            "notification_count": self._notification_queue.qsize(),
            "running": self._running,
            "rate_limit": self._rate_limit
        }


# Global singleton instance
_message_queue: Optional[MessageQueue] = None


def initialize_message_queue() -> MessageQueue:
    """
    Initialize the global message queue singleton.
    
    Returns:
        Initialized MessageQueue instance
    """
    global _message_queue
    _message_queue = MessageQueue()
    logger.info("[MessageQueue] Global instance initialized")
    return _message_queue


def get_message_queue() -> Optional[MessageQueue]:
    """
    Get the global message queue instance.
    
    Returns:
        The global MessageQueue instance, or None if not initialized
    """
    return _message_queue

