"""
Bot lifecycle and configuration management.

This module handles:
- Custom bot class with global event handlers
- Resource initialization (database pool, process pool, cache)
- Resource cleanup at shutdown
"""

import asyncio
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import discord
from discord.ext import commands

from src.backend.db.connection_pool import close_pool, initialize_pool
from src.backend.db.test_connection_startup import test_database_connection
from src.backend.core.app_context import command_guard_service, leaderboard_service, ranking_service
from src.backend.infrastructure.cache_service import static_cache
from src.backend.services.command_guard_service import DMOnlyError
from src.backend.services.data_access_service import DataAccessService
from src.backend.monitoring.memory_monitor import initialize_memory_monitor, log_memory
from src.backend.services.performance_service import FlowTracker, performance_monitor
from src.backend.services.process_pool_health import set_bot_instance
from src.bot.components.command_guard_embeds import create_command_guard_error_embed
from src.bot.config import DATABASE_URL, DB_POOL_MAX_CONNECTIONS, DB_POOL_MIN_CONNECTIONS, WORKER_PROCESSES

# Add app_context import
from src.backend.core import app_context

logger = logging.getLogger(__name__)


def _health_check_worker():
    """
    Simple health check function for process pool.
    
    This function can be pickled and sent to worker processes.
    Returns a simple success indicator.
    """
    import os
    import time
    
    # Simple health indicators
    return {
        "status": "healthy",
        "pid": os.getpid(),
        "timestamp": time.time()
    }


