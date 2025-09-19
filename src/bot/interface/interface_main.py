import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from src.bot.interface.interface_setup_command import register_setup_command
from src.bot.interface.interface_setcountry_command import register_setcountry_command
from src.bot.interface.interface_termsofservice_command import register_termsofservice_command
from src.bot.interface.interface_queue_command import register_queue_command
from src.bot.interface.interface_admin_commands import register_admin_commands

intents = discord.Intents.default()
intents.message_content = True  # Needed for DMs
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot online as {bot.user}")
    try:
        # Register slash commands
        register_setup_command(bot.tree)
        register_setcountry_command(bot.tree)
        register_termsofservice_command(bot.tree)
        register_queue_command(bot.tree)
        register_admin_commands(bot.tree)
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
        
        # Load matchmaking background task
        await bot.load_extension("src.bot.tasks.matchmaking_task")
        print("✅ Matchmaking task loaded")
        
    except Exception as e:
        print("Startup error:", e)

if __name__ == "__main__":
    load_dotenv()
    TOKEN = os.getenv("EVOLADDERBOT_TOKEN")
    bot.run(TOKEN)