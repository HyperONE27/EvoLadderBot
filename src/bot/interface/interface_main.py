import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from src.bot.interface.interface_setup_command import register_setup_command
from src.bot.interface.interface_setcountry_command import register_setcountry_command
from src.bot.interface.interface_termsofservice_command import register_termsofservice_command

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot online as {bot.user}")
    try:
        register_setup_command(bot.tree)
        register_setcountry_command(bot.tree)
        register_termsofservice_command(bot.tree)
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print("Sync failed:", e)

if __name__ == "__main__":
    load_dotenv()
    TOKEN = os.getenv("EVOLADDERBOT_TOKEN")
    bot.run(TOKEN)