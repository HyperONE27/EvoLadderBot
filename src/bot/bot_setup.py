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

from src.bot.config import WORKER_PROCESSES, DATABASE_URL
from src.backend.db.connection_pool import initialize_pool, close_pool
from src.backend.db.test_connection_startup import test_database_connection
from src.backend.services.cache_service import static_cache
from src.backend.services.app_context import db_writer, command_guard_service
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
    
    # Commands that should only work in DMs
    DM_ONLY_COMMANDS = {
        "activate",
        "setup", 
        "setcountry",
        "termsofservice",
        "profile",
        "leaderboard",
        "queue"
    }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.process_pool: ProcessPoolExecutor = None

    async def on_interaction(self, interaction: discord.Interaction):
        """
        Global listener for all interactions to log command calls and enforce DM-only rules.
        
        This event fires for every interaction (slash commands, buttons, etc.)
        and logs slash command usage to the database asynchronously (non-blocking).
        """
        if interaction.type == discord.InteractionType.application_command:
            command_name = interaction.command.name if interaction.command else "unknown"
            user = interaction.user
            
            # Start performance tracking for this interaction
            flow = FlowTracker(f"interaction.{command_name}", user_id=user.id)
            flow.checkpoint("interaction_start")
            
            # Check if this is a DM-only command used outside of DMs
            if command_name in self.DM_ONLY_COMMANDS:
                try:
                    command_guard_service.require_dm(interaction)
                except DMOnlyError as e:
                    flow.checkpoint("dm_check_failed")
                    error_embed = create_command_guard_error_embed(e)
                    await interaction.response.send_message(embed=error_embed)
                    flow.complete("dm_check_failed")
                    return
            
            flow.checkpoint("dm_check_passed")
            
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
        initialize_pool(dsn=DATABASE_URL)
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
    1. Database connection pool
    2. Process pool for CPU-bound tasks
    
    Args:
        bot: The EvoLadderBot instance to clean up
    """
    print("[Shutdown] Closing application resources...")
    
    # 1. Close Database Connection Pool
    close_pool()
    
    # 2. Shutdown Process Pool
    if bot.process_pool:
        print("[Shutdown] Shutting down process pool...")
        bot.process_pool.shutdown(wait=True)
        print("[Shutdown] Process pool shutdown complete.")
    
    print("[Shutdown] All resources closed.")

