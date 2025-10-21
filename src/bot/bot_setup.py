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
from src.backend.services.app_context import command_guard_service, db_writer, leaderboard_service
from src.backend.services.cache_service import static_cache
from src.backend.services.command_guard_service import DMOnlyError
from src.backend.services.performance_service import FlowTracker, performance_monitor
from src.backend.services.process_pool_health import set_bot_instance
from src.bot.components.command_guard_embeds import create_command_guard_error_embed
from src.bot.config import DATABASE_URL, DB_POOL_MAX_CONNECTIONS, DB_POOL_MIN_CONNECTIONS, WORKER_PROCESSES

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
        # self._leaderboard_cache_task = None  # DISABLED: No longer using periodic refresh
        self._process_pool_monitor_task = None
        self._process_pool_lock = asyncio.Lock()
        self._active_work_count = 0  # Track number of active tasks
        self._last_work_time = 0  # Track when work was last submitted

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
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                db_writer.insert_command_call,
                discord_uid,
                player_name,
                command
            )
        except Exception as e:
            # Log error but don't fail the command
            logger.error(f"Failed to log command {command} for user {discord_uid}: {e}")
    
    def _track_work_start(self):
        """Track that work is starting on the process pool."""
        self._active_work_count += 1
        self._last_work_time = time.time()
        print(f"[Process Pool] Work started (active: {self._active_work_count})")
    
    def _track_work_end(self):
        """Track that work has completed on the process pool."""
        if self._active_work_count > 0:
            self._active_work_count -= 1
        print(f"[Process Pool] Work completed (active: {self._active_work_count})")
    
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
                    print("[Process Pool] Shutting down crashed pool...")
                    try:
                        self.process_pool.shutdown(wait=False, cancel_futures=True)
                    except Exception as e:
                        logger.warning(f"[Process Pool] Error during shutdown: {e}")
                
                # Create new pool
                print(f"[Process Pool] Creating new pool with {WORKER_PROCESSES} worker(s)...")
                self.process_pool = ProcessPoolExecutor(max_workers=WORKER_PROCESSES)
                print("[Process Pool] ✅ Process pool restarted successfully")
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
            print(f"[Process Pool] Workers busy (age: {work_age:.1f}s), using extended timeout: {timeout:.1f}s")
        else:
            timeout = 5.0  # Standard timeout for idle workers
            print(f"[Process Pool] Workers idle, using standard timeout: {timeout:.1f}s")
        
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
                print(f"[Process Pool] ✅ Health check passed (PID: {result.get('pid', 'unknown')})")
                return True
            else:
                logger.error(f"[Process Pool] Health check returned invalid result: {result}")
                return await self._restart_process_pool()
                
        except asyncio.TimeoutError:
            # Timeout occurred - check if workers were legitimately busy
            if self._is_worker_busy():
                work_age = self._get_work_age()
                if work_age < 60:  # If work is less than 1 minute old, might be legitimate
                    print(f"[Process Pool] Health check timeout but workers busy (age: {work_age:.1f}s) - retrying later")
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
    
    # DISABLED: Periodic leaderboard cache refresh task removed for resource optimization
    # Cache will now be invalidated only when MMR changes occur
    # async def _refresh_leaderboard_cache_task(self):
    #     """
    #     DISABLED: Background task that periodically refreshes the leaderboard cache.
    #     
    #     This was removed to reduce idle CPU usage. Cache is now invalidated
    #     only when MMR changes occur, making it more efficient.
    #     """
    #     pass
    
    def start_background_tasks(self):
        """Start all background tasks for the bot."""
        print("[Background Tasks] Starting background tasks...")
        
        # DISABLED: Process pool monitor task removed for resource optimization
        # Process pool health is now checked on-demand when work is submitted
        # This eliminates idle spinning and reduces resource usage
        
        # DISABLED: Leaderboard cache refresh task removed for resource optimization
        # Cache will be invalidated only when MMR changes occur
        # self._leaderboard_cache_task = asyncio.create_task(self._refresh_leaderboard_cache_task())
        # print("[Background Tasks] Leaderboard cache refresh task started")
    
    def stop_background_tasks(self):
        """Stop all background tasks for the bot."""
        print("[Background Tasks] Stopping background tasks...")
        
        # DISABLED: Process pool monitor task removed for resource optimization
        # Process pool health is now checked on-demand when work is submitted
        
        # DISABLED: Leaderboard cache refresh task removed for resource optimization
        # Cache will be invalidated only when MMR changes occur


def initialize_bot_resources(bot: EvoLadderBot) -> None:
    """
    Initialize and attach all necessary resources for the bot.
    
    This should be called before running the bot. It initializes:
    1. Database connection pool
    2. Database connection test
    3. Static data cache (maps, races, regions, countries)
    4. Process pool for CPU-bound tasks
    
    Args:
        bot: The EvoLadderBot instance to initialize
        
    Raises:
        SystemExit: If any critical resource fails to initialize
    """
    print("[Startup] Initializing application resources...")
    
    # 1. Initialize Database Connection Pool
    try:
        initialize_pool(
            dsn=DATABASE_URL,
            min_conn=DB_POOL_MIN_CONNECTIONS,
            max_conn=DB_POOL_MAX_CONNECTIONS
        )
    except Exception as e:
        print(f"\n[FATAL] Failed to initialize connection pool: {e}")
        sys.exit(1)
    
    # 2. Test Database Connection
    success, message = test_database_connection()
    if not success:
        print(f"\n[FATAL] Database connection test failed: {message}")
        print("[FATAL] Bot cannot start without a working database connection.")
        print("[FATAL] Please fix the database configuration and try again.\n")
        sys.exit(1)
        
    # 3. Initialize Static Data Cache
    print("[Startup] Initializing static data cache...")
    try:
        static_cache.initialize()
    except Exception as e:
        print(f"\n[FATAL] Failed to initialize static data cache: {e}")
        print("[FATAL] Bot cannot start without static data.")
        print("[FATAL] Please check that data/misc/*.json files exist.\n")
        sys.exit(1)
        
    # 4. Create and Attach Process Pool
    bot.process_pool = ProcessPoolExecutor(max_workers=WORKER_PROCESSES)
    print(f"[INFO] Initialized Process Pool with {WORKER_PROCESSES} worker process(es)")
    
    # 5. Register bot instance for global process pool health checking
    set_bot_instance(bot)
    print("[INFO] Process pool health checker registered")
    
    # 6. Performance monitoring is active
    print("[INFO] Performance monitoring ACTIVE - All commands will be tracked")
    print("[INFO] Performance thresholds configured:")
    for cmd, threshold in performance_monitor.alert_thresholds.items():
        print(f"  - {cmd}: {threshold}ms")


def shutdown_bot_resources(bot: EvoLadderBot) -> None:
    """
    Gracefully shut down all application resources.
    
    This should be called when the bot is shutting down. It cleans up:
    1. Background tasks
    2. Database connection pool
    3. Process pool for CPU-bound tasks
    
    Args:
        bot: The EvoLadderBot instance to clean up
    """
    print("[Shutdown] Closing application resources...")
    
    # 1. Stop Background Tasks
    bot.stop_background_tasks()
    
    # 2. Close Database Connection Pool
    close_pool()
    
    # 3. Shutdown Process Pool
    if bot.process_pool:
        print("[Shutdown] Shutting down process pool...")
        bot.process_pool.shutdown(wait=True)
        print("[Shutdown] Process pool shutdown complete.")
    
    print("[Shutdown] All resources closed.")

