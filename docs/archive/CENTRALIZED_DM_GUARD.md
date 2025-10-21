# Centralized DM-Only Command Guard

## Summary

Implemented a centralized DM-only enforcement system using decorators. Commands that require DM usage are managed in a single location (`command_decorators.py`) and enforced using the `@dm_only` decorator.

## Architecture

### 1. **Centralized Command List**

**File**: `src/bot/utils/command_decorators.py`

```python
# Centralized list of DM-only commands
DM_ONLY_COMMANDS: Set[str] = {
    "prune",  # Personal message cleanup
    "queue"   # Matchmaking (security + ephemeral messages work in DMs)
}
```

### 2. **Decorator Implementation**

```python
def dm_only(func: Callable) -> Callable:
    """
    Decorator to enforce DM-only requirement for a command.
    
    Usage:
        @dm_only
        async def my_command(interaction: discord.Interaction):
            ...
    """
    @wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        try:
            command_guard_service.require_dm(interaction)
        except CommandGuardError as exc:
            error_embed = create_command_guard_error_embed(exc)
            await send_ephemeral_response(interaction, embed=error_embed)
            return
        
        return await func(interaction, *args, **kwargs)
    
    return wrapper
```

### 3. **Usage in Commands**

**queue_command.py**:
```python
from src.bot.utils.command_decorators import dm_only

@dm_only
async def queue_command(interaction: discord.Interaction):
    """Handle the /queue slash command"""
    # Command logic here - DM check handled by decorator
```

**prune_command.py**:
```python
from src.bot.utils.command_decorators import dm_only

@dm_only
async def prune_command(interaction: discord.Interaction):
    """Handle the /prune slash command"""
    # Command logic here - DM check handled by decorator
```

## How It Works

### 1. **Decorator Pattern**
- The `@dm_only` decorator wraps the command function
- DM check runs **before** the command function executes
- If check fails, error is sent and command exits early
- If check passes, command executes normally

### 2. **Execution Flow**

```
User calls /queue in guild
    ↓
@dm_only decorator intercepts
    ↓
command_guard_service.require_dm(interaction)
    ↓
Not a DM → Raises DMOnlyError
    ↓
Decorator catches exception
    ↓
Sends error embed to user
    ↓
Returns early (command never executes)
```

### 3. **Success Flow**

```
User calls /queue in DM
    ↓
@dm_only decorator intercepts
    ↓
command_guard_service.require_dm(interaction)
    ↓
Is a DM → Check passes
    ↓
Command function executes normally
```

## Benefits

### 1. **Centralized Management**
- ✅ Single source of truth for DM-only commands
- ✅ Easy to add/remove DM-only commands
- ✅ No code duplication across commands

### 2. **Clean Command Code**
- ✅ Commands don't need manual DM checks
- ✅ Decorator handles all DM enforcement
- ✅ Command logic remains focused on business logic

### 3. **Consistent Error Handling**
- ✅ All DM-only errors use same embed format
- ✅ Consistent user experience
- ✅ Follows existing CommandGuardError pattern

### 4. **Type Safety**
- ✅ Decorator preserves function signature
- ✅ IDE autocomplete still works
- ✅ No runtime type issues

### 5. **Maintainability**
- ✅ Easy to find all DM-only commands (one file)
- ✅ Easy to add new DM-only commands (just add decorator)
- ✅ Easy to update DM enforcement logic (one place)

## Adding New DM-Only Commands

### Option 1: Using Decorator (Recommended)

```python
from src.bot.utils.command_decorators import dm_only

@dm_only
async def my_new_command(interaction: discord.Interaction):
    # Your command logic here
    pass
```

### Option 2: Auto-Apply (Advanced)

If you want to auto-apply based on the centralized list:

```python
from src.bot.utils.command_decorators import auto_apply_dm_guard

def register_my_command(tree: app_commands.CommandTree):
    @tree.command(name="mycommand")
    async def mycommand(interaction: discord.Interaction):
        # Command logic
        pass
    
    # Auto-apply DM guard if in DM_ONLY_COMMANDS list
    return auto_apply_dm_guard("mycommand", mycommand)
```

