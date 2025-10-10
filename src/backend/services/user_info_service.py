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
from src.backend.db.db_reader_writer import DatabaseReader, DatabaseWriter


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
    """Service for managing user information and settings."""
    
    def __init__(self) -> None:
        self.reader = DatabaseReader()
        self.writer = DatabaseWriter()
    
    def get_player(self, discord_uid: int) -> Optional[Dict[str, Any]]:
        """
        Get player information by Discord UID.
        
        Args:
            discord_uid: Discord user ID.
        
        Returns:
            Player data dictionary or None if not found.
        """
        return self.reader.get_player_by_discord_uid(discord_uid)
    
    def player_exists(self, discord_uid: int) -> bool:
        """
        Check if a player exists.
        
        Args:
            discord_uid: Discord user ID.
        
        Returns:
            True if player exists, False otherwise.
        """
        return self.reader.player_exists(discord_uid)
    
    def ensure_player_exists(self, discord_uid: int, discord_username: str) -> Dict[str, Any]:
        """
        Ensure a player record exists in the database.
        
        If the player doesn't exist, creates a minimal record with discord_uid and discord_username.
        If the player already exists but has a different username, updates the username and logs the change.
        If the player already exists with the same username, returns their existing data.
        
        This should be called at the start of any slash command to ensure the user
        has a database record before any operations are performed.
        
        Args:
            discord_uid: Discord user ID.
            discord_username: Discord username (e.g., "username" from username#1234 or @username).
        
        Returns:
            Player data dictionary (either existing or newly created).
        """
        player = self.get_player(discord_uid)
        
        if player is None:
            # Create minimal player record with discord username
            self.create_player(discord_uid=discord_uid, discord_username=discord_username)
            player = self.get_player(discord_uid)
        else:
            # Check if username has changed
            current_username = player.get('discord_username')
            if current_username != discord_username:
                # Update username and log the change
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
        
        Args:
            discord_uid: Discord user ID.
            discord_username: Discord username (e.g., "username" from username#1234 or @username).
                              Defaults to "Unknown" if not provided.
            player_name: Player's in-game name.
            battletag: Player's BattleTag.
            country: Country code.
            region: Region code.
            activation_code: Activation code.
        
        Returns:
            The ID of the newly created player.
        """
        return self.writer.create_player(
            discord_uid=discord_uid,
            discord_username=discord_username,
            player_name=player_name,
            battletag=battletag,
            country=country,
            region=region,
            activation_code=activation_code
        )
    
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
        
        # Perform the update
        success = self.writer.update_player(
            discord_uid=discord_uid,
            discord_username=discord_username,
            player_name=player_name,
            battletag=battletag,
            alt_player_name_1=alt_player_name_1,
            alt_player_name_2=alt_player_name_2,
            country=country,
            region=region
        )
        
        # Log each field change individually
        if success and log_changes and old_player:
            # Use updated player_name if provided, otherwise use old value, fallback to discord_username
            current_player_name = (player_name if player_name is not None 
                                 else old_player.get("player_name") 
                                 or old_player.get("discord_username", "Unknown"))
            
            # Log each field that was provided and actually changed
            if discord_username is not None and old_player.get("discord_username") != discord_username:
                self.writer.log_player_action(
                    discord_uid=discord_uid,
                    player_name=current_player_name,
                    setting_name="discord_username",
                    old_value=old_player.get("discord_username"),
                    new_value=discord_username
                )
            
            if player_name is not None and old_player.get("player_name") != player_name:
                self.writer.log_player_action(
                    discord_uid=discord_uid,
                    player_name=current_player_name,
                    setting_name="player_name",
                    old_value=old_player.get("player_name"),
                    new_value=player_name
                )
            
            if battletag is not None and old_player.get("battletag") != battletag:
                self.writer.log_player_action(
                    discord_uid=discord_uid,
                    player_name=current_player_name,
                    setting_name="battletag",
                    old_value=old_player.get("battletag"),
                    new_value=battletag
                )
            
            if alt_player_name_1 is not None:
                # Normalize: empty string becomes None for comparison
                normalized_new = alt_player_name_1.strip() if alt_player_name_1 else None
                normalized_old = old_player.get("alt_player_name_1") or None
                if normalized_old != normalized_new:
                    self.writer.log_player_action(
                        discord_uid=discord_uid,
                        player_name=current_player_name,
                        setting_name="alt_player_name_1",
                        old_value=old_player.get("alt_player_name_1"),
                        new_value=normalized_new
                    )
            
            if alt_player_name_2 is not None:
                # Normalize: empty string becomes None for comparison
                normalized_new = alt_player_name_2.strip() if alt_player_name_2 else None
                normalized_old = old_player.get("alt_player_name_2") or None
                if normalized_old != normalized_new:
                    self.writer.log_player_action(
                        discord_uid=discord_uid,
                        player_name=current_player_name,
                        setting_name="alt_player_name_2",
                        old_value=old_player.get("alt_player_name_2"),
                        new_value=normalized_new
                    )
            
            if country is not None and old_player.get("country") != country:
                self.writer.log_player_action(
                    discord_uid=discord_uid,
                    player_name=current_player_name,
                    setting_name="country",
                    old_value=old_player.get("country"),
                    new_value=country
                )
            
            if region is not None and old_player.get("region") != region:
                self.writer.log_player_action(
                    discord_uid=discord_uid,
                    player_name=current_player_name,
                    setting_name="region",
                    old_value=old_player.get("region"),
                    new_value=region
                )
        
        return success
    
    def update_country(self, discord_uid: int, country: str) -> bool:
        """
        Update player's country.
        
        Args:
            discord_uid: Discord user ID.
            country: Country code.
        
        Returns:
            True if successful, False otherwise.
        """
        player = self.get_player(discord_uid)
        old_country = player.get("country") if player else None
        
        success = self.writer.update_player_country(discord_uid, country)
        
        if success and player:
            # Use player_name if available, otherwise use discord_username, fallback to "Unknown"
            player_name = (player.get("player_name") 
                          or player.get("discord_username") 
                          or "Unknown")
            self.writer.log_player_action(
                discord_uid=discord_uid,
                player_name=player_name,
                setting_name="country",
                old_value=old_country,
                new_value=country
            )
        
        return success
    
    def submit_activation_code(self, discord_uid: int, activation_code: str) -> Dict[str, Any]:
        """
        Submit an activation code for a player.
        
        Args:
            discord_uid: Discord user ID.
            activation_code: The activation code to submit.
        
        Returns:
            Dictionary with status and message.
        """
        # Check if player exists
        player = self.get_player(discord_uid)
        
        if player:
            # Update existing player's activation code
            success = self.writer.update_player_activation_code(discord_uid, activation_code)
            if success:
                # Use player_name if available, otherwise use discord_username, fallback to "Unknown"
                player_name = (player.get("player_name") 
                              or player.get("discord_username") 
                              or "Unknown")
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
        
        success = self.writer.accept_terms_of_service(discord_uid)
        
        if success and player:
            # Use player_name if available, otherwise use discord_username, fallback to "Unknown"
            player_name = (player.get("player_name") 
                          or player.get("discord_username") 
                          or "Unknown")
            self.writer.log_player_action(
                discord_uid=discord_uid,
                player_name=player_name,
                setting_name="accepted_tos",
                old_value="False",
                new_value="True"
            )
        
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
        success = self.writer.complete_setup(discord_uid)
        
        if success:
            # Only log if completed_setup actually changed
            if old_player and not old_player.get("completed_setup"):
                self.writer.log_player_action(
                    discord_uid=discord_uid,
                    player_name=player_name,
                    setting_name="completed_setup",
                    old_value="False",
                    new_value="True"
                )
        
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
