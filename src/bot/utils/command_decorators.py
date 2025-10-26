"""
Command decorators for centralized command guards and checks.

This module provides decorators and wrappers to enforce command requirements
like DM-only enforcement before the command handler runs.
"""

from functools import wraps
from typing import Callable, Set
import discord

from src.backend.services.app_context import command_guard_service
from src.backend.services.command_guard_service import CommandGuardError
from src.bot.components.command_guard_embeds import create_command_guard_error_embed
from src.bot.utils.discord_utils import send_ephemeral_response


# Centralized list of DM-only commands
DM_ONLY_COMMANDS: Set[str] = {
    "prune",  # Personal message cleanup
    "queue",  # Matchmaking (security + ephemeral messages work in DMs)
    "help",  # Help command
    "leaderboard",  # View leaderboard
    "profile",  # View player profile
    "setup",  # User setup
    "setcountry",  # Set country
    "termsofservice",  # Terms of service
    "activate"  # Account activation
}


def dm_only(func: Callable) -> Callable:
    """
    Decorator to enforce DM-only requirement for a command.
    
    Usage:
        @dm_only
        async def my_command(interaction: discord.Interaction):
            ...
    """
    @wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        try:
            command_guard_service.require_dm(interaction)
        except CommandGuardError as exc:
            error_embed = create_command_guard_error_embed(exc)
            await send_ephemeral_response(interaction, embed=error_embed)
            return
        
        return await func(interaction, *args, **kwargs)
    
    return wrapper


def auto_apply_dm_guard(command_name: str, func: Callable) -> Callable:
    """
    Automatically apply DM guard if command is in DM_ONLY_COMMANDS list.
    
    This allows centralized management of which commands are DM-only without
    manually decorating each command.
    
    Usage:
        command_func = auto_apply_dm_guard("queue", queue_command)
    """
    if command_name in DM_ONLY_COMMANDS:
        return dm_only(func)
    return func

