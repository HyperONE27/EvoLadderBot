"""
User info service.

This module defines the UserInfoService class, which handles user information management.
It contains methods for:
- Creating and updating user profiles
- Managing user settings (country, region, etc.)
- Handling activation codes
- Accepting terms of service
- Completing setup
- Utility functions for Discord user information
"""

from typing import Optional, Dict, Any
import discord
import asyncio
from src.backend.db.db_reader_writer import DatabaseReader, DatabaseWriter
from src.backend.services.data_access_service import DataAccessService
from src.backend.infrastructure.cache_service import player_cache


# ========== Utility Functions ==========

def get_user_info(interaction: discord.Interaction) -> Dict[str, Any]:
    """
    Extract user information from a Discord interaction.
    
    Args:
        interaction: Discord interaction object.
        
    Returns:
        Dictionary containing user information.
    """
    user = interaction.user
    return {
        'id': user.id,
        'username': user.name,
        'display_name': user.display_name or user.name,
        'mention': user.mention,
        'discriminator': user.discriminator if hasattr(user, 'discriminator') else None,
        'avatar_url': user.display_avatar.url if user.display_avatar else None
    }


def create_user_embed_field(user_info: Dict[str, Any], title: str = "User Information") -> Dict[str, Any]:
    """
    Create a Discord embed field for user information.
    
    Args:
        user_info: User information dictionary from get_user_info().
        title: Title for the embed field.
        
    Returns:
        Dictionary with name and value for Discord embed field.
    """
    user_text = f"**Username:** {user_info['display_name']}\n**Discord ID:** `{user_info['id']}`"
    
    if user_info['discriminator'] and user_info['discriminator'] != '0':
        user_text += f"\n**Tag:** {user_info['username']}#{user_info['discriminator']}"
    
    return {
        'name': title,
        'value': user_text,
        'inline': False
    }


def log_user_action(user_info: Dict[str, Any], action: str, details: str = "") -> None:
    """
    Log user action with consistent formatting.
    
    Args:
        user_info: User information dictionary from get_user_info().
        action: Description of the action performed.
        details: Additional details about the action.
    """
    log_message = f"User {user_info['display_name']} (ID: {user_info['id']}) {action}"
    if details:
        log_message += f" - {details}"
    print(log_message)


