# Admin Commands Final Refactoring

## Summary

Complete refactoring of admin commands based on user feedback:
1. ✅ Simplified admin verification (no separate module)
2. ✅ Admin commands work in any channel (exempt from DMs-only rule)
3. ✅ All components start with "Admin" prefix
4. ✅ All interactions restricted to admins only

## Changes Made

### 1. Simplified Admin Verification

**Before**: Separate `admin_loader_service.py` module with singleton pattern

**After**: Simple function directly in `admin_command.py`:

```python
# Load admin IDs from admins.json (at module import)
def _load_admin_ids() -> Set[int]:
    try:
        with open('data/misc/admins.json', 'r', encoding='utf-8') as f:
            admins_data = json.load(f)
        return {admin['discord_id'] for admin in admins_data if 'discord_id' in admin}
    except Exception as e:
        print(f"[AdminCommands] ERROR loading admins: {e}")
        return set()

ADMIN_IDS = _load_admin_ids()

def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.id in ADMIN_IDS
```

**Benefits**:
- ✅ No unnecessary module/class overhead
- ✅ Loaded once at import time
- ✅ Simple set membership check (O(1))
- ✅ All admin logic in one place

### 2. Admin Commands Work Anywhere

**Before**: Admin commands subject to DMs-only guards like other commands

**After**: Admin commands explicitly documented as exempt:

```python
def admin_only():
    """
    Decorator to restrict commands to admins.
    
    Note: Admin commands are exempt from DMs-only rule and can be used anywhere.
    """
```

**Usage**: Admins can run commands in:
- ✅ DMs (like before)
- ✅ Server channels (NEW)
- ✅ Any channel where bot has permissions

### 3. All Components Start with "Admin"

Every admin-related component now clearly labeled:

**Command Descriptions**:
- `/admin snapshot` → `[Admin] Get system state snapshot`
- `/admin player` → `[Admin] View player state`
- `/admin match` → `[Admin] View match state`
- `/admin resolve` → `[Admin] Manually resolve a match conflict`
- `/admin adjust_mmr` → `[Admin] Adjust player MMR`
- `/admin remove_queue` → `[Admin] Force remove player from queue`
- `/admin reset_aborts` → `[Admin] Reset player's abort count`
- `/admin clear_queue` → `[Admin] EMERGENCY: Clear entire queue`

**Embed Titles**:
- `Admin System Snapshot`
- `Admin Player State`
- `Admin Match #123 State`
- `⚠️ Admin: Confirm Match Resolution`
- `✅ Admin: Conflict Resolved`
- `❌ Admin: Resolution Failed`
- `🚨 Admin: EMERGENCY Queue Cleared`

**Button Labels**:
- `Admin Confirm` (was "Confirm")
- `Admin Cancel` (was "Cancel")

**File Names**:
- `admin_snapshot_1234567890.txt`
- `admin_match_123.json`

**Access Denied Messages**:
- `🚫 Admin Access Denied` (was "Access Denied")

### 4. Admin-Only Interaction Checks

**New `AdminConfirmationView` Class**:

```python
class AdminConfirmationView(View):
    """
    Admin-only confirmation view.
    
    All interactions with this view are restricted to admins only,
    even if the message is visible in a public channel.
    """
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only admins can interact with this view."""
        if not is_admin(interaction):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🚫 Admin Access Denied",
                    description="Only administrators can interact with admin controls.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return False
        return True
```

**What This Means**:
- Admin sends `/admin resolve` in public channel
- Confirmation buttons appear
- Non-admin tries to click button → `Admin Access Denied` error
- Only admins can interact with admin views

### 5. Simplified Code Structure

**Before**:
- 688 lines
- Complex imports (`ConfirmRestartCancelButtons`)
- DummyView workaround
- Inconsistent button handling

**After**:
- 573 lines (-115 lines)
- Direct imports (`ConfirmButton`, `CancelButton`)
- No workarounds needed
- Consistent `_create_admin_confirmation` helper

**Helper Function**:

```python
def _create_admin_confirmation(
    interaction: discord.Interaction,
    title: str,
    description: str,
    confirm_callback,
    color=discord.Color.orange()
) -> tuple:
    """Create an admin confirmation view with buttons."""
    embed = discord.Embed(title=title, description=description, color=color)
    view = AdminConfirmationView(timeout=60)
    view.set_admin(interaction.user.id)
    
    confirm_btn = ConfirmButton(confirm_callback, label="Admin Confirm", row=0)
    cancel_btn = CancelButton(reset_target=None, label="Admin Cancel", row=0)
    
    view.add_item(confirm_btn)
    view.add_item(cancel_btn)
    
    return embed, view
```

