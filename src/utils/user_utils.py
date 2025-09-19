import discord
from typing import Dict, Any

def get_user_info(interaction: discord.Interaction) -> Dict[str, Any]:
    """
    Extract user information from a Discord interaction
    
    Args:
        interaction: Discord interaction object
        
    Returns:
        Dictionary containing user information
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
    Create a Discord embed field for user information
    
    Args:
        user_info: User information dictionary from get_user_info()
        title: Title for the embed field
        
    Returns:
        Dictionary with name and value for Discord embed field
    """
    user_text = f"**Username:** {user_info['display_name']}\n**Discord ID:** `{user_info['id']}`"
    
    if user_info['discriminator'] and user_info['discriminator'] != '0':
        user_text += f"\n**Tag:** {user_info['username']}#{user_info['discriminator']}"
    
    return {
        'name': title,
        'value': user_text,
        'inline': False
    }

def log_user_action(user_info: Dict[str, Any], action: str, details: str = ""):
    """
    Log user action with consistent formatting
    
    Args:
        user_info: User information dictionary from get_user_info()
        action: Description of the action performed
        details: Additional details about the action
    """
    log_message = f"User {user_info['display_name']} (ID: {user_info['id']}) {action}"
    if details:
        log_message += f" - {details}"
    print(log_message)
