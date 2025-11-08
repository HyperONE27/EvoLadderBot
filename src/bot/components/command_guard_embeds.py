"""
Embeds for command guard errors.
"""
import discord
from src.backend.services.command_guard_service import (
    CommandGuardError,
    TermsNotAcceptedError,
    SetupIncompleteError,
    AccountNotActivatedError,
    DMOnlyError,
    BannedError
)
from src.bot.components.confirm_restart_cancel_buttons import ConfirmRestartCancelButtons
from src.bot.config import GLOBAL_TIMEOUT

def create_command_guard_error_embed(error: CommandGuardError) -> tuple[discord.Embed, discord.ui.View]:
    """Create a red error embed with X emote and Close button for command guard errors."""
    # Determine the embed based on error type
    if isinstance(error, TermsNotAcceptedError):
        embed = discord.Embed(
            title="❌ Terms of Service Required",
            description="You must accept the Terms of Service before using this command.\n\n"
                        "Use `/termsofservice` to review and accept the terms.",
            color=discord.Color.red()
        )
    elif isinstance(error, SetupIncompleteError):
        embed = discord.Embed(
            title="❌ Profile Setup Required",
            description="You must complete your profile setup before using this command.\n\n"
                        "Use `/setup` to complete your profile.",
            color=discord.Color.red()
        )
    elif isinstance(error, AccountNotActivatedError):
        embed = discord.Embed(
            title="❌ Account Not Activated",
            description="Your account must be activated before using this command.\n\n"
                        "Use /activation to activate your account.",
            color=discord.Color.red()
        )
    elif isinstance(error, DMOnlyError):
        embed = discord.Embed(
            title="❌ DM Only Command",
            description="This bot's commands can only be used in DMs (private messages).\n\n"
                        "Please send me a DM and try the command again.",
            color=discord.Color.red()
        )
    elif isinstance(error, BannedError):
        from src.bot.components.banned_embed import create_banned_embed
        return create_banned_embed()
    else:
        # Generic error embed
        embed = discord.Embed(
            title="❌ Command Error",
            description=str(error),
            color=discord.Color.red()
        )
    
    # Create view with Close button
    class ErrorView(discord.ui.View):
        pass
    
    view = ErrorView(timeout=GLOBAL_TIMEOUT)
    close_buttons = ConfirmRestartCancelButtons.create_buttons(
        reset_target=view,
        include_confirm=False,
        include_restart=False,
        include_cancel=True,
        cancel_label="Close"
    )
    for button in close_buttons:
        view.add_item(button)
    
    return embed, view