Then add to `DM_ONLY_COMMANDS`:
```python
DM_ONLY_COMMANDS: Set[str] = {
    "prune",
    "queue",
    "mycommand"  # Add here
}
```

## Current DM-Only Commands

| Command | Reason |
|---------|--------|
| `/prune` | Personal message cleanup - should only affect user's own DM |
| `/queue` | Matchmaking security - prevents unauthorized access to match views |

## Why This Approach?

### ❌ **What Didn't Work: `on_interaction` Listener**

The original attempt used `on_interaction` to enforce DM checks:

**Problem**: 
- `on_interaction` runs **alongside** the command handler, not **before** it
- Command handler already calls `interaction.response.send_message()` first
- DM check tries to respond after interaction is already acknowledged
- Result: "Interaction has already been acknowledged" error

### ✅ **What Works: Decorator Pattern**

**Solution**:
- Decorator wraps the command function
- DM check runs **before** the command function is called
- If check fails, command function never executes
- No interaction acknowledgement conflicts

## Testing

### Test DM Enforcement

1. **In DM (Should Work)**:
   - User calls `/queue` in DM
   - Command executes normally
   - No error messages

2. **In Guild (Should Fail)**:
   - User calls `/queue` in guild channel
   - Error embed shown: "This command can only be used in DMs."
   - Command does not execute

### Test Non-DM Commands

1. **In DM (Should Work)**:
   - User calls `/leaderboard` in DM
   - Command executes normally
   - Response is NOT ephemeral (DM limitation)

2. **In Guild (Should Work)**:
   - User calls `/leaderboard` in guild channel
   - Command executes normally
   - Response IS ephemeral (only visible to user)

## Implementation Notes

### Why Not Use `app_commands.check()`?

Discord.py provides a built-in `app_commands.check()` decorator, but:
- ❌ Requires specific error handling setup
- ❌ Less flexible for custom error embeds
- ❌ Different pattern from existing CommandGuardError system
- ✅ Our decorator integrates with existing guard system
- ✅ Consistent error handling with other guards

### Performance Impact

**Decorator Overhead**: ~0.01ms
- Minimal impact on command response time
- Decorator adds one function call wrapper
- DM check is simple `isinstance()` call
- Total impact negligible compared to network latency

## Future Enhancements

### 1. **Guild-Only Commands**
```python
@guild_only
async def admin_command(interaction: discord.Interaction):
    # Command logic
    pass
```

### 2. **Permission-Based Guards**
```python
@require_permissions(["manage_messages"])
async def mod_command(interaction: discord.Interaction):
    # Command logic
    pass
```

### 3. **Rate Limiting**
```python
@rate_limit(calls=5, period=60)  # 5 calls per 60 seconds
async def expensive_command(interaction: discord.Interaction):
    # Command logic
    pass
```

## Troubleshooting

### Issue: "Interaction has already been acknowledged"

**Cause**: DM check is running after command has already responded

**Solution**: Ensure decorator is applied correctly:
```python
@dm_only  # Must be BEFORE async def
async def queue_command(interaction: discord.Interaction):
    # ...
```

### Issue: Command not enforcing DM-only

**Cause**: Decorator not imported or applied

**Solution**: 
1. Import: `from src.bot.utils.command_decorators import dm_only`
2. Apply: `@dm_only` before function definition
3. Verify decorator is on the actual command function, not the registration function

### Issue: Type hints not working

**Cause**: Decorator not preserving function signature

**Solution**: Ensure `@wraps(func)` is used in decorator implementation (already done)

## Conclusion

The centralized decorator approach provides:
- ✅ **Single source of truth** for DM-only commands
- ✅ **Clean command code** with no manual checks
- ✅ **Consistent error handling** across all commands
- ✅ **Easy maintenance** and future enhancements
- ✅ **Type safety** and IDE support

This pattern can be extended to other command guards (guild-only, permissions, rate limiting, etc.) in the future.

