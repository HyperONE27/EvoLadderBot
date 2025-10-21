# Prune Command Documentation

## Overview

The `/prune` command allows users to delete old bot messages in their DM channel to reduce Discord client lag caused by accumulated embeds and views.

## Purpose

### Problem
- Leaderboard and other bot commands create rich embeds with many Discord components
- These messages accumulate over time in DM channels
- Discord's client becomes laggy when rendering many old embeds
- **Performance bottleneck**: Not the API (which is fast), but the Discord client UI rendering all the old messages

### Solution
- `/prune` command deletes old bot messages
- Only deletes messages older than `GLOBAL_TIMEOUT` (default: 180 seconds)
- **Protects active queue views** from deletion (safety measure)
- Reduces Discord client lag significantly

## Usage

```
/prune
```

### Requirements
- Must be used in a DM channel (not in servers)
- User must have accepted Terms of Service
- Bot must have permission to read and delete messages

### Behavior

1. **Fetches** up to 100 bot messages in the channel
2. **Filters** messages that are:
   - Sent by the bot
   - Older than `GLOBAL_TIMEOUT` seconds
   - NOT associated with active queue views
3. **Deletes** filtered messages
4. **Reports** results (success/failure count)

## Safety Features

### Protected Messages
Messages associated with **active queue views** are NOT deleted. This prevents:
- Losing ongoing match information
- Breaking queue UI while users are in matchmaking
- Deleting messages with active replay upload views

### How Protection Works

1. **Registration**: When a queue view is created, its message ID is registered
   ```python
   from src.bot.commands.prune_command import register_active_queue_message
   
   register_active_queue_message(message.id)
   ```

2. **Unregistration**: When a queue view times out or completes, its message ID is unregistered
   ```python
   from src.bot.commands.prune_command import unregister_active_queue_message
   
   unregister_active_queue_message(message.id)
   ```

3. **Protection**: `/prune` skips any message ID in the protected set

### Integration with Queue Command

To integrate with the queue command, add these calls:

```python
# In queue_command.py or wherever QueueView is created
from src.bot.commands.prune_command import (
    register_active_queue_message,
    unregister_active_queue_message
)

class QueueView(discord.ui.View):
    def __init__(self, ...):
        super().__init__(timeout=GLOBAL_TIMEOUT)
        self.message_id = None
        # ... rest of init
    
    async def on_message_sent(self, message: discord.Message):
        """Called after the view's message is sent"""
        self.message_id = message.id
        register_active_queue_message(message.id)
    
    async def on_timeout(self):
        """Called when the view times out"""
        if self.message_id:
            unregister_active_queue_message(self.message_id)
        # ... rest of timeout handling
    
    async def on_match_complete(self):
        """Called when the match completes"""
        if self.message_id:
            unregister_active_queue_message(self.message_id)
        # ... rest of completion handling
```

## Response Messages

### Success
```
✅ Messages Pruned
Successfully deleted 15 old bot message(s).
```

### Partial Success
```
✅ Messages Pruned
Successfully deleted 12 old bot message(s).

⚠️ Failed to Delete
3 message(s) could not be deleted.
```

### No Messages
```
✅ No Messages to Prune
No bot messages older than 180 seconds found.
```

### Error: Not in DM
```
❌ Error
This command can only be used in DMs.
```

### Error: Permission
```
❌ Permission Error
I don't have permission to read message history in this channel.
```

## Performance Impact

### Discord Client Lag
**Before /prune:**
- Discord client renders all accumulated embeds
- Scrolling becomes laggy
- UI responsiveness degrades over time
- Can feel "sluggish" even though API calls are fast

**After /prune:**
- Only recent messages remain
- Discord client is responsive
- Smooth scrolling and UI interactions
- Feels "snappy" again

### Bot Performance
- **Fetching messages**: ~50-200ms (depends on message count)
- **Deleting messages**: ~750ms per message (with rate limit protection)
- **Total time**: ~7.5s-37.5s (for 10-50 messages)
- Uses `defer()` so user isn't waiting for immediate response

### Rate Limit Handling
To avoid Discord's rate limits, the command:
- **Delays 750ms between each deletion** (~1.3 deletions/second)
- **Automatically retries** if rate limited (with exponential backoff)
- **Shows progress message** for 10+ messages to set expectations
- **Safe margin**: Discord allows ~5 deletions/sec, we do ~1.3/sec

