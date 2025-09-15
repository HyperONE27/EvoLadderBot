import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
# from src.bot.interface.interface_commands import register_commands
from src.bot.interface.interface_setup import register_setup_command

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot online as {bot.user}")
    try:
        print("Registering setup command...")
        register_setup_command(bot.tree)  # Pass bot.tree instead of bot
        print("Setup command registered successfully")
        print("Syncing commands with Discord...")
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
        for cmd in synced:
            print(f"  - {cmd.name}: {cmd.description}")
    except Exception as e:
        print("Sync failed:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    load_dotenv()
    TOKEN = os.getenv("EVOLADDERBOT_TOKEN")
    bot.run(TOKEN)