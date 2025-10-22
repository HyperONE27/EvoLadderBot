"""
Prune command for cleaning up old bot messages.

This command allows users to delete the bot's messages in the current DM channel
that are older than GLOBAL_TIMEOUT. This helps reduce lag caused by many old
embeds and views accumulating in the channel.

Messages associated with active queue views are NOT pruned (safety measure).
"""

import asyncio
import discord
from discord import app_commands
from datetime import datetime, timezone, timedelta
from typing import List

from src.backend.services.command_guard_service import CommandGuardError
from src.backend.services.app_context import command_guard_service
from src.bot.utils.discord_utils import send_ephemeral_response
from src.bot.components.command_guard_embeds import create_command_guard_error_embed
from src.bot.config import GLOBAL_TIMEOUT, RECENT_MESSAGE_PROTECTION_MINUTES, QUEUE_MESSAGE_PROTECTION_DAYS, PRUNE_DELETE_DELAY_SECONDS
from src.backend.services.performance_service import FlowTracker
from src.bot.utils.command_decorators import dm_only
from src.bot.components.confirm_restart_cancel_buttons import ConfirmRestartCancelButtons


# Track active queue message IDs to avoid deleting them
_active_queue_message_ids: set = set()


def register_active_queue_message(message_id: int) -> None:
    """
    Register a message ID as associated with an active queue view.
    
    Args:
        message_id: Discord message ID to protect from pruning
    """
    _active_queue_message_ids.add(message_id)


def unregister_active_queue_message(message_id: int) -> None:
    """
    Unregister a message ID when the queue view is no longer active.
    
    Args:
        message_id: Discord message ID to allow pruning
    """
    _active_queue_message_ids.discard(message_id)


def is_prune_related_message(message: discord.Message) -> bool:
    """
    Detect if a message is related to the prune command and should be protected.
    We never want to delete prune messages, regardless of age.
    
    Args:
        message: Discord message to check
        
    Returns:
        True if the message appears to be prune-related and should be protected
    """
    # Check if message has embeds
    if not message.embeds:
        return False
    
    embed = message.embeds[0]  # Check the first embed
    
    # Check for prune-related embed titles
    prune_titles = [
        "🗑️ Confirm Message Deletion",
        "🗑️ Pruning in Progress...",
        "✅ Messages Pruned",
        "❌ Failed to Prune",
        "✅ No Messages to Prune",
        "🗑️ Confirm Message Deletion",  # Duplicate to be extra sure
    ]
    
    if embed.title:
        for title_pattern in prune_titles:
            if title_pattern in embed.title:
                return True
    
    # Check for prune-related descriptions
    prune_descriptions = [
        "message(s) will be deleted",
        "Deleting",
        "old message(s)",
        "Successfully deleted",
        "Could not delete",
        "No bot messages found",
        "Queue-related messages",
        "automatically protected",
        "Delete old bot messages",
        "to reduce lag",
    ]
    
    if embed.description:
        for desc_pattern in prune_descriptions:
            if desc_pattern in embed.description:
                return True
    
    # Check for prune-related field names
    if embed.fields:
        for field in embed.fields:
            if field.name and any(keyword in field.name.lower() for keyword in ["oldest message", "newest message", "estimated time"]):
                return True
            if field.value and any(keyword in field.value.lower() for keyword in ["jump to message", "created:", "seconds"]):
                return True
    
    return False


def is_queue_related_message(message: discord.Message) -> bool:
    """
    Detect if a message contains queue-related content that should be protected from pruning.
    Only protects queue messages that are less than a week old.
    
    Args:
        message: Discord message to check
        
    Returns:
        True if the message appears to be queue-related and should be protected
    """
    # Check if message has embeds
    if not message.embeds:
        return False
    
    # Only protect queue messages that are less than the configured protection period
    protection_cutoff = datetime.now(timezone.utc) - timedelta(days=QUEUE_MESSAGE_PROTECTION_DAYS)
    if message.created_at < protection_cutoff:
        return False
    
    embed = message.embeds[0]  # Check the first embed
    
    # Check for queue-related embed titles
    queue_titles = [
        "🔍 Searching...",
        "Match #",  # Match found views start with "Match #"
    ]
    
    if embed.title:
        for title_pattern in queue_titles:
            if title_pattern in embed.title:
                return True
    
    # Check for queue-related field names
    queue_field_names = [
        "Player Information:",
        "Match Information:",
        "Match Result:",
        "Replay Status:"
    ]
    
    if embed.fields:
        for field in embed.fields:
            if field.name in queue_field_names:
                return True
    
    # Check for queue-related button labels in components
    if message.components:
        for component in message.components:
            if hasattr(component, 'children'):
                for child in component.children:
                    if hasattr(child, 'label') and child.label:
                        queue_button_labels = [
                            "Cancel Queue",  # From QueueSearchingView
                            "Abort Match",  # From MatchFoundView
                            "Report match result...",
                            "Select result first...",
                        ]
                        if child.label in queue_button_labels:
                            return True
    
    # Check for queue-related descriptions
    queue_descriptions = [
        "The queue is searching for a game",
        "Search interval:",
        "Next match wave:",
        "Current players queueing:",
    ]
    
    if embed.description:
        for desc_pattern in queue_descriptions:
            if desc_pattern in embed.description:
                return True
    
    return False


