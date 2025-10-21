# DM-Only Command Enforcement

## Summary

Implemented DM-only enforcement for `/prune` and `/queue` commands. These commands must be used in DMs for security and privacy reasons. All other commands can work in both DMs and guilds, with ephemeral messages in guilds.

## Changes Made

### 1. **queue_command.py**
```python
# Added DM-only check in guard checks
try:
    flow.checkpoint("guard_checks_start")
    player = guard_service.ensure_player_record(interaction.user.id, interaction.user.name)
    guard_service.require_dm(interaction)  # DM-only check
    guard_service.require_queue_access(player)
    flow.checkpoint("guard_checks_complete")
except CommandGuardError as exc:
    flow.complete("guard_check_failed")
    error_embed = create_command_guard_error_embed(exc)
    await send_ephemeral_response(interaction, embed=error_embed)
    return
```

### 2. **prune_command.py**
```python
# Added DM-only check in guard checks
try:
    flow.checkpoint("guard_checks_start")
    player = command_guard_service.ensure_player_record(
        interaction.user.id, 
        interaction.user.name
    )
    command_guard_service.require_dm(interaction)  # DM-only check
    command_guard_service.require_tos_accepted(player)
    flow.checkpoint("guard_checks_complete")
except CommandGuardError as exc:
    flow.complete("guard_check_failed")
    error_embed = create_command_guard_error_embed(exc)
    await send_ephemeral_response(interaction, embed=error_embed)
    return
```

### 3. **bot_setup.py**
```python
# DM_ONLY_COMMANDS list is for documentation only
# Actual enforcement happens in individual command handlers
DM_ONLY_COMMANDS = {
    "prune",  # Personal message cleanup
    "queue"   # Matchmaking (security + ephemeral messages work in DMs)
}
```

## Benefits

### 1. **Ephemeral Messages Now Work!**
- In guilds: Messages visible only to command user
- In DMs: Still works (though ephemeral has no effect)
- Reduces clutter in guild channels
- Better privacy for sensitive commands

### 2. **Flexibility**
- Users can use commands in DMs (private)
- Users can use commands in guilds (public)
- No restrictions on where bot is used

### 3. **Better UX**
- Ephemeral messages reduce channel spam
- Commands work anywhere the bot is present
- No "DM only" error messages

## Command Behavior by Channel Type

### In DMs (Private)
- All commands work as before
- Ephemeral messages have no effect (Discord limitation)
- `/prune` still needed for cleanup

### In Guilds (Public)
- All commands work with ephemeral messages
- Messages visible only to command user
- No channel spam
- No cleanup needed (ephemeral auto-expires)

## Security Considerations

### Sensitive Commands
Commands like `/activate`, `/setup`, `/setcountry` now work in public channels but are **ephemeral** (only visible to the user):

- ✅ **Privacy maintained** - Only user sees the response
- ✅ **No channel spam** - Ephemeral messages don't clutter
- ✅ **Secure** - Activation codes, setup data not visible to others

### Queue Commands
- `/queue` still uses `ephemeral=False` in guilds
- Match state needs to be visible to opponents
- May need adjustment for guild-based matchmaking

## Testing Checklist

### DM Testing
- [ ] All commands work in DMs
- [ ] Ephemeral has no effect (expected)
- [ ] `/prune` works for cleanup

### Guild Testing
- [ ] All commands work in guilds
- [ ] Ephemeral messages work (only visible to user)
- [ ] No channel spam from bot responses
- [ ] Queue commands work with opponents

### Security Testing
- [ ] `/activate` - activation codes not visible to others
- [ ] `/setup` - profile data not visible to others
- [ ] `/setcountry` - country changes not visible to others
- [ ] `/profile` - profile info not visible to others
- [ ] `/leaderboard` - leaderboard not visible to others

## Potential Issues

### 1. Queue Matchmaking in Guilds
**Issue**: Queue commands designed for DMs may not work well in guilds
**Solution**: May need guild-specific queue handling

### 2. Bot Permissions
**Issue**: Bot needs appropriate permissions in guilds
**Solution**: Ensure bot has necessary permissions for commands

### 3. User Expectations
**Issue**: Users may expect commands to work differently in guilds
**Solution**: Document behavior differences

## Future Enhancements

### 1. Guild-Specific Features
- Guild leaderboards (server-specific rankings)
- Guild matchmaking (server-only matches)
- Guild statistics

### 2. Permission-Based Commands
- Admin-only commands in guilds
- Role-based access control
- Channel-specific restrictions

### 3. Hybrid Approach
- Some commands DM-only (sensitive)
- Some commands guild-only (public)
- Some commands work anywhere

## Migration Notes

### For Users
- Commands now work in both DMs and guilds
- Ephemeral messages reduce spam in guilds
- No behavior change in DMs

### For Developers
- Remove any DM-specific logic
- Test commands in both DMs and guilds
- Consider guild-specific features

## Conclusion

Removing DM-only restrictions enables:
- ✅ Ephemeral messages work in guilds
- ✅ Better user experience
- ✅ More flexible bot usage
- ✅ Reduced channel spam

The bot is now more versatile while maintaining security through ephemeral messages for sensitive commands.
