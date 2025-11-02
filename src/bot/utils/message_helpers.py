"""
Helper functions for queuing Discord API calls through the message queue.

This module provides wrapper functions that replace direct Discord API calls with
queued equivalents. All functions maintain the same signature and return behavior
as the original Discord.py methods, but route calls through the prioritized message
queue for rate limiting and ordering control.

Example usage:
    from src.bot.utils.message_helpers import queue_interaction_response
    
    @bot.tree.command()
    async def join(interaction: discord.Interaction):
        await queue_interaction_response(interaction, content="You joined the queue!")
"""

from typing import Optional

import discord

from src.bot.message_queue import get_message_queue


# =============================================================================
# INTERACTION OPERATIONS (High Priority Queue)
# =============================================================================

async def queue_interaction_response(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    ephemeral: bool = False,
    **kwargs
):
    """
    Queue an interaction.response.send_message() call.
    
    Args:
        interaction: The Discord interaction object
        content: Text content to send
        embed: Embed to send
        view: View to send
        ephemeral: Whether the message should be ephemeral
        **kwargs: Additional arguments for send_message
        
    Returns:
        None (interaction responses don't return message objects)
        
    Raises:
        Exception: If the Discord API call fails after 3 retries
    """
    queue = get_message_queue()
    
    async def operation():
        return await interaction.response.send_message(
            content=content,
            embed=embed,
            view=view,
            ephemeral=ephemeral,
            **kwargs
        )
    
    future = await queue.enqueue_interaction(operation)
    return await future


async def queue_interaction_defer(
    interaction: discord.Interaction,
    ephemeral: bool = False,
    **kwargs
):
    """
    Queue an interaction.response.defer() call.
    
    Args:
        interaction: The Discord interaction object
        ephemeral: Whether the deferred response should be ephemeral
        **kwargs: Additional arguments for defer
        
    Returns:
        None
        
    Raises:
        Exception: If the Discord API call fails after 3 retries
    """
    queue = get_message_queue()
    
    async def operation():
        return await interaction.response.defer(ephemeral=ephemeral, **kwargs)
    
    future = await queue.enqueue_interaction(operation)
    return await future


async def queue_interaction_edit(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    **kwargs
):
    """
    Queue an interaction.response.edit_message() call.
    
    Args:
        interaction: The Discord interaction object
        content: Text content to update
        embed: Embed to update
        view: View to update
        **kwargs: Additional arguments for edit_message
        
    Returns:
        None
        
    Raises:
        Exception: If the Discord API call fails after 3 retries
    """
    queue = get_message_queue()
    
    async def operation():
        return await interaction.response.edit_message(
            content=content,
            embed=embed,
            view=view,
            **kwargs
        )
    
    future = await queue.enqueue_interaction(operation)
    return await future


async def queue_followup(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    ephemeral: bool = False,
    wait: bool = False,
    **kwargs
) -> Optional[discord.WebhookMessage]:
    """
    Queue an interaction.followup.send() call.
    
    Args:
        interaction: The Discord interaction object
        content: Text content to send
        embed: Embed to send
        view: View to send
        ephemeral: Whether the message should be ephemeral
        wait: Whether to wait for the message to be created
        **kwargs: Additional arguments for followup.send
        
    Returns:
        WebhookMessage if wait=True, else None
        
    Raises:
        Exception: If the Discord API call fails after 3 retries
    """
    queue = get_message_queue()
    
    async def operation():
        return await interaction.followup.send(
            content=content,
            embed=embed,
            view=view,
            ephemeral=ephemeral,
            wait=wait,
            **kwargs
        )
    
    future = await queue.enqueue_interaction(operation)
    return await future


async def queue_interaction_modal(
    interaction: discord.Interaction,
    modal: discord.ui.Modal,
    **kwargs
):
    """
    Queue an interaction.response.send_modal() call.
    
    Args:
        interaction: The Discord interaction object
        modal: The modal to send
        **kwargs: Additional arguments for send_modal
        
    Returns:
        None (modal responses don't return message objects)
        
    Raises:
        Exception: If the Discord API call fails after 3 retries
    """
    queue = get_message_queue()
    
    async def operation():
        return await interaction.response.send_modal(modal, **kwargs)
    
    future = await queue.enqueue_interaction(operation)
    return await future


async def queue_edit_original(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    **kwargs
) -> discord.InteractionMessage:
    """
    Queue an interaction.edit_original_response() call.
    
    Args:
        interaction: The Discord interaction object
        content: Text content to update
        embed: Embed to update
        view: View to update
        **kwargs: Additional arguments for edit_original_response
        
    Returns:
        InteractionMessage object
        
    Raises:
        Exception: If the Discord API call fails after 3 retries
    """
    queue = get_message_queue()
    
    async def operation():
        return await interaction.edit_original_response(
            content=content,
            embed=embed,
            view=view,
            **kwargs
        )
    
    future = await queue.enqueue_interaction(operation)
    return await future


# =============================================================================
# NOTIFICATION OPERATIONS (Low Priority Queue)
# =============================================================================

async def queue_channel_send(
    channel,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    **kwargs
) -> discord.Message:
    """
    Queue a channel.send() call.
    
    Args:
        channel: The Discord channel object
        content: Text content to send
        embed: Embed to send
        view: View to send
        **kwargs: Additional arguments for send
        
    Returns:
        Message object
        
    Raises:
        Exception: If the Discord API call fails after 3 retries
    """
    queue = get_message_queue()
    
    async def operation():
        return await channel.send(
            content=content,
            embed=embed,
            view=view,
            **kwargs
        )
    
    future = await queue.enqueue_notification(operation)
    return await future


async def queue_user_send(
    user,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    **kwargs
) -> discord.Message:
    """
    Queue a user.send() call (DM).
    
    Args:
        user: The Discord user object
        content: Text content to send
        embed: Embed to send
        view: View to send
        **kwargs: Additional arguments for send
        
    Returns:
        Message object
        
    Raises:
        Exception: If the Discord API call fails after 3 retries
    """
    queue = get_message_queue()
    
    async def operation():
        return await user.send(
            content=content,
            embed=embed,
            view=view,
            **kwargs
        )
    
    future = await queue.enqueue_notification(operation)
    return await future


async def queue_message_edit(
    message: discord.Message,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    **kwargs
) -> discord.Message:
    """
    Queue a message.edit() call.
    
    Args:
        message: The Discord message object to edit
        content: Text content to update
        embed: Embed to update
        view: View to update
        **kwargs: Additional arguments for edit
        
    Returns:
        Message object
        
    Raises:
        Exception: If the Discord API call fails after 3 retries
    """
    queue = get_message_queue()
    
    async def operation():
        return await message.edit(
            content=content,
            embed=embed,
            view=view,
            **kwargs
        )
    
    future = await queue.enqueue_notification(operation)
    return await future


async def queue_message_delete(
    message: discord.Message,
    **kwargs
):
    """
    Queue a message.delete() call.
    
    Args:
        message: The Discord message object to delete
        **kwargs: Additional arguments for delete
        
    Returns:
        None
        
    Raises:
        Exception: If the Discord API call fails after 3 retries
    """
    queue = get_message_queue()
    
    async def operation():
        return await message.delete(**kwargs)
    
    future = await queue.enqueue_notification(operation)
    return await future

