"""
Discord interaction utilities for centralized ephemerality control.
"""
from typing import Union, Optional
import discord
import json
import os


def should_be_ephemeral(interaction: discord.Interaction) -> bool:
    """
    Determine if a Discord interaction response should be ephemeral.
    
    Rules:
    - All commands are non-ephemeral in DMs (private messages)
    - All commands are ephemeral in guild channels (servers)
    
    Args:
        interaction: The Discord interaction object
        
    Returns:
        bool: True if the response should be ephemeral, False otherwise
    """
    # If the interaction is in a DM (guild is None), responses should not be ephemeral
    if interaction.guild is None:
        return False
    
    # If the interaction is in a guild channel, responses should be ephemeral
    return True


def get_ephemeral_kwargs(interaction: discord.Interaction) -> dict:
    """
    Get the ephemeral parameter for Discord interaction responses.
    
    Args:
        interaction: The Discord interaction object
        
    Returns:
        dict: Dictionary containing the ephemeral parameter
    """
    return {"ephemeral": should_be_ephemeral(interaction)}


def send_ephemeral_response(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    **kwargs
) -> Union[discord.InteractionResponse, discord.WebhookMessage]:
    """
    Send a response with centralized ephemerality control.
    
    Args:
        interaction: The Discord interaction object
        content: Text content to send
        embed: Embed to send
        view: View to send
        **kwargs: Additional arguments for send_message
        
    Returns:
        The response object
    """
    ephemeral_kwargs = get_ephemeral_kwargs(interaction)
    
    # Build the message parameters, only including view if it's not None
    message_params = {
        "content": content,
        "embed": embed,
        "ephemeral": ephemeral_kwargs["ephemeral"],
        **kwargs
    }
    
    # Only add view parameter if it's not None
    if view is not None:
        message_params["view"] = view
    
    return interaction.response.send_message(**message_params)


def edit_ephemeral_response(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    **kwargs
) -> Union[discord.InteractionResponse, discord.WebhookMessage]:
    """
    Edit a response with centralized ephemerality control.
    
    Args:
        interaction: The Discord interaction object
        content: Text content to send
        embed: Embed to send
        view: View to send
        **kwargs: Additional arguments for edit_message
        
    Returns:
        The response object
    """
    ephemeral_kwargs = get_ephemeral_kwargs(interaction)
    return interaction.response.edit_message(
        content=content,
        embed=embed,
        view=view,
        **kwargs
    )


def followup_ephemeral_response(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    **kwargs
) -> discord.WebhookMessage:
    """
    Send a followup response with centralized ephemerality control.
    
    Args:
        interaction: The Discord interaction object
        content: Text content to send
        embed: Embed to send
        view: View to send
        **kwargs: Additional arguments for followup.send
        
    Returns:
        The followup message object
    """
    ephemeral_kwargs = get_ephemeral_kwargs(interaction)
    return interaction.followup.send(
        content=content,
        embed=embed,
        view=view,
        ephemeral=ephemeral_kwargs["ephemeral"],
        **kwargs
    )


def country_to_flag(code: str) -> str:
    """Convert 2-letter country code to 🇨🇦 style flag emoji."""
    code = code.upper()
    return chr(127397 + ord(code[0])) + chr(127397 + ord(code[1]))


def get_race_emote(race: str) -> str:
    """Get the Discord emote for a race from emotes.json."""
    # Get the project root directory
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    emotes_path = os.path.join(project_root, "data", "misc", "emotes.json")
    
    try:
        with open(emotes_path, 'r', encoding='utf-8') as f:
            emotes_data = json.load(f)
        
        # Find the emote for the race
        for emote in emotes_data:
            if emote.get("name") == race:
                return emote.get("markdown", f":{race}:")
        
        # Fallback to generic format if not found
        return f":{race}:"
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        # Fallback to generic format if file not found or invalid
        return f":{race}:"


def get_flag_emote(country_code: str) -> str:
    """Get the appropriate flag emote for a country code."""
    if country_code in ["XX", "ZZ"]:
        # Use custom emotes for non-representing and other
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        emotes_path = os.path.join(project_root, "data", "misc", "emotes.json")
        
        try:
            with open(emotes_path, 'r', encoding='utf-8') as f:
                emotes_data = json.load(f)
            
            # Find the flag emote
            for emote in emotes_data:
                if emote.get("name") == f"flag_{country_code.lower()}":
                    return emote.get("markdown", f":flag_{country_code.lower()}:")
            
            # Fallback to generic format if not found
            return f":flag_{country_code.lower()}:"
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            # Fallback to generic format if file not found or invalid
            return f":flag_{country_code.lower()}:"
    else:
        # Use Unicode flag emoji for standard country codes
        return country_to_flag(country_code)
