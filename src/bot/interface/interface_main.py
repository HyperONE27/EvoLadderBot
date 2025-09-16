import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from src.bot.interface.interface_commands import register_commands

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot online as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print("Sync failed:", e)

if __name__ == "__main__":
    load_dotenv()
    TOKEN = os.getenv("EVOLADDERBOT_TOKEN")
    register_commands(bot)
    bot.run(TOKEN)