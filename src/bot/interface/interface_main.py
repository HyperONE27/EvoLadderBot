import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

from src.bot.interface.commands.activate_command import register_activate_command
from src.bot.interface.commands.leaderboard_command import register_leaderboard_command
from src.bot.interface.commands.queue_command import register_queue_command
from src.bot.interface.commands.setcountry_command import register_setcountry_command
from src.bot.interface.commands.setup_command import register_setup_command
from src.bot.interface.commands.termsofservice_command import register_termsofservice_command
from src.backend.services.matchmaking_service import matchmaker


intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

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
    except Exception as e:
        print("Sync failed:", e)

def register_commands(bot: commands.Bot):
    register_activate_command(bot.tree)
    register_leaderboard_command(bot.tree)
    register_queue_command(bot.tree)
    register_setcountry_command(bot.tree)
    register_setup_command(bot.tree)
    register_termsofservice_command(bot.tree)

if __name__ == "__main__":
    TOKEN = os.getenv("EVOLADDERBOT_TOKEN")
    bot.run(TOKEN)