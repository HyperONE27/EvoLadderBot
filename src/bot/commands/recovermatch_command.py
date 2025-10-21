"""
Recover Match command for EvoLadderBot.

Allows players to recover their active match if the match view was lost
due to bot restart, interaction expiry, or other issues.
"""

import discord
from discord import app_commands

from src.backend.db.db_reader_writer import DatabaseReader
from src.bot.utils.discord_utils import send_ephemeral_response
from src.bot.commands.queue_command import MatchFoundView, match_found_view_manager
from src.backend.services.matchmaking_service import matchmaker, MatchResult


def register_recovermatch_command(tree: app_commands.CommandTree):
    """Register the recovermatch command"""
    @tree.command(
        name="recovermatch",
        description="Recover your active match if the match view was lost"
    )
    async def recovermatch(interaction: discord.Interaction):
        await recovermatch_command(interaction)
    
    return recovermatch


async def recovermatch_command(interaction: discord.Interaction):
    """
    Recover an active match for a player.
    
    Searches for any active matches for the player and re-displays the match view.
    """
    db_reader = DatabaseReader()
    discord_uid = interaction.user.id
    
    # Defer response since we'll be querying the database
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Query for active matches for this player
        # Active match = match_result is NULL or empty
        query = """
            SELECT 
                match_id,
                player_1_discord_id,
                player_2_discord_id,
                player_1_user_id,
                player_2_user_id,
                player_1_race,
                player_2_race,
                map_choice,
                server_choice,
                in_game_channel,
                match_result,
                match_result_confirmation_status,
                replay_uploaded,
                replay_upload_time,
                unix_epoch
            FROM matches
            WHERE (player_1_discord_id = $1 OR player_2_discord_id = $1)
              AND (match_result IS NULL OR match_result = '')
              AND unix_epoch > EXTRACT(EPOCH FROM NOW() - INTERVAL '24 hours')
            ORDER BY unix_epoch DESC
            LIMIT 1
        """
        
        result = await db_reader.fetch_one(query, discord_uid)
        
        if not result:
            # No active match found
            embed = discord.Embed(
                title="No Active Match",
                description="You don't have any active matches to recover.",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Found an active match - reconstruct the MatchResult
        is_player1 = result['player_1_discord_id'] == discord_uid
        
        match_result = MatchResult(
            match_id=result['match_id'],
            player_1_discord_id=result['player_1_discord_id'],
            player_2_discord_id=result['player_2_discord_id'],
            player_1_user_id=result['player_1_user_id'],
            player_2_user_id=result['player_2_user_id'],
            player_1_race=result['player_1_race'],
            player_2_race=result['player_2_race'],
            map_choice=result['map_choice'],
            server_choice=result['server_choice'],
            in_game_channel=result['in_game_channel'],
            match_result=result['match_result'],
            match_result_confirmation_status=result['match_result_confirmation_status'],
            replay_uploaded=result['replay_uploaded'] or "No",
            replay_upload_time=result['replay_upload_time']
        )
        
        # Create and register the match found view
        match_view = MatchFoundView(match_result, is_player1)
        
        # Register for replay detection
        if interaction.channel_id:
            await match_view.register_for_replay_detection(interaction.channel_id)
        
        # Store interaction for updates
        match_view.last_interaction = interaction
        
        # Send the match view
        await interaction.followup.send(
            embed=match_view.get_embed(),
            view=match_view,
            ephemeral=False  # Make it public so replays can be uploaded to it
        )
        
        print(f"[Recover Match] Player {discord_uid} recovered match {result['match_id']}")
        
    except Exception as e:
        print(f"[Recover Match] Error recovering match for player {discord_uid}: {e}")
        import traceback
        traceback.print_exc()
        
        embed = discord.Embed(
            title="Error",
            description="An error occurred while recovering your match. Please contact an administrator.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
