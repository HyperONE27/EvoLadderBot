import asyncio
import logging

import discord
from discord.ext import commands

from src.backend.services.matchmaking_service import matchmaker
from src.bot.bot_setup import EvoLadderBot, initialize_bot_resources, shutdown_bot_resources
# from src.bot.commands.activate_command import register_activate_command  # DISABLED: Obsolete command
from src.bot.commands.help_command import register_help_command
from src.bot.commands.leaderboard_command import register_leaderboard_command
from src.bot.commands.profile_command import register_profile_command
from src.bot.commands.prune_command import register_prune_command
from src.bot.commands.queue_command import on_message as handle_replay_message, register_queue_command
from src.bot.commands.recovermatch_command import register_recovermatch_command
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
        
        # Recover orphaned matches on startup
        await recover_orphaned_matches(bot)
        
    except Exception as e:
        print("Sync failed:", e)


async def recover_orphaned_matches(bot: commands.Bot):
    """
    On bot startup, check for active matches and send recovery notifications.
    
    This helps recover matches that were active when the bot restarted.
    """
    try:
        from src.backend.db.db_reader_writer import DatabaseReader
        
        db_reader = DatabaseReader()
        
        # Find all active matches from the last 24 hours
        query = """
            SELECT 
                match_id,
                player_1_discord_id,
                player_2_discord_id,
                player_1_user_id,
                player_2_user_id
            FROM matches
            WHERE (match_result IS NULL OR match_result = '')
              AND unix_epoch > EXTRACT(EPOCH FROM NOW() - INTERVAL '24 hours')
            ORDER BY unix_epoch DESC
        """
        
        results = await db_reader.fetch_all(query)
        
        if not results:
            print("[Match Recovery] No orphaned matches found")
            return
        
        print(f"[Match Recovery] Found {len(results)} active matches to recover")
        
        # For each match, try to send a recovery notification to both players
        for match in results:
            match_id = match['match_id']
            p1_discord_id = match['player_1_discord_id']
            p2_discord_id = match['player_2_discord_id']
            
            print(f"[Match Recovery] Match {match_id}: Notifying players to use /recovermatch")
            
            # Send DM to both players
            for discord_id in [p1_discord_id, p2_discord_id]:
                try:
                    user = await bot.fetch_user(discord_id)
                    if user:
                        embed = discord.Embed(
                            title="⚠️ Active Match Detected",
                            description=(
                                f"You have an active match (ID: {match_id}) that needs to be completed.\n\n"
                                f"Use `/recovermatch` to restore your match view and continue playing."
                            ),
                            color=discord.Color.orange()
                        )
                        await user.send(embed=embed)
                        print(f"[Match Recovery] Sent recovery notification to player {discord_id}")
                except discord.Forbidden:
                    print(f"[Match Recovery] Cannot send DM to player {discord_id} (DMs disabled)")
                except Exception as e:
                    print(f"[Match Recovery] Error sending DM to player {discord_id}: {e}")
        
        print(f"[Match Recovery] Recovery notifications sent for {len(results)} matches")
        
    except Exception as e:
        print(f"[Match Recovery] Error during match recovery: {e}")
        import traceback
        traceback.print_exc()

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
    register_recovermatch_command(bot.tree)
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