**Example timing:**
- 10 messages: ~7.5 seconds
- 20 messages: ~15 seconds  
- 50 messages: ~37.5 seconds

This is **intentionally slow** to respect Discord's rate limits and avoid 429 errors.

## Limitations

### Discord API Limits
1. **History limit**: Can only fetch last 100 messages
2. **Rate limiting**: Deleting many messages may hit rate limits
3. **Message age**: Messages older than 14 days can't be bulk deleted (but we delete one-by-one so this doesn't affect us)

### Permission Requirements
- Bot needs `READ_MESSAGE_HISTORY` permission
- Bot needs `MANAGE_MESSAGES` or message must be bot's own (we only delete bot's messages)

### Not Deleted
- Messages newer than `GLOBAL_TIMEOUT`
- Messages from other users
- Messages associated with active queue views
- Messages the bot doesn't have permission to delete

## Best Practices

### When to Use
- Discord client feels laggy
- Many old leaderboard messages accumulated
- Before a long session of bot usage
- Periodically (e.g., once per day)

### When NOT to Use
- While actively in queue (protected anyway, but still)
- While viewing recent leaderboard pages (they'll be deleted)
- If you want to keep message history

### Frequency
- **Recommended**: Run `/prune` when Discord feels laggy
- **Not recommended**: Running constantly (unnecessary API calls)
- **Protected**: Even if run frequently, active queue views are safe

## Implementation Details

### Module: `src/bot/commands/prune_command.py`

**Key Functions:**
- `prune_command(interaction)` - Main command handler
- `register_active_queue_message(message_id)` - Protect a message
- `unregister_active_queue_message(message_id)` - Unprotect a message

**Protected Message IDs:**
- Stored in module-level set: `_active_queue_message_ids`
- Thread-safe for Discord's async environment
- Automatically checked during pruning

### Performance Tracking
Uses `FlowTracker` to monitor:
- Guard checks
- Message fetching
- Message deletion
- Total command duration

### Rate Limit Implementation
```python
# Discord rate limit: ~5 deletions per second for DM messages
DELAY_BETWEEN_DELETES = 0.75  # 750ms delay = ~1.3 deletions/sec (safe margin)

for i, message in enumerate(messages_to_delete):
    try:
        await message.delete()
        deleted_count += 1
        
        # Add delay between deletions (except after the last one)
        if i < len(messages_to_delete) - 1:
            await asyncio.sleep(DELAY_BETWEEN_DELETES)
            
    except discord.HTTPException as e:
        # Handle rate limit errors with automatic retry
        if e.status == 429:
            retry_after = e.retry_after if hasattr(e, 'retry_after') else 2.0
            print(f"[Prune] Rate limited, waiting {retry_after}s before retrying...")
            await asyncio.sleep(retry_after)
            # Retry this message
            try:
                await message.delete()
                deleted_count += 1
            except Exception:
                failed_count += 1
```

**Key features:**
- **750ms delay** between deletions prevents rate limits
- **Automatic retry** with exponential backoff if rate limited
- **Graceful degradation** - continues even if some deletions fail
- **Progress notification** for large batches (10+ messages)

## Future Enhancements

### Automatic Pruning
- Background task that auto-prunes every N minutes
- Configurable auto-prune threshold
- Per-user opt-in/opt-out

### Selective Pruning
- `/prune leaderboard` - Only delete leaderboard messages
- `/prune profile` - Only delete profile messages
- `/prune all` - Delete all old bot messages (current behavior)

### Age-Based Pruning
- `/prune 300` - Delete messages older than 300 seconds
- `/prune 1h` - Delete messages older than 1 hour
- `/prune 1d` - Delete messages older than 1 day

### Statistics
- Show how many messages of each type would be deleted
- Confirm before deleting (optional)
- Report which message types were deleted

## Conclusion

The `/prune` command addresses **Discord client lag** (UI rendering old embeds) rather than **API response time** (which is out of our control). This is the most effective way to improve the user's perceived performance of the bot.

**Key Benefit**: Users can now "clean up" their DM channel to keep Discord responsive, without risking deletion of active queue/match information.