All commands now use this consistent pattern.

## Files Modified

### Deleted Files

1. `src/backend/services/admin_loader_service.py` - No longer needed

### Modified Files

1. `src/bot/commands/admin_command.py` - Complete rewrite
   - Simplified admin verification
   - AdminConfirmationView class
   - All embeds/buttons prefixed with "Admin"
   - Consistent confirmation pattern

## Security Model

### Before

```
Command → @admin_only decorator → Check admin → Execute
```

### After

```
Command → @admin_only decorator → Check admin → Execute
Button Click → AdminConfirmationView.interaction_check() → Check admin → Execute
```

**Two Layers of Protection**:
1. Command level: `@admin_only()` decorator
2. Interaction level: `AdminConfirmationView.interaction_check()`

**Scenario**:
```
1. Admin runs /admin resolve in #public-channel
2. Bot shows confirmation (visible to all)
3. Non-admin tries to click "Admin Confirm"
4. Bot shows "Admin Access Denied" (ephemeral, only to that user)
5. Only admins can actually confirm
```

## Testing Checklist

### Admin Verification
- [ ] Admin can run `/admin` commands
- [ ] Non-admin gets "Admin Access Denied"
- [ ] Admin IDs loaded correctly from `admins.json`

### Channel Access
- [ ] `/admin` commands work in DMs
- [ ] `/admin` commands work in server channels
- [ ] Other users don't see ephemeral admin messages

### Component Naming
- [ ] All command descriptions start with `[Admin]`
- [ ] All embed titles include "Admin"
- [ ] All button labels include "Admin"
- [ ] All error messages say "Admin Access Denied"

### Interaction Security
- [ ] Admin clicks confirmation → works
- [ ] Non-admin clicks confirmation → "Admin Access Denied"
- [ ] Multiple admins can't interfere with each other's confirmations

### Functionality
- [ ] `/admin snapshot` - Shows system state
- [ ] `/admin player discord_id:123` - Shows player info
- [ ] `/admin match match_id:123` - Shows match JSON
- [ ] `/admin resolve` - Resolves conflict after confirmation
- [ ] `/admin adjust_mmr` - Adjusts MMR after confirmation
- [ ] `/admin remove_queue` - Removes player after confirmation
- [ ] `/admin reset_aborts` - Resets aborts after confirmation
- [ ] `/admin clear_queue` - Clears queue after confirmation

## Migration Notes

### If Upgrading

1. **No action needed** - Admin configuration still uses `data/misc/admins.json`
2. **No database changes** - All admin actions still logged
3. **No breaking changes** - Same commands, same functionality

### If You Had Custom Admin Checks

If you referenced the old `admin_loader_service` elsewhere:

**Before**:
```python
from src.backend.services.admin_loader_service import get_admin_loader
admin_loader = get_admin_loader()
if admin_loader.is_admin(user_id):
    ...
```

**After**:
```python
from src.bot.commands.admin_command import is_admin
if is_admin(interaction):
    ...
```

## Benefits Summary

### User Experience
✅ **Clearer Labeling** - Every admin component explicitly labeled  
✅ **Flexible Usage** - Works in any channel, not just DMs  
✅ **Better Security Feedback** - Clear "Admin Access Denied" messages  

### Developer Experience
✅ **Simpler Code** - No unnecessary modules/classes  
✅ **Easier Maintenance** - All admin logic in one file  
✅ **Consistent Patterns** - Helper function for all confirmations  
✅ **Better Security** - Two-layer protection (command + interaction)  

### Performance
✅ **Fast Lookups** - O(1) set membership check  
✅ **Single Load** - Admin IDs loaded once at startup  
✅ **No Extra Dependencies** - No separate service layer  

## Conclusion

Admin commands are now:
- ✅ Simpler to understand (no separate loader module)
- ✅ More flexible (work in any channel)
- ✅ Clearly labeled (every component starts with "Admin")
- ✅ More secure (two-layer admin checks)
- ✅ Easier to maintain (all in one file, consistent patterns)

The refactoring removes unnecessary complexity while improving security and usability.

