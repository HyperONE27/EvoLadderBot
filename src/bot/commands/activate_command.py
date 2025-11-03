# DISABLED: This command is obsolete and has been disabled
# The activation system is no longer used in the application

import asyncio
import discord
from discord import app_commands
from src.bot.components.confirm_embed import ConfirmEmbedView
from src.bot.components.error_embed import ErrorEmbedException, create_simple_error_view
from src.backend.services.command_guard_service import CommandGuardError
from src.backend.services.app_context import (
    user_info_service,
    command_guard_service as guard_service
)
from src.bot.utils.discord_utils import send_ephemeral_response
from src.bot.components.command_guard_embeds import create_command_guard_error_embed
from src.bot.utils.command_decorators import dm_only
from src.bot.config import GLOBAL_TIMEOUT
from src.backend.services.performance_service import FlowTracker
from src.bot.utils.message_helpers import queue_interaction_modal


# API Call / Data Handling
def submit_activation_code(user_id: int, code: str) -> dict:
    """
    Submit activation code to backend.
    
    Args:
        user_id: Discord user ID.
        code: Activation code.
    
    Returns:
        Dictionary with status and code.
    """
    print(f"[TERMINAL] Activation attempt by {user_id} with code: {code}")
    
    # Example validation that could trigger an error
    if len(code) < 3:
        raise ErrorEmbedException(
            title="Invalid Activation Code",
            description="The activation code you provided is too short.",
            error_fields=[
                ("Provided Code", code),
                ("Minimum Length", "3 characters"),
                ("Your Code Length", f"{len(code)} characters")
            ]
        )
    
    # Submit to backend
    # Use shared service instance
    result = user_info_service.submit_activation_code(user_id, code)
    
    if result["status"] == "error":
        raise ErrorEmbedException(
            title="Activation Failed",
            description=result["message"],
            error_fields=[
                ("Error Code", "ACTIVATION_ERROR"),
                ("Suggestion", "Please check your code and try again")
            ]
        )
    
    return {"status": "ok", "code": code}


# Register Command - DISABLED
def register_activate_command(tree: app_commands.CommandTree):
    """DISABLED: This command is obsolete and should not be registered."""
    return  # Early return to disable the command
    @tree.command(
        name="activate",
        description="Enter your activation code for ladder access"
    )
    @dm_only
    async def activate(interaction: discord.Interaction):
        print(f"[TERMINAL] /activate started by {interaction.user.id}")
        try:
            player = guard_service.ensure_player_record(interaction.user.id, interaction.user.name)
            guard_service.require_tos_accepted(player)
        except CommandGuardError as exc:
            error_embed = create_command_guard_error_embed(exc)
            await send_ephemeral_response(interaction, embed=error_embed)
            return
        
        await queue_interaction_modal(interaction, ActivateModal())


# UI Elements
class ActivateModal(discord.ui.Modal, title="Enter Activation Code"):
    code_input = discord.ui.TextInput(
        label="Activation Code",
        placeholder="Paste your code here",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            result = submit_activation_code(interaction.user.id, self.code_input.value)

            # Show preview with confirm/restart/cancel options
            async def confirm_callback(interaction: discord.Interaction):
                # Process the activation
                # TODO: Add actual backend processing here
                
                # Show post-confirmation view
                post_confirm_view = ConfirmEmbedView(
                    title="Activation Complete",
                    description="Your activation code has been processed successfully.",
                    fields=[("Entered Code", result["code"])],
                    mode="post_confirmation",
                    reset_target=ActivateModal(),
                    restart_label="🔄 Activate Another"
                )
                await send_ephemeral_response(interaction, embed=post_confirm_view.embed, view=post_confirm_view)

            confirm_view = ConfirmEmbedView(
                title="Preview Activation",
                description="Please review your activation code before confirming:",
                fields=[("Entered Code", result["code"])],
                mode="preview",
                confirm_callback=confirm_callback,
                reset_target=ActivateModal()
            )
            await send_ephemeral_response(interaction, embed=confirm_view.embed, view=confirm_view)
            
        except ErrorEmbedException as e:
            # Handle custom error exceptions
            error_view = create_simple_error_view(
                title=e.title,
                description=e.description,
                error_fields=e.error_fields,
                reset_target=ActivateModal()
            )
            await send_ephemeral_response(interaction, embed=error_view.embed, view=error_view)
            
        except CommandGuardError as e:
            error_embed = create_command_guard_error_embed(e)
            await send_ephemeral_response(interaction, embed=error_embed)
            return
            
        except Exception as e:
            # Handle unexpected errors
            error_view = create_simple_error_view(
                title="Unexpected Error",
                description="An unexpected error occurred while processing your activation code.",
                error_fields=[
                    ("Error Type", type(e).__name__),
                    ("Error Message", str(e)),
                    ("Suggestion", "Please try again or contact support if the issue persists")
                ],
                reset_target=ActivateModal()
            )
            await send_ephemeral_response(interaction, embed=error_view.embed, view=error_view)