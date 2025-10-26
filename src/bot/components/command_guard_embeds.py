"""
Embeds for command guard errors.
"""
import discord
from src.backend.services.command_guard_service import (
    CommandGuardError,
    TermsNotAcceptedError,
    SetupIncompleteError,
    AccountNotActivatedError,
    DMOnlyError
)

def create_command_guard_error_embed(error: CommandGuardError) -> discord.Embed:
    """Create a red error embed with X emote for command guard errors."""
    if isinstance(error, TermsNotAcceptedError):
        return discord.Embed(
            title="❌ Terms of Service Required",
            description="You must accept the Terms of Service before using this command.\n\n"
                        "Use `/termsofservice` to review and accept the terms.",
            color=discord.Color.red()
        )
    elif isinstance(error, SetupIncompleteError):
        return discord.Embed(
            title="❌ Profile Setup Required",
            description="You must complete your profile setup before using this command.\n\n"
                        "Use `/setup` to complete your profile.",
            color=discord.Color.red()
        )
    elif isinstance(error, AccountNotActivatedError):
        return discord.Embed(
            title="❌ Account Not Activated",
            description="Your account must be activated before using this command.\n\n"
                        "Use /activation to activate your account.",
            color=discord.Color.red()
        )
    elif isinstance(error, DMOnlyError):
        return discord.Embed(
            title="❌ DM Only Command",
            description="This bot's commands can only be used in DMs (private messages).\n\n"
                        "Please send me a DM and try the command again.",
            color=discord.Color.red()
        )
    else:
        # Generic error embed
        return discord.Embed(
            title="❌ Command Error",
            description=str(error),
            color=discord.Color.red()
        )
