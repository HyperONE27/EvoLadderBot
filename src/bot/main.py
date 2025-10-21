import asyncio
import logging

import discord
from discord.ext import commands

from src.backend.services.matchmaking_service import matchmaker
from src.bot.bot_setup import EvoLadderBot, initialize_bot_resources, shutdown_bot_resources
# from src.bot.commands.activate_command import register_activate_command  # DISABLED: Obsolete command
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


@bot.event
async def on_ready():
    print(f"Bot online as {bot.user}")
    try:
        register_commands(bot)
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
        
        # Start the matchmaker
        asyncio.create_task(matchmaker.run())
        print("Matchmaker started")
        
        # Start background tasks (leaderboard cache refresh, etc.)
        bot.start_background_tasks()
        print("Background tasks started")
    except Exception as e:
        print("Sync failed:", e)

@bot.event
async def on_message(message):
    """Handle replay file detection for active match views."""
    await handle_replay_message(message, bot)

def register_commands(bot: commands.Bot):
    # register_activate_command(bot.tree)  # DISABLED: Obsolete command
    register_leaderboard_command(bot.tree)
    register_profile_command(bot.tree)
    register_prune_command(bot.tree)
    register_queue_command(bot.tree)
    register_setcountry_command(bot.tree)
    register_setup_command(bot.tree)
    register_termsofservice_command(bot.tree)

if __name__ == "__main__":
    # Initialize all bot resources (database pool, cache, process pool)
    initialize_bot_resources(bot)
    
    try:
        # Run the bot
        bot.run(EVOLADDERBOT_TOKEN)
    finally:
        # Gracefully shut down all resources
        shutdown_bot_resources(bot)