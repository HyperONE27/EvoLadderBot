# Admin Configuration via JSON

## Summary

Admin user configuration has been moved from environment variables to `data/misc/admins.json` for easier management and version control.

## Changes Made

### Before (Environment Variables)

Admins were configured in environment variables:
```bash
ADMIN_USER_IDS=123456789,987654321
ADMIN_ROLE_IDS=111111111,222222222
```

**Problems**:
- Hard to manage (need to restart bot to change)
- Not version controlled
- Need to set up on every deployment
- Mixed role IDs and user IDs (confusing)

### After (JSON File)

Admins are now configured in `data/misc/admins.json`:
```json
[
    {
        "discord_id": 218147282875318274,
        "name": "HyperONE"
    },
    {
        "discord_id": 180800712874262528,
        "name": "Kat"
    }
]
```

**Benefits**:
- ✅ Easy to edit (just modify JSON file)
- ✅ Version controlled (track who added/removed admins)
- ✅ No bot restart needed (can reload if needed)
- ✅ Documented (names included for reference)
- ✅ Simple format (just Discord user IDs)

## New Files

### `src/backend/services/admin_loader_service.py`

Service that loads and caches admin configuration:

```python
from src.backend.services.admin_loader_service import get_admin_loader

admin_loader = get_admin_loader()

# Check if user is admin
if admin_loader.is_admin(discord_id):
    # User is admin

# Get all admin IDs
admin_ids = admin_loader.get_admin_ids()

# Reload configuration (if file changed)
admin_loader.reload()
```

**Features**:
- Loads from `data/misc/admins.json` on first access
- Caches admin IDs for fast lookups
- Singleton pattern (one global instance)
- Graceful error handling (logs warnings, continues with empty list)
- Can reload without bot restart

## Modified Files

### `src/bot/commands/admin_command.py`

**Removed**:
```python
ADMIN_ROLE_IDS = [int(id_str) for id_str in os.getenv("ADMIN_ROLE_IDS", "").split(",") if id_str.strip()]
ADMIN_USER_IDS = [int(id_str) for id_str in os.getenv("ADMIN_USER_IDS", "").split(",") if id_str.strip()]

def is_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.id in ADMIN_USER_IDS:
        return True
    if hasattr(interaction.user, 'roles'):
        return any(role.id in ADMIN_ROLE_IDS for role in interaction.user.roles)
    return False
```

**Added**:
```python
from src.backend.services.admin_loader_service import get_admin_loader

def is_admin(interaction: discord.Interaction) -> bool:
    """Check if user is an admin (loaded from admins.json)."""
    admin_loader = get_admin_loader()
    return admin_loader.is_admin(interaction.user.id)
```

**Note**: Role-based admin access has been removed. Only direct Discord user IDs are now supported. If role-based access is needed in the future, it can be added back separately.

## JSON File Format

### Required Fields

- `discord_id` (integer): Discord user ID

### Optional Fields

- `name` (string): Human-readable name for reference (not used by bot)

### Example

```json
[
    {
        "discord_id": 123456789012345678,
        "name": "AdminUser1"
    },
    {
        "discord_id": 987654321098765432,
        "name": "AdminUser2"
    }
]
```

### Getting Discord User IDs

To get a Discord user ID:
1. Enable Developer Mode in Discord (User Settings → Advanced → Developer Mode)
2. Right-click on a user
3. Click "Copy User ID"
4. Paste into `admins.json`

## Error Handling

The service handles errors gracefully:

### File Not Found
```
[AdminLoader] WARNING: data/misc/admins.json not found. No admins loaded.
```
Bot continues running with no admins (all admin commands will fail).

### Invalid JSON
```
[AdminLoader] ERROR: Failed to parse data/misc/admins.json: ...
```
Bot continues running with no admins.

### Missing discord_id
Entries without `discord_id` are silently skipped.

## Migration Steps

### If you had environment variables set:

1. Get the user IDs from your environment variables
2. Add them to `data/misc/admins.json`:
   ```json
   [
       {
           "discord_id": YOUR_ID_HERE,
           "name": "Your Name"
       }
   ]
   ```
3. Remove `ADMIN_USER_IDS` and `ADMIN_ROLE_IDS` from your environment
4. Restart the bot

### If you're setting up for the first time:

1. Edit `data/misc/admins.json`
2. Add your Discord user ID
3. Start the bot

## Adding/Removing Admins

### To Add an Admin

1. Edit `data/misc/admins.json`
2. Add new entry:
   ```json
   {
       "discord_id": 123456789012345678,
       "name": "NewAdmin"
   }
   ```
3. Save the file
4. (Optional) Reload configuration or restart bot

### To Remove an Admin

1. Edit `data/misc/admins.json`
2. Delete the entry
3. Save the file
4. (Optional) Reload configuration or restart bot

### Future Enhancement: Reload Command

A future enhancement could add `/admin reload` to reload the configuration without restart:

```python
@admin_group.command(name="reload", description="Reload admin configuration")
@admin_only()
async def admin_reload(interaction: discord.Interaction):
    admin_loader = get_admin_loader()
    admin_loader.reload()
    admin_ids = admin_loader.get_admin_ids()
    
    embed = discord.Embed(
        title="✅ Configuration Reloaded",
        description=f"Loaded {len(admin_ids)} admin(s) from admins.json",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
```

## Security Considerations

### Advantages

✅ **Version Control**: Track who added/removed admins via git history  
✅ **Audit Trail**: Commit messages document changes  
✅ **No Secrets in Env**: Discord IDs are not sensitive (they're visible in Discord)  
✅ **Easy Review**: See all admins in one file  

### Important Notes

⚠️ **Discord User IDs are NOT secrets**: They are visible to anyone who can see the user in Discord. It's safe to store them in version control.

⚠️ **Role-based access removed**: The old `ADMIN_ROLE_IDS` environment variable is no longer supported. If you need role-based access, this must be re-implemented separately (or just add those users directly to admins.json).

## Testing

Test the configuration:

1. **Valid admin**: Run any `/admin` command as a user in `admins.json` → should work
2. **Non-admin**: Run any `/admin` command as a user NOT in `admins.json` → should show "Access Denied"
3. **Missing file**: Delete `admins.json` → should log warning, no commands work
4. **Invalid JSON**: Break JSON syntax → should log error, no commands work

## Current Admins

The current `data/misc/admins.json` contains 9 admins:
- HyperONE (218147282875318274)
- Kat (180800712874262528)
- dingusfrog (329001986135556096)
- Magnath (333564488898969600)
- Vanya (1197177996663066674)
- ZaRDieNT (329173955170664448)
- Rake (494665531224490004)
- Meven (143843782704627712)
- November (472471742162665472)

## Rollback Plan

If issues arise, you can temporarily use environment variables by reverting:

```bash
git checkout HEAD~1 -- src/bot/commands/admin_command.py
git checkout HEAD~1 -- src/backend/services/admin_loader_service.py
```

Then set environment variables:
```bash
ADMIN_USER_IDS=123,456,789
```

## Conclusion

Admin configuration is now:
- ✅ Simpler (just edit JSON file)
- ✅ Version controlled (track changes in git)
- ✅ Documented (names included in JSON)
- ✅ More maintainable (no environment variable management)
- ✅ Follows existing patterns (same as maps, races, regions, countries)

