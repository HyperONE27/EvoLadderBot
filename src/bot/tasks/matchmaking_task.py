"""Background task for processing matchmaking queue."""
import asyncio
import discord
from discord.ext import tasks, commands
from datetime import datetime
from typing import TYPE_CHECKING
from src.backend.db import get_db_session
from src.backend.services import MatchmakingService, RegionMappingService
from src.backend.db.models import Race

if TYPE_CHECKING:
    from discord.ext.commands import Bot


class MatchmakingTask(commands.Cog):
    """Background task that processes the matchmaking queue."""
    
    def __init__(self, bot: 'Bot'):
        self.bot = bot
        self.region_service = RegionMappingService()
        self.process_queue.start()
    
    def cog_unload(self):
        """Clean up when cog is unloaded."""
        self.process_queue.cancel()
    
    @tasks.loop(seconds=10)
    async def process_queue(self):
        """Process matchmaking queue every 10 seconds."""
        try:
            async with get_db_session() as db_session:
                # Find all possible matches
                matches = await MatchmakingService.find_matches(db_session)
                
                # Process each match
                for entry1, entry2, match_info in matches:
                    try:
                        # Create the match
                        match = await MatchmakingService.create_match(
                            db_session,
                            entry1,
                            entry2,
                            match_info
                        )
                        
                        # Notify both players
                        await self._notify_match_found(
                            entry1,
                            entry2,
                            match,
                            match_info
                        )
                        
                    except Exception as e:
                        print(f"Error creating match: {e}")
                        
        except Exception as e:
            print(f"Error in matchmaking task: {e}")
    
    @process_queue.before_loop
    async def before_process_queue(self):
        """Wait until bot is ready before starting task."""
        await self.bot.wait_until_ready()
    
    async def _notify_match_found(self, entry1, entry2, match, match_info):
        """Notify both players that a match has been found."""
        # Get both users
        user1 = self.bot.get_user(entry1.discord_id)
        user2 = self.bot.get_user(entry2.discord_id)
        
        if not user1 or not user2:
            print(f"Could not find Discord users for match {match.id}")
            return
        
        # Get server name
        server_name = self.region_service.get_server_name(match.server_region)
        
        # Get race names
        race1_name = match_info["player1_race"].value.replace("_", " ").title()
        race2_name = match_info["player2_race"].value.replace("_", " ").title()
        
        # Create match found embed
        def create_match_embed(for_player1: bool) -> discord.Embed:
            if for_player1:
                your_race = race1_name
                your_mmr = int(match_info["player1_mmr"])
                opp_name = entry2.user.main_id
                opp_race = race2_name
                opp_mmr = int(match_info["player2_mmr"])
            else:
                your_race = race2_name
                your_mmr = int(match_info["player2_mmr"])
                opp_name = entry1.user.main_id
                opp_race = race1_name
                opp_mmr = int(match_info["player1_mmr"])
            
            embed = discord.Embed(
                title="⚔️ Match Found!",
                description="A ranked match has been found for you.",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            # Match details
            embed.add_field(
                name="Your Race",
                value=f"{your_race} ({your_mmr} MMR)",
                inline=True
            )
            
            embed.add_field(
                name="Opponent",
                value=f"{opp_name}\n{opp_race} ({opp_mmr} MMR)",
                inline=True
            )
            
            embed.add_field(
                name="Map",
                value=match.map_name,
                inline=True
            )
            
            embed.add_field(
                name="Server",
                value=server_name,
                inline=True
            )
            
            embed.add_field(
                name="Channel",
                value=f"`{match.channel_name}`",
                inline=True
            )
            
            embed.add_field(
                name="Match ID",
                value=f"#{match.id}",
                inline=True
            )
            
            # Instructions
            embed.add_field(
                name="📋 Instructions",
                value=(
                    f"1. Join channel `{match.channel_name}` in-game\n"
                    f"2. Create/join a lobby on **{server_name}** server\n"
                    f"3. Play on map **{match.map_name}**\n"
                    "4. Report the result after the match"
                ),
                inline=False
            )
            
            embed.set_footer(text="Good luck, have fun!")
            
            return embed
        
        # Send notifications to both players
        try:
            await user1.send(embed=create_match_embed(for_player1=True))
        except discord.Forbidden:
            print(f"Could not DM user {user1.id} - DMs may be disabled")
        
        try:
            await user2.send(embed=create_match_embed(for_player1=False))
        except discord.Forbidden:
            print(f"Could not DM user {user2.id} - DMs may be disabled")


def setup(bot: 'Bot'):
    """Set up the matchmaking cog."""
    bot.add_cog(MatchmakingTask(bot))
