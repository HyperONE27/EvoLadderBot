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
from src.bot.config import GLOBAL_TIMEOUT
from src.backend.services.performance_service import FlowTracker


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


def register_prune_command(tree: app_commands.CommandTree):
    """Register the prune command"""
    @tree.command(
        name="prune",
        description=f"Delete old bot messages (older than {GLOBAL_TIMEOUT/60} minutes) to reduce lag"
    )
    async def prune(interaction: discord.Interaction):
        await prune_command(interaction)
    
    return prune


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
    flow.checkpoint("defer_response_start")
    await interaction.response.defer(ephemeral=True)
    flow.checkpoint("defer_response_complete")
    
    # Calculate cutoff time
    cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=GLOBAL_TIMEOUT)
    
    # Get the channel (can be DM or guild)
    channel = interaction.channel
    
    # Debug: Log cutoff time and current time
    print(f"[Prune Debug] Current time: {datetime.now(timezone.utc)}")
    print(f"[Prune Debug] Cutoff time: {cutoff_time}")
    print(f"[Prune Debug] GLOBAL_TIMEOUT: {GLOBAL_TIMEOUT} seconds")
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
            
            # Skip if message is newer than cutoff
            if message.created_at > cutoff_time:
                too_new += 1
                print(f"[Prune Debug] Message too new: {message.created_at} > {cutoff_time}")
                continue
            
            # Skip if message is associated with an active queue view
            if message.id in _active_queue_message_ids:
                protected += 1
                print(f"[Prune Debug] Message protected (queue): {message.id}")
                continue
            
            messages_to_delete.append(message)
            print(f"[Prune Debug] Message queued for deletion: {message.id} (created: {message.created_at})")
        
        # Debug summary
        print(f"[Prune Debug] Summary:")
        print(f"  - Total messages fetched: {total_messages}")
        print(f"  - Bot messages: {bot_messages}")
        print(f"  - Too new (< {GLOBAL_TIMEOUT}s): {too_new}")
        print(f"  - Protected (queue): {protected}")
        print(f"  - Queued for deletion: {len(messages_to_delete)}")
    
    except discord.Forbidden:
        error_embed = discord.Embed(
            title="❌ Permission Error",
            description="I don't have permission to read message history in this channel.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)
        flow.complete("permission_error")
        return
    except discord.HTTPException as e:
        error_embed = discord.Embed(
            title="❌ Error",
            description=f"Failed to fetch messages: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)
        flow.complete("fetch_error")
        return
    
    flow.checkpoint("fetch_messages_complete")
    
    # If no messages to delete
    if not messages_to_delete:
        info_embed = discord.Embed(
            title="✅ No Messages to Prune",
            description=f"No bot messages older than {GLOBAL_TIMEOUT} seconds found.",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=info_embed, ephemeral=True)
        flow.complete("no_messages")
        return
    
    # Delete messages with rate limit handling
    flow.checkpoint("delete_messages_start")
    deleted_count = 0
    failed_count = 0
    
    # Add delay between deletions to avoid rate limiting
    # Discord rate limit: ~5 deletions per second for DM messages
    DELAY_BETWEEN_DELETES = 0.5  # 500ms delay = ~2 deletions/sec (safe margin)
    
    # Notify user that pruning is in progress (especially for many messages)
    if len(messages_to_delete) > 10:
        estimated_time = int(len(messages_to_delete) * DELAY_BETWEEN_DELETES)
        progress_embed = discord.Embed(
            title="🗑️ Pruning in Progress...",
            description=f"Deleting {len(messages_to_delete)} old message(s).\n\n"
                       f"*This may take up to {estimated_time} seconds "
                       f"to avoid Discord rate limits.*",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=progress_embed, ephemeral=True)
    
    for i, message in enumerate(messages_to_delete):
        try:
            await message.delete()
            deleted_count += 1
            
            # Add delay between deletions (except after the last one)
            if i < len(messages_to_delete) - 1:
                await asyncio.sleep(DELAY_BETWEEN_DELETES)
                
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
        await interaction.followup.send(embed=success_embed, ephemeral=True)
        flow.complete("success")
    else:
        error_embed = discord.Embed(
            title="❌ Failed to Prune",
            description=f"Could not delete any messages. {failed_count} deletion(s) failed.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)
        flow.complete("all_failed")

