import discord
from discord import app_commands
from src.bot.utils.discord_utils import send_ephemeral_response
from src.bot.interface.components.confirm_embed import ConfirmEmbedView
from src.bot.interface.components.confirm_restart_cancel_buttons import (
    ConfirmButton,
    CancelButton,
)
from src.bot.interface.components.command_guard_embeds import (
    create_command_guard_error_embed,
)
from src.backend.services.command_guard_service import CommandGuardError
from src.bot.config import GLOBAL_TIMEOUT


def register_termsofservice_command(tree: app_commands.CommandTree):
    @tree.command(
        name="termsofservice", description="View and accept the Terms of Service"
    )
    async def termsofservice(interaction: discord.Interaction):
        command_guard_service = interaction.client.app_context.command_guard_service
        user_info_service = interaction.client.app_context.user_info_service

        try:
            player = command_guard_service.ensure_player_record(
                interaction.user.id, interaction.user.name
            )
        except CommandGuardError as e:
            await send_ephemeral_response(
                interaction, embed=create_command_guard_error_embed(e)
            )
            return

        if player.get("accepted_tos"):
            embed = discord.Embed(
                title="✅ Terms of Service Already Accepted",
                description="You have already accepted the Terms of Service. You can proceed with `/setup`.",
                color=discord.Color.green(),
            )
            await send_ephemeral_response(interaction, embed=embed)
            return

        async def confirm_callback(interaction: discord.Interaction):
            await interaction.response.defer()
            success = user_info_service.accept_terms_of_service(interaction.user.id)
            if success:
                post_confirm_view = ConfirmEmbedView(
                    title="✅ Terms of Service Accepted",
                    description="You can now proceed with `/setup`.",
                    fields=[],
                    mode="post_confirmation",
                )
                await interaction.edit_original_response(
                    embed=post_confirm_view.embed, view=post_confirm_view
                )
            else:
                error_embed = discord.Embed(
                    title="❌ Error",
                    description="An error occurred while accepting the Terms of Service. Please try again.",
                    color=discord.Color.red(),
                )
                await interaction.edit_original_response(embed=error_embed, view=None)

        tos_text = (
            "**Welcome to the EvoLadder Alpha!**\n\n"
            "This is an alpha test for a new StarCraft matchmaking service. By participating, you agree to the following:\n\n"
            "1. **Alpha Status**: The service is in active development. Expect bugs, downtime, and data resets.\n"
            "2. **Data Collection**: We collect match data, replays, and Discord user information for development and analysis.\n"
            "3. **Code of Conduct**: Be respectful. Harassment, cheating, or exploiting bugs will result in a ban.\n"
            "4. **No Guarantees**: The service is provided 'as-is' without any warranties.\n\n"
            "Please confirm to proceed."
        )

        class TosConfirmView(discord.ui.View):
            def __init__(self) -> None:
                super().__init__(timeout=GLOBAL_TIMEOUT)
                self.add_item(ConfirmButton(confirm_callback, "Accept"))
                self.add_item(CancelButton(None, "Decline"))

        embed = discord.Embed(
            title="📜 Terms of Service",
            description=tos_text,
            color=discord.Color.blue(),
        )
        await send_ephemeral_response(interaction, embed=embed, view=TosConfirmView())

    return termsofservice