def register_prune_command(tree: app_commands.CommandTree):
    """Register the prune command"""
    @tree.command(
        name="prune",
        description=f"Delete old bot messages (older than {GLOBAL_TIMEOUT/60} minutes) to reduce lag"
    )
    async def prune(interaction: discord.Interaction):
        await prune_command(interaction)
    
    return prune


@dm_only
async def prune_command(interaction: discord.Interaction):
    """
    Handle the /prune slash command.
    
    Deletes bot messages in the current DM channel that are:
    - Sent by this bot
    - Older than GLOBAL_TIMEOUT seconds
    - NOT associated with active queue views
    """
    flow = FlowTracker("prune_command", user_id=interaction.user.id)
    
    try:
        flow.checkpoint("guard_checks_start")
        player = command_guard_service.ensure_player_record(
            interaction.user.id, 
            interaction.user.name
        )
        command_guard_service.require_tos_accepted(player)
        flow.checkpoint("guard_checks_complete")
    except CommandGuardError as exc:
        flow.complete("guard_check_failed")
        error_embed = create_command_guard_error_embed(exc)
        await send_ephemeral_response(interaction, embed=error_embed)
        return
    
    # Defer the response since this might take a while
    flow.checkpoint("response_start")
    # Removed defer() - system is now fast enough that Discord's loading indicator provides better UX
    flow.checkpoint("response_complete")
    
    # Get the channel (DM-only enforced by centralized system)
    channel = interaction.channel
    
    # Debug: Log current time and protected messages
    print(f"[Prune Debug] Current time: {datetime.now(timezone.utc)}")
    print(f"[Prune Debug] Bot user ID: {interaction.client.user.id}")
    print(f"[Prune Debug] Protected queue messages: {len(_active_queue_message_ids)}")
    
    flow.checkpoint("fetch_messages_start")
    
    # Fetch messages to delete
    messages_to_delete: List[discord.Message] = []
    bot_user_id = interaction.client.user.id
    
    try:
        # Fetch up to 100 messages (Discord limit)
        total_messages = 0
        bot_messages = 0
        too_new = 0
        protected = 0
        
        async for message in channel.history(limit=100):
            total_messages += 1
            
            # Only consider bot's own messages
            if message.author.id != bot_user_id:
                continue
            
            bot_messages += 1
            
            # Skip if message is associated with an active queue view (legacy protection)
            if message.id in _active_queue_message_ids:
                protected += 1
                print(f"[Prune Debug] Message protected (legacy queue): {message.id}")
                continue
            
            # Skip if message contains prune-related content (protect prune command messages)
            if is_prune_related_message(message):
                protected += 1
                print(f"[Prune Debug] Message protected (prune command): {message.id}")
                print(f"[Prune Debug] - Title: {message.embeds[0].title if message.embeds else 'No embeds'}")
                print(f"[Prune Debug] - Description: {message.embeds[0].description[:100] if message.embeds and message.embeds[0].description else 'No description'}")
                continue
            
            # Skip very recent messages (within configured protection period) as they might be prune-related
            recent_cutoff = datetime.now(timezone.utc) - timedelta(minutes=RECENT_MESSAGE_PROTECTION_MINUTES)
            if message.created_at > recent_cutoff:
                protected += 1
                print(f"[Prune Debug] Message protected (recent message): {message.id} (created: {message.created_at})")
                continue
            
            # Skip if message contains queue-related content (programmatic detection)
            # Only protects queue messages less than the configured protection period
            if is_queue_related_message(message):
                protected += 1
                print(f"[Prune Debug] Message protected (queue content < {QUEUE_MESSAGE_PROTECTION_DAYS} days): {message.id}")
                continue
            
            messages_to_delete.append(message)
            print(f"[Prune Debug] Message queued for deletion: {message.id} (created: {message.created_at})")
        
        # Debug summary
        print(f"[Prune Debug] Summary:")
        print(f"  - Total messages fetched: {total_messages}")
        print(f"  - Bot messages: {bot_messages}")
        print(f"  - Protected (queue): {protected}")
        print(f"  - Queued for deletion: {len(messages_to_delete)}")
    
    except discord.Forbidden:
        error_embed = discord.Embed(
            title="❌ Permission Error",
            description="I don't have permission to read message history in this channel.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed, ephemeral=False)
        flow.complete("permission_error")
        return
    except discord.HTTPException as e:
        error_embed = discord.Embed(
            title="❌ Error",
            description=f"Failed to fetch messages: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed, ephemeral=False)
        flow.complete("fetch_error")
        return
    
    flow.checkpoint("fetch_messages_complete")
    
    # If no messages to delete
    if not messages_to_delete:
        info_embed = discord.Embed(
            title="✅ No Messages to Prune",
            description="No bot messages found that can be safely deleted.\n\nQueue-related messages less than a week old are automatically protected.",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=info_embed, ephemeral=False)
        flow.complete("no_messages")
        return
    
    # Show confirmation prompt with message details
    oldest_message = messages_to_delete[-1]  # Last in list is oldest
    newest_message = messages_to_delete[0]   # First in list is newest
    
    # Create confirmation embed
    confirm_embed = discord.Embed(
        title="🗑️ Confirm Message Deletion",
        description=f"**{len(messages_to_delete)} message(s)** will be deleted.\n\n"
                   f"Queue-related messages less than a week old are automatically protected from deletion.",
        color=discord.Color.orange()
    )
    
    # Add message links
    confirm_embed.add_field(
        name="📅 Oldest Message",
        value=f"[Jump to message]({oldest_message.jump_url})\n"
              f"Created: <t:{int(oldest_message.created_at.timestamp())}:R>",
        inline=True
    )
    confirm_embed.add_field(
        name="📅 Newest Message",
        value=f"[Jump to message]({newest_message.jump_url})\n"
              f"Created: <t:{int(newest_message.created_at.timestamp())}:R>",
        inline=True
    )
    
    # Estimated deletion time
    estimated_time = int(len(messages_to_delete) * PRUNE_DELETE_DELAY_SECONDS)
    
    confirm_embed.add_field(
        name="⏱️ Estimated Time",
        value=f"~{estimated_time} seconds",
        inline=False
    )
    
    # Create confirmation view with buttons
    confirm_view = discord.ui.View(timeout=GLOBAL_TIMEOUT)
    
    # Define the confirm callback
    async def confirm_deletion(confirm_interaction: discord.Interaction):
        # Removed defer() - system is now fast enough that Discord's loading indicator provides better UX
        
        # Show progress embed immediately
        progress_embed = discord.Embed(
            title="🗑️ Pruning in Progress...",
            description=f"Deleting {len(messages_to_delete)} old message(s).\n\n"
                       f"*This may take up to {estimated_time} seconds "
                       f"to avoid Discord rate limits.*",
            color=discord.Color.blue()
        )
        await confirm_interaction.edit_original_response(embed=progress_embed, view=None)
        
        # Delete messages with rate limit handling
        flow.checkpoint("delete_messages_start")
        deleted_count = 0
        failed_count = 0
        
        for i, message in enumerate(messages_to_delete):
            try:
                await message.delete()
                deleted_count += 1
                
                # Add delay between deletions (except after the last one)
                if i < len(messages_to_delete) - 1:
                    await asyncio.sleep(PRUNE_DELETE_DELAY_SECONDS)
                    
            except discord.NotFound:
                # Message already deleted
                failed_count += 1
            except discord.Forbidden:
                # No permission to delete this message
                failed_count += 1
            except discord.HTTPException as e:
                # Check if it's a rate limit error (shouldn't happen with our delays, but just in case)
                if e.status == 429:
                    # Rate limited - wait longer
                    retry_after = e.retry_after if hasattr(e, 'retry_after') else 2.0
                    print(f"[Prune] Rate limited, waiting {retry_after}s before retrying...")
                    await asyncio.sleep(retry_after)
                    # Retry this message
                    try:
                        await message.delete()
                        deleted_count += 1
                    except Exception:
                        failed_count += 1
                else:
                    # Other HTTP error
                    failed_count += 1
        
        flow.checkpoint("delete_messages_complete")
        
        # Send success message
        if deleted_count > 0:
            success_embed = discord.Embed(
                title="✅ Messages Pruned",
                description=f"Successfully deleted {deleted_count} old bot message(s).",
                color=discord.Color.green()
            )
            if failed_count > 0:
                success_embed.add_field(
                    name="⚠️ Failed to Delete",
                    value=f"{failed_count} message(s) could not be deleted.",
                    inline=False
                )
            await confirm_interaction.edit_original_response(embed=success_embed, view=None)
            flow.complete("success")
        else:
            error_embed = discord.Embed(
                title="❌ Failed to Prune",
                description=f"Could not delete any messages. {failed_count} deletion(s) failed.",
                color=discord.Color.red()
            )
            await confirm_interaction.edit_original_response(embed=error_embed, view=None)
            flow.complete("all_failed")
    
    # Create a dummy view for cancel button (required by ConfirmRestartCancelButtons)
    class PruneCancelView:
        """Dummy view to satisfy ConfirmRestartCancelButtons requirements"""
        pass
    
    cancel_target = PruneCancelView()
    
    # Add confirm and cancel buttons
    buttons = ConfirmRestartCancelButtons.create_buttons(
        confirm_callback=confirm_deletion,
        reset_target=cancel_target,  # Dummy target for cancel
        include_confirm=True,
        include_restart=False,
        include_cancel=True
    )
    
    for button in buttons:
        confirm_view.add_item(button)
    
    # Send confirmation prompt
    await interaction.followup.send(embed=confirm_embed, view=confirm_view, ephemeral=False)
    flow.complete("awaiting_confirmation")

