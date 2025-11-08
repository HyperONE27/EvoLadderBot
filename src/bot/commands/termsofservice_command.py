import discord
from discord import app_commands
from src.backend.services.command_guard_service import CommandGuardError
from src.backend.services.user_info_service import get_user_info, log_user_action
from src.backend.services.app_context import (
    user_info_service,
    command_guard_service as guard_service
)
from src.bot.utils.discord_utils import send_ephemeral_response
from src.bot.components.confirm_embed import ConfirmEmbedView
from src.bot.components.command_guard_embeds import create_command_guard_error_embed
from src.bot.components.confirm_restart_cancel_buttons import ConfirmRestartCancelButtons
from src.bot.utils.command_decorators import dm_only
from src.bot.config import GLOBAL_TIMEOUT
from src.backend.services.performance_service import FlowTracker
from src.bot.utils.message_helpers import queue_interaction_edit

BOT_ICON_URL = "https://images-ext-1.discordapp.net/external/RB5N__Tb9izV-SQ8txIoeiV15DEqIH75_VX77O1slIE/%3Fsize%3D4096/https/cdn.discordapp.com/avatars/1415538525742301216/70e6f0051edfe42da3b4db67122fe727.png"

# API Call / Data Handling
@dm_only
async def termsofservice_command(interaction: discord.Interaction):
    """Show the terms of service"""
    try:
        guard_service.ensure_player_record(interaction.user.id, interaction.user.name)
    except CommandGuardError as exc:
        error_embed, error_view = create_command_guard_error_embed(exc)
        await send_ephemeral_response(interaction, embed=error_embed, view=error_view)
        return

    user_info = get_user_info(interaction)

    # Create the Terms of Service embed
    embed = discord.Embed(
        title="📋 Terms of Service, User Conduct, Privacy Policy, Refund Policy",
        description=(
            "Please read our Terms of Service, User Conduct guidelines, Privacy Policy, and Refund Policy. **You must accept these terms in order to use the SC: Evo Complete Ladder Bot.**\n\n"
            "**Official Terms of Service:**\n"
            "🔗 [SC: Evo Ladder ToS](https://www.scevo.net/ladder/tos)\n"
            "🔗 [EvoLadderBot ToS (Mirror)](https://rentry.co/evoladderbot-tos)\n\n"
            "By clicking **✅ I Accept These Terms** below, you confirm that you have read and agree to abide by the Terms of Service. "
            "You can withdraw your agreement to these terms at any time by using this command again and clicking **❌ I Decline These Terms** below.\n\n"
            "**⚠️ Failure to read or understand these terms is NOT AN ACCEPTABLE DEFENSE for violating them, and may result in your removal from the Service.**"
        ),
        color=discord.Color.blue()
    )

    # Add footer
    embed.set_footer(
        text="EvoLadderBot • SC: Evo Complete Ladder Bot",
        icon_url=BOT_ICON_URL
    )


    # Log the action
    log_user_action(user_info, "viewed terms of service")

    # Create custom view with only confirm and cancel buttons (no restart)
    class TOSConfirmView(discord.ui.View):
        def __init__(self) -> None:
            super().__init__(timeout=GLOBAL_TIMEOUT)

        @discord.ui.button(label="I Accept These Terms", emoji="✅", style=discord.ButtonStyle.success)
        async def accept_terms(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Update in backend that user has confirmed the terms of service
            success = await user_info_service.accept_terms_of_service(user_info["id"])

            if not success:
                error_embed = discord.Embed(
                    title="❌ Error",
                    description="An error occurred while confirming your acceptance. Please try again.",
                    color=discord.Color.red()
                )
                await queue_interaction_edit(interaction, embed=error_embed, view=None)
                return

            # Log the confirmation
            log_user_action(user_info, "confirmed terms of service")

            # Create post-confirmation embed
            confirm_embed = discord.Embed(
                title="✅ Terms of Service Confirmed",
                description="Thank you for agreeing to the Terms of Service.",
                color=discord.Color.green()
            )
            confirm_embed.set_footer(
                text="You may now use all SC: Evo Complete Ladder Bot features.",
                icon_url=BOT_ICON_URL
            )
            
            # Create view with Close button
            class ConfirmView(discord.ui.View):
                pass
            
            confirm_view = ConfirmView(timeout=GLOBAL_TIMEOUT)
            close_buttons = ConfirmRestartCancelButtons.create_buttons(
                reset_target=confirm_view,
                include_confirm=False,
                include_restart=False,
                include_cancel=True,
                cancel_label="Close"
            )
            for button in close_buttons:
                confirm_view.add_item(button)
            
            await queue_interaction_edit(interaction, embed=confirm_embed, view=confirm_view)

        @discord.ui.button(label="I Decline These Terms", emoji="✖️", style=discord.ButtonStyle.danger)
        async def decline_terms(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Update in backend that user has declined the terms of service
            success = await user_info_service.decline_terms_of_service(user_info["id"])

            if not success:
                error_embed = discord.Embed(
                    title="❌ Error",
                    description="An error occurred while recording your decision. Please try again.",
                    color=discord.Color.red()
                )
                await queue_interaction_edit(interaction, embed=error_embed, view=None)
                return

            # Log the decline
            log_user_action(user_info, "declined terms of service")

            # Create custom decline embed
            decline_embed = discord.Embed(
                title="❌ Terms of Service Declined",
                description="Since you have declined the Terms of Service, you may not the SC: Evo Complete Ladder Bot.",
                color=discord.Color.red()
            )
            decline_embed.set_footer(
                text="You may use /termsofservice to review the terms again if you change your mind.",
                icon_url=BOT_ICON_URL
            )
            
            # Create view with Close button
            class DeclineView(discord.ui.View):
                pass
            
            decline_view = DeclineView(timeout=GLOBAL_TIMEOUT)
            close_buttons = ConfirmRestartCancelButtons.create_buttons(
                reset_target=decline_view,
                include_confirm=False,
                include_restart=False,
                include_cancel=True,
                cancel_label="Close"
            )
            for button in close_buttons:
                decline_view.add_item(button)

            await queue_interaction_edit(interaction, embed=decline_embed, view=decline_view)

    confirm_view = TOSConfirmView()

    # Send the full terms of service first
    await send_ephemeral_response(
        interaction,
        embed=embed,
        view=confirm_view
    )


# Register Command
def register_termsofservice_command(tree: app_commands.CommandTree):
    """Register the termsofservice command.

    Args:
        tree: The app command tree to register the command to.

    Returns:
        The registered command.
    """
    @tree.command(
        name="termsofservice",
        description="Show the terms of service"
    )
    async def termsofservice(interaction: discord.Interaction):
        await termsofservice_command(interaction)

    return termsofservice