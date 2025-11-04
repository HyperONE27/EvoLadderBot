"""Command guard service centralizing pre-checks for slash commands."""

from __future__ import annotations

from typing import Any, Dict
import discord

from src.backend.services.user_info_service import UserInfoService


class CommandGuardError(Exception):
    """Base exception for command guard failures."""


class AccountNotActivatedError(CommandGuardError):
    """Raised when a user needs activation before proceeding."""


class TermsNotAcceptedError(CommandGuardError):
    """Raised when terms of service were not accepted."""


class SetupIncompleteError(CommandGuardError):
    """Raised when setup is incomplete."""


class DMOnlyError(CommandGuardError):
    """Raised when a command is used outside of DMs."""


class BannedError(CommandGuardError):
    """Raised when a banned user attempts to use the bot."""


class CommandGuardService:
    """Centralized helper to perform pre-command checks for slash handlers."""

    def __init__(self, user_service: UserInfoService | None = None) -> None:
        self.user_service = user_service or UserInfoService()

    def ensure_player_record(self, discord_user_id: int, discord_username: str) -> Dict[str, Any]:
        """
        Ensure the player exists and return the record.
        
        Fetches directly from the in-memory DataAccessService via UserInfoService.
        """
        player_record = self.user_service.ensure_player_exists(discord_user_id, discord_username)
        self.require_not_banned(player_record)
        return player_record

    def require_player_exists(self, discord_user_id: int, discord_username: str) -> Dict[str, Any]:
        """Alias kept for readability; returns the player record."""
        return self.ensure_player_record(discord_user_id, discord_username)

    def require_tos_accepted(self, player: Dict[str, Any]) -> None:
        if not player.get("accepted_tos"):
            raise TermsNotAcceptedError("Terms of service not accepted.")

    def require_setup_completed(self, player: Dict[str, Any]) -> None:
        if not player.get("completed_setup"):
            raise SetupIncompleteError("Profile setup not completed.")
    
    def require_not_banned(self, player: Dict[str, Any]) -> None:
        """Check if player is banned. Raises BannedError if banned."""
        if player.get('is_banned', False):
            raise BannedError("Your account has been banned from using this bot.")

    def require_account_activated(self, player: Dict[str, Any]) -> None:
        """DISABLED: Activation requirement removed - command is obsolete."""
        self.require_tos_accepted(player)
        self.require_setup_completed(player)
        # Activation check disabled - command is obsolete
        # if not player.get("activation_code"):
        #     raise AccountNotActivatedError("Account not activated.")

    def require_queue_access(self, player: Dict[str, Any]) -> None:
        """Require TOS acceptance and setup completion for queue access."""
        self.require_tos_accepted(player)
        self.require_setup_completed(player)
        # Activation check disabled - command is obsolete
        # if not player.get("activation_code"):
        #     raise AccountNotActivatedError("Account not activated.")
    
    def require_dm(self, interaction: discord.Interaction) -> None:
        """Require that the command is used in a DM channel."""
        if not isinstance(interaction.channel, discord.DMChannel):
            raise DMOnlyError("This command can only be used in DMs.")