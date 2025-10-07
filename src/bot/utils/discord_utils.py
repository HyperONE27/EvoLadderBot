"""
Discord interaction utilities for centralized ephemerality control.
"""
from typing import Union, Optional
import discord


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
    return interaction.response.send_message(
        content=content,
        embed=embed,
        view=view,
        ephemeral=ephemeral_kwargs["ephemeral"],
        **kwargs
    )


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
