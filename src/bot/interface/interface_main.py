import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

from src.bot.interface.commands.activate_command import register_activate_command
from src.bot.interface.commands.leaderboard_command import register_leaderboard_command
from src.bot.interface.commands.profile_command import register_profile_command
from src.bot.interface.commands.queue_command import register_queue_command, on_message as handle_replay_message
from src.bot.interface.commands.setcountry_command import register_setcountry_command
from src.bot.interface.commands.setup_command import register_setup_command
from src.bot.interface.commands.termsofservice_command import register_termsofservice_command
from src.backend.services.matchmaking_service import matchmaker
from src.backend.db.db_reader_writer import DatabaseWriter


intents = discord.Intents.default()
intents.messages = True
intents.message_content = True


class EvoLadderBot(commands.Bot):
    async def on_interaction(self, interaction: discord.Interaction):
        """A global listener for all interactions to log command calls."""
        if interaction.type == discord.InteractionType.application_command:
            command_name = interaction.command.name if interaction.command else "unknown"
            user = interaction.user
            # We instantiate the writer here to ensure it's fresh for each event
            db_writer = DatabaseWriter()
            db_writer.insert_command_call(
                discord_uid=user.id,
                player_name=user.name,
                command=command_name
            )
        
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
    except Exception as e:
        print("Sync failed:", e)

@bot.event
async def on_message(message):
    """Handle replay file detection for active match views."""
    await handle_replay_message(message)

def register_commands(bot: commands.Bot):
    register_activate_command(bot.tree)
    register_leaderboard_command(bot.tree)
    register_profile_command(bot.tree)
    register_queue_command(bot.tree)
    register_setcountry_command(bot.tree)
    register_setup_command(bot.tree)
    register_termsofservice_command(bot.tree)

if __name__ == "__main__":
    TOKEN = os.getenv("EVOLADDERBOT_TOKEN")
    bot.run(TOKEN)