class EvoLadderBot(commands.Bot):
    """
    Custom bot class with lifecycle management and global event handlers.
    
    Attributes:
        process_pool: ProcessPoolExecutor for CPU-bound tasks (replay parsing)
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.process_pool: ProcessPoolExecutor = None
        # Leaderboard cache task removed - DataAccessService handles this now
        self._process_pool_monitor_task = None
        self._memory_monitor_task = None
        self._process_pool_lock = asyncio.Lock()
        self._active_work_count = 0  # Track number of active tasks
        self._last_work_time = 0  # Track when work was last submitted

    async def setup_hook(self) -> None:
        """
        Asynchronous initialization method for the bot.
        
        This is called by discord.py after login but before the bot is connected to the websocket.
        It's the ideal place for async resource initialization.
        """
        await initialize_backend_services(self)
        self.start_background_tasks()

    async def on_interaction(self, interaction: discord.Interaction):
        """
        Global listener for all interactions to log command calls.
        
        This event fires for every interaction (slash commands, buttons, etc.)
        and logs slash command usage to the database asynchronously (non-blocking).
        
        Note: DM-only checks are done in individual command handlers, not here,
        because this listener runs alongside the command handler, not before it.
        """
        if interaction.type == discord.InteractionType.application_command:
            command_name = interaction.command.name if interaction.command else "unknown"
            user = interaction.user
            
            # Start performance tracking for this interaction
            flow = FlowTracker(f"interaction.{command_name}", user_id=user.id)
            flow.checkpoint("interaction_start")
            
            # Log command asynchronously (fire and forget - don't block command execution)
            asyncio.create_task(self._log_command_async(user.id, user.name, command_name))
            
            # Mark as logged immediately (actual write happens in background)
            flow.checkpoint("command_logged")
            
            # Complete flow tracking
            duration = flow.complete("success")
            
            # Check against performance thresholds
            performance_monitor.check_threshold(f"{command_name}_command", duration)
    
    async def _log_command_async(self, discord_uid: int, player_name: str, command: str):
        """
        Log command call asynchronously without blocking command execution.
        
        This runs in the background and will not slow down command responses.
        If logging fails, it logs an error but doesn't impact the user.
        
        Args:
            discord_uid: Discord user ID
            player_name: Discord username
            command: Command name
        """
        try:
            from src.backend.services.data_access_service import DataAccessService
            data_service = await DataAccessService.get_instance()
            await data_service.insert_command_call(discord_uid, player_name, command)
        except Exception as e:
            # Log error but don't fail the command
            logger.error(f"Failed to log command {command} for user {discord_uid}: {e}")
    
    def _track_work_start(self):
        """Track that work is starting on the process pool."""
        self._active_work_count += 1
        self._last_work_time = time.time()
        logger.debug("Process pool work started", extra={"active_count": self._active_work_count})
    
    def _track_work_end(self):
        """Track that work has completed on the process pool."""
        if self._active_work_count > 0:
            self._active_work_count -= 1
        logger.debug("Process pool work completed", extra={"active_count": self._active_work_count})
    
    def _is_worker_busy(self) -> bool:
        """Check if workers are currently busy with legitimate work."""
        return self._active_work_count > 0
    
    def _get_work_age(self) -> float:
        """Get the age of the oldest active work in seconds."""
        if self._last_work_time == 0:
            return 0
        return time.time() - self._last_work_time
    
    async def _restart_process_pool(self) -> bool:
        """
        Restart the process pool.
        
        Returns:
            True if restart was successful, False otherwise
        """
        async with self._process_pool_lock:
            try:
                # Shutdown old pool
                if self.process_pool:
                    logger.warning("Shutting down crashed process pool")
                    try:
                        self.process_pool.shutdown(wait=False, cancel_futures=True)
                    except Exception as e:
                        logger.warning("Error during process pool shutdown", extra={"error": str(e)})
                
                # Create new pool
                logger.info("Creating new process pool", extra={"worker_count": WORKER_PROCESSES})
                self.process_pool = ProcessPoolExecutor(max_workers=WORKER_PROCESSES)
                logger.info("Process pool restarted successfully")
                return True
                
            except Exception as e:
                logger.error(f"[Process Pool] ❌ Failed to restart process pool: {e}")
                return False
    
    async def _ensure_process_pool_healthy(self) -> bool:
        """
        Intelligent event-driven process pool health check.
        
        Only checks the process pool when it's actually needed for work.
        Uses intelligent timeouts based on worker status to avoid false positives
        when workers are legitimately busy with long-running tasks.
        
        Returns:
            True if pool is healthy or was successfully restarted, False otherwise
        """
        if not self.process_pool:
            logger.error("[Process Pool] Process pool is None, attempting restart...")
            return await self._restart_process_pool()
        
        # Determine appropriate timeout based on worker status
        if self._is_worker_busy():
            work_age = self._get_work_age()
            # If workers are busy, give them more time based on how long they've been working
            # Cap at 30 seconds to avoid infinite waits
            timeout = min(5.0 + (work_age * 0.1), 30.0)
            logger.debug("Process pool workers busy, using extended timeout", 
                        extra={"work_age_seconds": round(work_age, 1), "timeout_seconds": round(timeout, 1)})
        else:
            timeout = 5.0  # Standard timeout for idle workers
            logger.debug("Process pool workers idle, using standard timeout", extra={"timeout_seconds": timeout})
        
        # Test pool health with a simple task
        try:
            loop = asyncio.get_running_loop()
            # Submit a simple health check task
            future = loop.run_in_executor(
                self.process_pool,
                _health_check_worker
            )
            # Wait with intelligent timeout
            result = await asyncio.wait_for(future, timeout=timeout)
            
            # Validate the health check result
            if isinstance(result, dict) and result.get("status") == "healthy":
                logger.debug("Process pool health check passed", extra={"worker_pid": result['pid']})
                return True
            else:
                logger.error(f"[Process Pool] Health check returned invalid result: {result}")
                return await self._restart_process_pool()
                
        except asyncio.TimeoutError:
            # Timeout occurred - check if workers were legitimately busy
            if self._is_worker_busy():
                work_age = self._get_work_age()
                if work_age < 60:  # If work is less than 1 minute old, might be legitimate
                    logger.debug("Process pool health check timeout but workers busy, will retry", 
                                extra={"work_age_seconds": round(work_age, 1)})
                    # Don't restart immediately, let the work complete
                    return True
                else:
                    logger.error(f"[Process Pool] Health check timeout with old work (age: {work_age:.1f}s) - likely crashed")
                    return await self._restart_process_pool()
            else:
                logger.error("[Process Pool] Health check timeout with no active work - likely crashed")
                return await self._restart_process_pool()
                
        except Exception as e:
            logger.error(f"[Process Pool] Health check failed: {e}")
            logger.info("[Process Pool] Attempting to restart process pool...")
            return await self._restart_process_pool()
    
    # _refresh_leaderboard_cache_task() removed - DataAccessService handles this now
    
    async def _memory_monitor_task_loop(self):
        """
        Background task that periodically reports memory usage.
        
        Reports every 5 minutes and checks for potential memory leaks.
        """
        await self.wait_until_ready()
        logger.info("Starting periodic memory monitoring")
        
        from src.backend.monitoring.memory_monitor import get_memory_monitor
        
        while not self.is_closed():
            try:
                await asyncio.sleep(300)  # Report every 5 minutes
                
                monitor = get_memory_monitor()
                if monitor:
                    # Log current memory usage
                    monitor.log_memory_usage("Periodic check")
                    
                    # Check for potential leak
                    if monitor.check_memory_leak(threshold_mb=100.0):
                        # Generate detailed report
                        report = monitor.generate_report(include_allocations=True)
                        logger.info("Memory monitor report", extra={"report": report})
                        logger.warning("[Memory Monitor] Memory leak detected - see report above")
                        
                        # Force garbage collection
                        collected, freed = monitor.force_garbage_collection()
                        logger.info(f"[Memory Monitor] Forced GC: collected {collected} objects, "
                                   f"freed {freed:.2f} MB")
                
            except Exception as e:
                logger.error(f"[Memory Monitor] Error in monitoring task: {e}")
    
    def start_background_tasks(self):
        """Start all background tasks for the bot."""
        logger.info("Starting background tasks")
        
        # Start memory monitoring task
        self._memory_monitor_task = asyncio.create_task(self._memory_monitor_task_loop())
        logger.info("Memory monitor task started")

        # Background refresh tasks removed - DataAccessService handles this now
    
    def stop_background_tasks(self):
        """Stop all background tasks for the bot."""
        logger.info("Stopping background tasks")
        
        # Stop memory monitor task
        if self._memory_monitor_task and not self._memory_monitor_task.done():
            self._memory_monitor_task.cancel()
            logger.info("Memory monitor task stopped")
        
        # Background refresh tasks removed - DataAccessService handles this now


async def initialize_backend_services(bot: EvoLadderBot) -> None:
    """
    Initialize and attach all necessary backend services for the bot.
    
    This should be called from the bot's async setup_hook. It initializes:
    1. Database connection pool
    2. Static data cache
    3. Process pool
    4. DataAccessService (in-memory DB)
    5. Ranking service (dependent on DataAccessService)
    
    Args:
        bot: The EvoLadderBot instance to initialize
        
    Raises:
        SystemExit: If any critical resource fails to initialize
    """
    logger.info("Initializing backend services")
    
    # 1. Initialize Memory Monitor
    logger.info("Initializing memory monitor")
    initialize_memory_monitor(enable_tracemalloc=True)
    log_memory("Startup - baseline")
    
    # 2. Initialize Database Connection Pool
    try:
        initialize_pool(
            dsn=DATABASE_URL,
            min_conn=DB_POOL_MIN_CONNECTIONS,
            max_conn=DB_POOL_MAX_CONNECTIONS
        )
        log_memory("After DB pool init")
    except Exception as e:
        logger.fatal("Failed to initialize connection pool", exc_info=True)
        sys.exit(1)
    
    # 3. Test Database Connection
    success, message = test_database_connection()
    if not success:
        logger.fatal("Database connection test failed", extra={"error_message": message})
        sys.exit(1)
        
    # 4. Initialize Static Data Cache
    logger.info("Initializing static data cache")
    try:
        static_cache.initialize()
        log_memory("After static cache init")
    except Exception as e:
        logger.fatal("Failed to initialize static data cache", exc_info=True)
        sys.exit(1)
        
    # 5. Create and Attach Process Pool
    bot.process_pool = ProcessPoolExecutor(max_workers=WORKER_PROCESSES)
    logger.info("Initialized Process Pool", extra={"worker_count": WORKER_PROCESSES})
    log_memory("After process pool init")
    
    # 6. Register bot instance for global process pool health checking
    set_bot_instance(bot)
    logger.info("Process pool health checker registered")
    
    # 7. Initialize DataAccessService
    logger.info("Initializing DataAccessService")
    try:
        data_service = await DataAccessService.get_instance()
        log_memory("After DataAccessService init")
        logger.info("DataAccessService initialized successfully")
    except Exception as e:
        logger.fatal("Failed to initialize DataAccessService", exc_info=True)
        sys.exit(1)
        
    # 8. Refresh Ranking Service (depends on DataAccessService)
    logger.info("Performing initial rank calculation")
    try:
        # Use the singleton from app_context
        await app_context.ranking_service.trigger_refresh()
        log_memory("After ranking service refresh")
        logger.info("Ranking service refreshed successfully")
    except Exception as e:
        logger.fatal("Failed to refresh ranking service", exc_info=True)
        sys.exit(1)
    
    # 9. Performance monitoring is active
    logger.info("Performance monitoring ACTIVE")


async def shutdown_bot_resources(bot: EvoLadderBot) -> None:
    """
    Gracefully shut down all application resources.
    
    Args:
        bot: The EvoLadderBot instance to clean up
    """
    logger.info("Closing application resources")
    
    # 1. Stop Background Tasks
    bot.stop_background_tasks()
    
    # 2. Shutdown DataAccessService
    try:
        data_access_service = await DataAccessService.get_instance()
        if DataAccessService._initialized:
            await data_access_service.shutdown()
            logger.info("DataAccessService shutdown complete")
    except Exception as e:
        logger.error("Error shutting down DataAccessService", exc_info=True)
    
    # 3. Close Database Connection Pool
    close_pool()
    
    # 4. Shutdown Process Pool
    if bot.process_pool:
        logger.info("Shutting down process pool")
        bot.process_pool.shutdown(wait=True)
        logger.info("Process pool shutdown complete")
    
    logger.info("All resources closed")

