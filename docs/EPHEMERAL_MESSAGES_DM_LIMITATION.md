# Ephemeral Messages: DM Limitation

## TL;DR

**Ephemeral messages don't work in DMs.** They're a Discord feature exclusively for guilds/servers. Since our bot enforces DM-only commands, ephemeral has no effect. Use `/prune` instead to clean up old messages.

## What Happened

We attempted to make all bot messages ephemeral (except `/queue`) to reduce clutter in DM channels. However, after implementation, **nothing became ephemeral**.

## Root Cause: Discord Limitation

### How Ephemeral Works in Discord

**In Guilds (Servers):**
- Multiple users can see channel messages
- Ephemeral = message visible only to command user
- Useful for private responses in public channels
- **Works as expected** ✅

**In DMs:**
- Only 2 parties: user + bot
- Ephemeral has no effect (everyone already sees everything)
- Message is always visible to both parties
- **Ephemeral parameter is ignored** ⚠️

### Our Bot Architecture

```python
# bot_setup.py
DM_ONLY_COMMANDS = {
    "activate",
    "setup", 
    "setcountry",
    "termsofservice",
    "profile",
    "leaderboard",
    "prune",
    "queue"
}
```

**All commands require DMs**, so ephemeral can never work for us.

## Why We Use DMs

1. **Privacy**: Setup, profile, activation codes are private
2. **Less spam**: Matchmaking notifications don't clutter servers
3. **User experience**: Focused 1-on-1 interaction
4. **No permissions needed**: Works without server management perms

## The Actual Solution: `/prune`

Since ephemeral doesn't work in DMs, we use `/prune` to clean up old messages:

```
/prune
```

**What it does:**
- Deletes bot messages older than 180 seconds
- Protects active queue views
- Rate-limited to respect Discord API (750ms per message)
- Reduces Discord client lag from accumulated embeds

**When to use:**
- Discord client feels laggy
- Many old leaderboard/profile messages
- After multiple matchmaking sessions
- Periodically (e.g., once per day)

## Alternatives Considered

### 1. Move Commands to Guild/Server
**Rejected** because:
- Loses privacy for sensitive commands (/activate, /setup)
- Requires server management permissions
- Creates spam in public channels
- Goes against bot's design philosophy

### 2. Auto-Delete Messages After Timeout
**Rejected** because:
- Discord doesn't allow bots to auto-delete their own messages after N seconds in DMs
- Would break queue flow (messages disappear mid-match)
- Users lose context/history
- Can't be selective (would delete everything)

### 3. Use Followup Messages
**No benefit** because:
- Followup messages are also not ephemeral in DMs
- Same limitation applies
- Adds complexity without solving the problem

### 4. Background Auto-Prune Task
**Possible future enhancement:**
- Bot periodically prunes old messages (every 5 minutes)
- Transparent to user
- Keeps DM channel clean
- **Trade-off**: Users lose message history

## Current Implementation Status

### Changes Reverted? NO

We're **keeping `ephemeral=True`** in the code even though it doesn't work in DMs because:

1. **Future-proofing**: If we ever add guild support, it'll work automatically
2. **Documentation**: Shows intent that these should be temporary messages
3. **No harm**: Parameter is ignored in DMs, doesn't cause errors
4. **Best practice**: Signals to other developers these are non-persistent interactions

### Files with `ephemeral=True`

- `activate_command.py`
- `setup_command.py`
- `termsofservice_command.py`
- `setcountry_command.py`
- `leaderboard_command.py`
- `profile_command.py`
- `prune_command.py`

**Effect in DMs**: None (ignored by Discord)
**Effect in Guilds**: Would work if we ever support guilds

## Recommendation

### For Users
**Use `/prune` regularly** to clean up old bot messages and reduce Discord client lag.

```
/prune  (every time Discord feels sluggish)
```

### For Developers
**Keep `ephemeral=True` in code** for:
- Documentation purposes
- Future guild support
- Best practice signaling
- No downside in DMs

### Future Enhancement: Background Auto-Prune

Add optional background task that automatically prunes messages:

```python
# In bot_setup.py
async def _auto_prune_task(self):
    """Background task that auto-prunes old messages every 5 minutes"""
    await self.wait_until_ready()
    
    while not self.is_closed():
        try:
            # Prune messages older than 5 minutes for all active DM channels
            # Skip if user has opted out
            # Skip active queue messages
            pass
        except Exception as e:
            logger.error(f"Auto-prune error: {e}")
        
        await asyncio.sleep(300)  # 5 minutes
```

**Trade-offs:**
- ✅ Keeps DMs clean automatically
- ✅ No user action needed
- ❌ Users lose message history
- ❌ More API calls (rate limit risk)
- ❌ Requires opt-in/opt-out system

## Lessons Learned

1. **Ephemeral is guild-only** - DMs don't support it
2. **DM-only bots need manual cleanup** - `/prune` is the solution
3. **Discord limitations are real** - Can't always solve problems with code
4. **User education matters** - Users need to know about `/prune`

## Documentation Updates

- ✅ Created `EPHEMERAL_MESSAGES_DM_LIMITATION.md` (this file)
- ⚠️ Update `EPHEMERAL_MESSAGES_UPDATE.md` to note DM limitation
- ⚠️ Update bot help/documentation to emphasize `/prune` usage
- ⚠️ Consider adding auto-prune task in future

## References

- Discord.py Documentation: [Ephemeral Messages](https://discordpy.readthedocs.io/en/stable/interactions/api.html#discord.InteractionResponse.send_message)
- Discord API: Ephemeral is a guild-only feature
- Our Implementation: `/prune` command for DM cleanup