class UserInfoService:
    """
    Service for managing user information and settings.
    
    This service now delegates to DataAccessService for fast in-memory operations.
    Legacy DatabaseReader/Writer are kept for backwards compatibility only.
    """
    
    def __init__(self) -> None:
        self.data_service = None
        # Legacy - kept for backwards compatibility
        self.reader = DatabaseReader()
        self.writer = DatabaseWriter()  # Still needed for operations not yet in DataAccessService
    
    async def _ensure_data_service(self) -> DataAccessService:
        """Ensure data_service is initialized, lazily obtaining it if needed."""
        if self.data_service is None:
            from src.backend.services.data_access_service import DataAccessService
            self.data_service = await DataAccessService.get_instance()
        return self.data_service
    
    def _get_player_display_name(self, player: Dict[str, Any]) -> str:
        """
        Get the best available display name for a player for logging.
        
        Args:
            player: Player data dictionary
            
        Returns:
            Display name (player_name > discord_username > "Unknown")
        """
        if not player:
            return "Unknown"
        return player["player_name"] or player["discord_username"]
    
    def get_player(self, discord_uid: int) -> Optional[Dict[str, Any]]:
        """
        Get player information by Discord UID.
        
        Uses DataAccessService for sub-millisecond in-memory lookup.
        
        Args:
            discord_uid: Discord user ID.
        
        Returns:
            Player data dictionary or None if not found.
        """
        return self.data_service.get_player_info(discord_uid)
    
    def player_exists(self, discord_uid: int) -> bool:
        """
        Check if a player exists.
        
        Uses DataAccessService for sub-millisecond in-memory lookup.
        
        Args:
            discord_uid: Discord user ID.
        
        Returns:
            True if player exists, False otherwise.
        """
        return self.data_service.player_exists(discord_uid)
    
    def ensure_player_exists(self, discord_uid: int, discord_username: str) -> Dict[str, Any]:
        """
        Ensure a player record exists in memory and database.
        
        If the player doesn't exist, creates a minimal record with discord_uid and discord_username.
        If the player already exists but has a different username, updates the username and logs the change.
        If the player already exists with the same username, returns their existing data.
        
        This should be called at the start of any slash command to ensure the user
        has a database record before any operations are performed.
        
        Uses DataAccessService for fast in-memory operations.
        
        Args:
            discord_uid: Discord user ID.
            discord_username: Discord username (e.g., "username" from username#1234 or @username).
        
        Returns:
            Player data dictionary (either existing or newly created).
        """
        player = self.get_player(discord_uid)
        
        if player is None:
            # Create minimal player record with discord username
            # Note: create_player is sync but will queue async write
            self.create_player(discord_uid=discord_uid, discord_username=discord_username)
            player = self.get_player(discord_uid)
        else:
            # Check if username has changed
            current_username = player.get('discord_username')
            if current_username != discord_username:
                # Update username and log the change
                # Note: update_player is sync but will queue async write
                self.update_player(
                    discord_uid=discord_uid,
                    discord_username=discord_username,
                    log_changes=True
                )
                # Get updated player data
                player = self.get_player(discord_uid)
        
        return player
    
    def create_player(
        self,
        discord_uid: int,
        discord_username: str = "Unknown",
        player_name: Optional[str] = None,
        battletag: Optional[str] = None,
        country: Optional[str] = None,
        region: Optional[str] = None,
        activation_code: Optional[str] = None
    ) -> int:
        """
        Create a new player.
        
        Uses DataAccessService for instant in-memory creation + async DB write.
        
        Args:
            discord_uid: Discord user ID.
            discord_username: Discord username (e.g., "username" from username#1234 or @username).
                              Defaults to "Unknown" if not provided.
            player_name: Player's in-game name.
            battletag: Player's BattleTag.
            country: Country code.
            region: Region code.
            activation_code: Activation code (not supported by DataAccessService).
        
        Returns:
            The discord_uid (for backwards compatibility).
        """
        # Run async create in sync context
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If called from async context, just schedule it
            asyncio.create_task(self.data_service.create_player(
                discord_uid=discord_uid,
                discord_username=discord_username,
                player_name=player_name,
                battletag=battletag,
                country=country,
                region=region
            ))
        else:
            # If called from sync context, run it
            loop.run_until_complete(self.data_service.create_player(
                discord_uid=discord_uid,
                discord_username=discord_username,
                player_name=player_name,
                battletag=battletag,
                country=country,
                region=region
            ))
        
        return discord_uid
    
    def update_player(
        self,
        discord_uid: int,
        discord_username: Optional[str] = None,
        player_name: Optional[str] = None,
        battletag: Optional[str] = None,
        alt_player_name_1: Optional[str] = None,
        alt_player_name_2: Optional[str] = None,
        country: Optional[str] = None,
        region: Optional[str] = None,
        log_changes: bool = False
    ) -> bool:
        """
        Update player information.
        
        Args:
            discord_uid: Discord user ID.
            discord_username: Discord username (e.g., "username" from username#1234 or @username).
            player_name: Player's in-game name.
            battletag: Player's BattleTag.
            alt_player_name_1: First alternative name.
            alt_player_name_2: Second alternative name.
            country: Country code.
            region: Region code.
            log_changes: If True, logs each field change individually to player_action_logs.
        
        Returns:
            True if successful, False otherwise.
        """
        # Get old values before update if logging is enabled
        old_player = None
        if log_changes:
            old_player = self.get_player(discord_uid)

        # Use a dictionary to hold updates
        update_payload = {
            "discord_username": discord_username,
            "player_name": player_name,
            "battletag": battletag,
            "alt_player_name_1": alt_player_name_1,
            "alt_player_name_2": alt_player_name_2,
            "country": country,
            "region": region,
        }
        # Filter out None values so we only update provided fields
        update_payload = {k: v for k, v in update_payload.items() if v is not None}

        # Perform the update via DataAccessService (async)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(
                self.data_service.update_player_info(discord_uid, **update_payload)
            )
        else:
            loop.run_until_complete(
                self.data_service.update_player_info(discord_uid, **update_payload)
            )

        # Log each field change individually
        if log_changes and old_player:
            current_player_name = (
                player_name
                if player_name is not None
                else old_player.get("player_name")
                or old_player["discord_username"]
            )
            
            for key, new_value in update_payload.items():
                old_value = old_player.get(key)
                # Normalize empty strings to None for comparison
                if isinstance(new_value, str) and not new_value.strip():
                    new_value = None
                if isinstance(old_value, str) and not old_value.strip():
                    old_value = None

                if old_value != new_value:
                    asyncio.create_task(self.data_service.log_player_action(
                        discord_uid=discord_uid,
                        player_name=current_player_name,
                        setting_name=key,
                        old_value=str(old_value) if old_value is not None else None,
                        new_value=str(new_value) if new_value is not None else None,
                    ))

        return True


    def update_country(self, discord_uid: int, country: str) -> bool:
        """
        Update player's country.
        
        Args:
            discord_uid: Discord user ID.
            country: Country code.
        
        Returns:
            True if successful, False otherwise.
        """
        old_player = self.get_player(discord_uid)
        
        # Perform update via DataAccessService
        loop = asyncio.get_event_loop()
        task = self.data_service.update_player_info(discord_uid, country=country)
        if loop.is_running():
            asyncio.create_task(task)
        else:
            loop.run_until_complete(task)

        # Log the change
        if old_player:
            player_name = self._get_player_display_name(old_player)
            old_country = old_player.get("country")
            if old_country != country:
                asyncio.create_task(self.data_service.log_player_action(
                    discord_uid=discord_uid,
                    player_name=player_name,
                    setting_name="country",
                    old_value=old_country,
                    new_value=country,
                ))
        
        return True

    def submit_activation_code(self, discord_uid: int, activation_code: str) -> Dict[str, Any]:
        """
        DISABLED: Submit an activation code for a player.
        
        This method is obsolete and should not be used.
        The activation system has been disabled.
        
        Args:
            discord_uid: Discord user ID.
            activation_code: The activation code to submit.
        
        Returns:
            Dictionary with status and message.
        """
        # Return error since activation is disabled
        return {"status": "error", "message": "Activation system is disabled"}
        # Check if player exists
        player = self.get_player(discord_uid)
        
        if player:
            # Update existing player's activation code
            success = self.writer.update_player_activation_code(discord_uid, activation_code)
            if success:
                # Invalidate cache since player record changed
                player_cache.invalidate(discord_uid)
                
                player_name = self._get_player_display_name(player)
                self.writer.log_player_action(
                    discord_uid=discord_uid,
                    player_name=player_name,
                    setting_name="activation_code",
                    old_value=player.get("activation_code"),
                    new_value=activation_code
                )
                return {"status": "ok", "message": "Activation code updated"}
            else:
                return {"status": "error", "message": "Failed to update activation code"}
        else:
            # Create new player with activation code
            player_id = self.create_player(
                discord_uid=discord_uid,
                activation_code=activation_code
            )
            if player_id:
                # Invalidate cache for new player
                player_cache.invalidate(discord_uid)
                return {"status": "ok", "message": "Player created with activation code"}
            else:
                return {"status": "error", "message": "Failed to create player"}
    
    def accept_terms_of_service(self, discord_uid: int) -> bool:
        """
        Mark player as having accepted terms of service.
        
        Args:
            discord_uid: Discord user ID.
        
        Returns:
            True if successful, False otherwise.
        """
        player = self.get_player(discord_uid)
        
        # Create player if they don't exist
        if not player:
            self.create_player(discord_uid=discord_uid)
            player = self.get_player(discord_uid)
        
        # This operation is not performance-critical and has no equivalent in DataAccessService yet.
        # It can be migrated later if needed. For now, we leave the legacy writer.
        success = self.writer.accept_terms_of_service(discord_uid)
        
        if success:
            # Invalidate cache since player record changed
            player_cache.invalidate(discord_uid)
            
            if player:
                player_name = self._get_player_display_name(player)
                asyncio.create_task(self.data_service.log_player_action(
                    discord_uid=discord_uid,
                    player_name=player_name,
                    setting_name="accepted_tos",
                    old_value="False",
                    new_value="True",
                ))
        
        return success
    
    def complete_setup(
        self,
        discord_uid: int,
        player_name: str,
        battletag: str,
        alt_player_name_1: Optional[str] = None,
        alt_player_name_2: Optional[str] = None,
        country: Optional[str] = None,
        region: Optional[str] = None
    ) -> bool:
        """
        Complete player setup.
        
        Logs each field change individually in player_action_logs.
        
        Args:
            discord_uid: Discord user ID.
            player_name: Player's in-game name.
            battletag: Player's BattleTag.
            alt_player_name_1: First alternative name.
            alt_player_name_2: Second alternative name.
            country: Country code.
            region: Region code.
        
        Returns:
            True if successful, False otherwise.
        """
        player = self.get_player(discord_uid)
        
        # Create player if they don't exist
        if not player:
            self.create_player(
                discord_uid=discord_uid,
                player_name=player_name,
                battletag=battletag,
                country=country,
                region=region
            )
        
        # Update player information with logging enabled
        # This will log each field change as a separate row in player_action_logs
        self.update_player(
            discord_uid=discord_uid,
            player_name=player_name,
            battletag=battletag,
            alt_player_name_1=alt_player_name_1,
            alt_player_name_2=alt_player_name_2,
            country=country,
            region=region,
            log_changes=True  # Enable individual field logging
        )
        
        # Mark setup as complete
        old_player = self.get_player(discord_uid)
        
        # This operation is not performance-critical and has no equivalent in DataAccessService yet.
        # It can be migrated later if needed. For now, we leave the legacy writer.
        success = self.writer.complete_setup(discord_uid)
        
        if success:
            # Invalidate cache since player record changed
            player_cache.invalidate(discord_uid)
            
            # Only log if completed_setup actually changed
            if old_player and not old_player.get("completed_setup"):
                asyncio.create_task(self.data_service.log_player_action(
                    discord_uid=discord_uid,
                    player_name=player_name,
                    setting_name="completed_setup",
                    old_value="False",
                    new_value="True",
                ))
        
        return success
    
    def get_player_action_logs(
        self,
        discord_uid: Optional[int] = None,
        limit: int = 100
    ) -> list:
        """
        Get player action logs.
        
        Args:
            discord_uid: Discord user ID (optional, None for all players).
            limit: Maximum number of logs to return.
        
        Returns:
            List of action log dictionaries.
        """
        return self.reader.get_player_action_logs(discord_uid, limit)
    
    def get_remaining_aborts(self, discord_uid: int) -> int:
        """
        Get the number of remaining aborts for a player.
        
        Args:
            discord_uid: Discord user ID.
        
        Returns:
            Number of remaining aborts (defaults to 3 if player not found).
        """
        player = self.get_player(discord_uid)
        if player:
            return player.get('remaining_aborts', 3)
        return 3
    
    def decrement_aborts(self, discord_uid: int) -> bool:
        """
        Decrement the remaining aborts count for a player.
        
        Args:
            discord_uid: Discord user ID.
        
        Returns:
            True if successful, False otherwise.
        """
        player = self.get_player(discord_uid)
        if not player:
            return False
        
        current_aborts = self.data_service.get_remaining_aborts(discord_uid)
        new_aborts = max(0, current_aborts - 1)
        
        loop = asyncio.get_event_loop()
        task = self.data_service.update_remaining_aborts(discord_uid, new_aborts)

        if loop.is_running():
            asyncio.create_task(task)
        else:
            loop.run_until_complete(task)

        # Log the abort usage
        player_name = self._get_player_display_name(player)
        asyncio.create_task(self.data_service.log_player_action(
            discord_uid=discord_uid,
            player_name=player_name,
            setting_name="remaining_aborts",
            old_value=str(current_aborts),
            new_value=str(new_aborts),
        ))
        
        return True