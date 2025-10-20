import discord
from discord import app_commands
from src.bot.utils.discord_utils import send_ephemeral_response
from src.bot.interface.components.command_guard_embeds import (
    create_command_guard_error_embed,
)
from src.backend.services.command_guard_service import CommandGuardError


def register_activate_command(tree: app_commands.CommandTree):
    @tree.command(name="activate", description="Activate your account with a code")
    @app_commands.describe(code="The activation code")
    async def activate(interaction: discord.Interaction, code: str):
        command_guard_service = interaction.client.app_context.command_guard_service
        user_info_service = interaction.client.app_context.user_info_service

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

        # For now, any code is valid during alpha
        # In the future, this would check against a list of valid codes
        is_valid_code = True

        if is_valid_code:
            user_info_service.submit_activation_code(interaction.user.id, code)
            embed = discord.Embed(
                title="✅ Account Activated!",
                description="Your account has been successfully activated. You can now join the queue using `/queue`.",
                color=discord.Color.green(),
            )
            await send_ephemeral_response(interaction, embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Invalid Code",
                description="The activation code you entered is not valid. Please check the code and try again.",
                color=discord.Color.red(),
            )
            await send_ephemeral_response(interaction, embed=embed)
