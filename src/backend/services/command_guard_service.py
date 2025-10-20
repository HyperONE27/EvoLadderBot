"""Command guard service centralizing pre-checks for slash commands."""

from __future__ import annotations

from typing import Any, Dict

from src.backend.services.user_info_service import UserInfoService


class CommandGuardError(Exception):
    """Base exception for command guard failures."""


class AccountNotActivatedError(CommandGuardError):
    """Raised when a user needs activation before proceeding."""


class TermsNotAcceptedError(CommandGuardError):
    """Raised when terms of service were not accepted."""


class SetupIncompleteError(CommandGuardError):
    """Raised when setup is incomplete."""


class CommandGuardService:
    """Centralized helper to perform pre-command checks for slash handlers."""

    def __init__(self, user_service: UserInfoService) -> None:
        self.user_service = user_service

    def ensure_player_record(
        self, discord_user_id: int, discord_username: str
    ) -> Dict[str, Any]:
        """Ensure the player exists and return the record."""
        return self.user_service.ensure_player_exists(discord_user_id, discord_username)

    def require_player_exists(
        self, discord_user_id: int, discord_username: str
    ) -> Dict[str, Any]:
        """Alias kept for readability; returns the player record."""
        return self.ensure_player_record(discord_user_id, discord_username)

    def require_tos_accepted(self, player: Dict[str, Any]) -> None:
        if not player.get("accepted_tos"):
            raise TermsNotAcceptedError("Terms of service not accepted.")

    def require_setup_completed(self, player: Dict[str, Any]) -> None:
        if not player.get("completed_setup"):
            raise SetupIncompleteError("Profile setup not completed.")

    def require_account_activated(self, player: Dict[str, Any]) -> None:
        self.require_tos_accepted(player)
        self.require_setup_completed(player)
        if not player.get("activation_code"):
            raise AccountNotActivatedError("Account not activated.")

    def require_queue_access(self, player: Dict[str, Any]) -> None:
        """Require TOS acceptance, setup completion, and activation for queue access."""
        self.require_tos_accepted(player)
        self.require_setup_completed(player)
        if not player.get("activation_code"):
            raise AccountNotActivatedError("Account not activated.")
