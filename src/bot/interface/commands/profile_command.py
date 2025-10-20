import discord
from discord import app_commands
from src.bot.utils.discord_utils import send_ephemeral_response
from src.bot.interface.components.command_guard_embeds import (
    create_command_guard_error_embed,
)
from src.backend.services.command_guard_service import CommandGuardError


def register_profile_command(tree: app_commands.CommandTree):
    @tree.command(name="profile", description="View your player profile")
    async def profile(interaction: discord.Interaction):
        command_guard_service = interaction.client.app_context.command_guard_service
        user_info_service = interaction.client.app_context.user_info_service
        mmr_service = interaction.client.app_context.mmr_service

        try:
            player = command_guard_service.ensure_player_record(
                interaction.user.id, interaction.user.name
            )
            command_guard_service.require_tos_accepted(player)
            command_guard_service.require_setup_completed(player)
        except CommandGuardError as e:
            await send_ephemeral_response(
                interaction, embed=create_command_guard_error_embed(e)
            )
            return

        embed = discord.Embed(
            title=f"📋 Player Profile: {player.get('player_name', interaction.user.name)}",
            color=discord.Color.blue(),
        )

        # Player Info
        embed.add_field(
            name="📜 Player Info",
            value=f"**In-Game Name:** `{player.get('player_name', 'N/A')}`\n"
            f"**BattleTag:** `{player.get('battletag', 'N/A')}`\n"
            f"**Country:** `{player.get('country', 'N/A')}`\n"
            f"**Region:** `{player.get('region', 'N/A')}`",
            inline=False,
        )

        # MMR Info
        mmrs = mmr_service.get_all_player_mmrs_1v1(player["discord_uid"])
        if mmrs:
            mmr_text = ""
            for mmr_record in mmrs:
                mmr_text += f"**{mmr_record['race'].capitalize()}:** `{mmr_record['mmr']} MMR` ({mmr_record['games_won']}W - {mmr_record['games_lost']}L)\n"
            embed.add_field(name="🏆 MMR Details", value=mmr_text, inline=False)
        else:
            embed.add_field(
                name="🏆 MMR Details",
                value="No MMR data available. Play a game!",
                inline=False,
            )

        await send_ephemeral_response(interaction, embed=embed)
