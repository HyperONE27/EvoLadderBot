import asyncio
import logging
import sys
import time

import discord
from discord.ext import commands

from src.backend.services.matchmaking_service import matchmaker
from src.backend.services.app_context import data_access_service
from src.bot.bot_setup import EvoLadderBot
from src.bot.commands.activate_command import register_activate_command  # DISABLED: Obsolete command
from src.bot.commands.admin_command import register_admin_commands
# from src.bot.commands.help_command import register_help_command
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
intents.members = True

bot = EvoLadderBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Bot online as {bot.user}")
    try:
        # Backend services are now initialized in setup_hook
        
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
    # Log SC2Replay detection at the entry point
    if message.attachments and any(a.filename.endswith('.SC2Replay') for a in message.attachments):
        logger.info(f"[Replay Detected] Channel={message.channel.id}, Author={message.author.name} ({message.author.id}), File={message.attachments[0].filename}")
    
    await handle_replay_message(message, bot)

@bot.event
async def on_disconnect():
    logger.warning("⚠️ [Discord Gateway] Bot disconnected")

@bot.event
async def on_resumed():
    logger.info("✅ [Discord Gateway] Connection resumed")

@bot.event  
async def on_connect():
    logger.info("🔗 [Discord Gateway] Bot connected")

def register_commands(bot: commands.Bot):
    # register_activate_command(bot.tree)  # DISABLED: Obsolete command
    register_admin_commands(bot.tree)
    # register_help_command(bot.tree)
    register_leaderboard_command(bot.tree)
    register_profile_command(bot.tree)
    register_prune_command(bot.tree)
    register_queue_command(bot.tree)
    register_setcountry_command(bot.tree)
    register_setup_command(bot.tree)
    register_termsofservice_command(bot.tree)

def main():
    # discord.py's bot.run() has built-in signal handling that will
    # call our custom EvoLadderBot.close() method on shutdown.
    # No custom signal handlers needed.

    try:
        # The bot's run method is blocking, so we run it here.
        # The new setup_hook will handle async initialization.
        bot.run(EVOLADDERBOT_TOKEN, log_handler=None, log_level=logging.INFO)
    except discord.errors.LoginFailure:
        logger.fatal("Invalid Discord token. Please check your config.py file.")
        sys.exit(1)
    except Exception as e:
        logger.fatal(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()