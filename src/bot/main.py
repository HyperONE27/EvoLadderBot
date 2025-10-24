import asyncio
import logging
import sys
import time

import discord
from discord.ext import commands

from src.backend.services.matchmaking_service import matchmaker
from src.backend.services.app_context import data_access_service
from src.bot.bot_setup import EvoLadderBot, shutdown_bot_resources
from src.bot.commands.activate_command import register_activate_command  # DISABLED: Obsolete command
from src.bot.commands.help_command import register_help_command
from src.bot.commands.leaderboard_command import register_leaderboard_command
from src.bot.commands.profile_command import register_profile_command
from src.bot.commands.prune_command import register_prune_command
from src.bot.commands.queue_command import on_message as handle_replay_message, register_queue_command
from src.bot.commands.setcountry_command import register_setcountry_command
from src.bot.commands.setup_command import register_setup_command
from src.bot.commands.termsofservice_command import register_termsofservice_command
from src.bot.config import EVOLADDERBOT_TOKEN


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Set specific log levels
logging.getLogger('discord').setLevel(logging.WARNING)  # Reduce Discord library noise
logging.getLogger('src.backend.services.performance_service').setLevel(logging.INFO)  # Show performance logs

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = EvoLadderBot(command_prefix="!", intents=intents)


async def initialize_backend_services():
    """
    Initialize all backend services eagerly during startup.
    
    This ensures that:
    1. DataAccessService loads all data before the first command is processed
    2. No "first request penalty" or race conditions during lazy initialization
    3. The write queue worker is started and ready to handle async writes
    
    This function should be called from on_ready() after the event loop is running.
    """
    print("[Startup] Initializing backend services...")
    start_time = time.time()
    
    # Initialize DataAccessService - loads all hot tables and starts write worker
    await data_access_service.initialize_async()
    
    elapsed = (time.time() - start_time) * 1000
    print(f"[Startup] Backend services initialized in {elapsed:.2f}ms")


@bot.event
async def on_ready():
    print(f"Bot online as {bot.user}")
    try:
        # Initialize all backend services BEFORE registering commands
        await initialize_backend_services()
        
        register_commands(bot)
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
        
        # Start the matchmaker
        asyncio.create_task(matchmaker.run())
        print("Matchmaker started")
        
        # Background tasks are started in bot_setup.py setup_hook
    except Exception as e:
        print("Sync failed:", e)

@bot.event
async def on_message(message):
    """Handle replay file detection for active match views."""
    await handle_replay_message(message, bot)

def register_commands(bot: commands.Bot):
    # register_activate_command(bot.tree)  # DISABLED: Obsolete command
    register_help_command(bot.tree)
    register_leaderboard_command(bot.tree)
    register_profile_command(bot.tree)
    register_prune_command(bot.tree)
    register_queue_command(bot.tree)
    register_setcountry_command(bot.tree)
    register_setup_command(bot.tree)
    register_termsofservice_command(bot.tree)

def setup_signal_handlers(bot: discord.Client):
    """Sets up signal handlers to ensure graceful shutdown."""
    import signal
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    def signal_handler(signum, frame):
        print(f"Received signal {signum}. Shutting down gracefully.")
        if loop.is_running():
            loop.create_task(bot.close())
        else:
            loop.run_until_complete(bot.close())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def main():
    # Set up signal handling for graceful shutdown
    setup_signal_handlers(bot)

    try:
        # The bot's run method is blocking, so we run it here.
        # The new setup_hook will handle async initialization.
        bot.run(EVOLADDERBOT_TOKEN, log_handler=None, log_level=logging.INFO)
    except discord.errors.LoginFailure:
        logger.fatal("Invalid Discord token. Please check your config.py file.")
        sys.exit(1)
    except Exception as e:
        logger.fatal(f"An unexpected error occurred: {e}")
    finally:
        # On exit, ensure resources are cleaned up
        # We need a new loop to run the async shutdown function
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                # If there's a running loop, create a task to do shutdown
                loop.create_task(shutdown_bot_resources(bot))
            else:
                # If not, run it to completion
                asyncio.run(shutdown_bot_resources(bot))
        except RuntimeError: # No running loop
            asyncio.run(shutdown_bot_resources(bot))
        except Exception as e:
            print(f"[Shutdown] An error occurred during final shutdown: {e}")


if __name__ == "__main__":
    main()