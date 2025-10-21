"""
Bot lifecycle and configuration management.

This module handles:
- Custom bot class with global event handlers
- Resource initialization (database pool, process pool, cache)
- Resource cleanup at shutdown
"""

import sys
import asyncio
import logging
import discord
from discord.ext import commands
from concurrent.futures import ProcessPoolExecutor

from src.bot.config import WORKER_PROCESSES, DATABASE_URL, DB_POOL_MIN_CONNECTIONS, DB_POOL_MAX_CONNECTIONS
from src.backend.db.connection_pool import initialize_pool, close_pool
from src.backend.db.test_connection_startup import test_database_connection
from src.backend.services.cache_service import static_cache
from src.backend.services.app_context import db_writer, command_guard_service, leaderboard_service
from src.backend.services.command_guard_service import DMOnlyError
from src.bot.components.command_guard_embeds import create_command_guard_error_embed
from src.backend.services.performance_service import FlowTracker, performance_monitor

logger = logging.getLogger(__name__)


class EvoLadderBot(commands.Bot):
    """
    Custom bot class with lifecycle management and global event handlers.
    
    Attributes:
        process_pool: ProcessPoolExecutor for CPU-bound tasks (replay parsing)
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.process_pool: ProcessPoolExecutor = None
        self._leaderboard_cache_task = None

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
    
    async def _refresh_leaderboard_cache_task(self):
        """
        Background task that periodically refreshes the leaderboard cache.
        
        This ensures the cache is always "hot" and users never have to wait
        for a database query when viewing the leaderboard. The task runs
        every 60 seconds (matching the cache TTL).
        """
        await self.wait_until_ready()
        print("[Background Task] Starting leaderboard cache refresh task...")
        
        while not self.is_closed():
            try:
                print("[Background Task] Refreshing leaderboard cache...")
                start_time = asyncio.get_event_loop().time()
                
                # Fetch leaderboard data - this will refresh the cache if needed
                # Pass the process pool to offload heavy computation
                # We don't care about the result, just that the cache is updated
                await leaderboard_service.get_leaderboard_data(
                    country_filter=None,
                    race_filter=None,
                    best_race_only=False,
                    current_page=1,
                    page_size=1,  # Only fetch 1 record to minimize processing
                    process_pool=self.process_pool  # Offload to worker process
                )
                
                duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                print(f"[Background Task] Leaderboard cache refreshed in {duration_ms:.2f}ms")
                
            except Exception as e:
                logger.error(f"[Background Task] Error refreshing leaderboard cache: {e}")
                print(f"[Background Task] Error refreshing leaderboard cache: {e}")
            
            # Wait 60 seconds before next refresh (matching cache TTL)
            await asyncio.sleep(60)
    
    def start_background_tasks(self):
        """Start all background tasks for the bot."""
        print("[Background Tasks] Starting background tasks...")
        
        # Start leaderboard cache refresh task
        self._leaderboard_cache_task = asyncio.create_task(self._refresh_leaderboard_cache_task())
        print("[Background Tasks] Leaderboard cache refresh task started")
    
    def stop_background_tasks(self):
        """Stop all background tasks for the bot."""
        print("[Background Tasks] Stopping background tasks...")
        
        if self._leaderboard_cache_task and not self._leaderboard_cache_task.done():
            self._leaderboard_cache_task.cancel()
            print("[Background Tasks] Leaderboard cache refresh task stopped")


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
    
    # 5. Performance monitoring is active
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

