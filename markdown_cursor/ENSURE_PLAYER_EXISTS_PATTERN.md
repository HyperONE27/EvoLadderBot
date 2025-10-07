# Ensure Player Exists Pattern

## Overview

Every slash command now calls `ensure_player_exists()` at the start. This method implements a **get-or-create** pattern that guarantees every user who interacts with the bot has a database record.

## The Method

**Location**: `src/backend/services/user_info_service.py`

```python
def ensure_player_exists(self, discord_uid: int) -> Dict[str, Any]:
    """
    Ensure a player record exists in the database.
    
    If the player doesn't exist, creates a minimal record with just the discord_uid.
    If the player already exists, returns their existing data.
    
    This should be called at the start of any slash command to ensure the user
    has a database record before any operations are performed.
    
    Args:
        discord_uid: Discord user ID.
    
    Returns:
        Player data dictionary (either existing or newly created).
    """
    player = self.get_player(discord_uid)
    
    if player is None:
        # Create minimal player record
        self.create_player(discord_uid=discord_uid)
        player = self.get_player(discord_uid)
    
    return player
```

## Why This Pattern?

1. **Consistency**: Every user gets a database record on first interaction
2. **Simplicity**: Commands don't need to check if user exists
3. **Clean**: Single method call handles both create and retrieve
4. **Safe**: Idempotent - can be called multiple times safely
5. **Minimal**: Only stores discord_uid initially, full data comes from `/setup`

## Usage in Commands

### Example: `/activate` Command

```python
async def on_submit(self, interaction: discord.Interaction):
    try:
        # Ensure player exists in database
        user_service = UserInfoService()
        user_service.ensure_player_exists(interaction.user.id)
        
        # Rest of command logic...
        result = submit_activation_code(interaction.user.id, self.code_input.value)
```

### Example: `/setup` Command

```python
async def setup_command(interaction: discord.Interaction):
    """Handle the /setup slash command"""
    # Ensure player exists in database
    user_info_service.ensure_player_exists(interaction.user.id)
    
    # Send the modal directly as the initial response
    modal = SetupModal()
    await interaction.response.send_modal(modal)
```

### Example: `/leaderboard` Command

```python
async def leaderboard_command(interaction: discord.Interaction):
    """Handle the /leaderboard slash command"""
    # Ensure player exists in database
    from src.backend.services.user_info_service import UserInfoService
    user_info_service = UserInfoService()
    user_info_service.ensure_player_exists(interaction.user.id)
    
    # Rest of command logic...
```

## What Gets Created?

When a new user runs any command, this minimal record is created:

```python
{
    'discord_uid': 12345,           # ✓ Set
    'player_name': None,             # Empty until /setup
    'battletag': None,               # Empty until /setup
    'alt_player_name_1': None,       # Empty until /setup
    'alt_player_name_2': None,       # Empty until /setup
    'country': None,                 # Empty until /setup
    'region': None,                  # Empty until /setup
    'accepted_tos': False,           # False until /termsofservice
    'completed_setup': False,        # False until /setup
    'activation_code': None,         # Empty until /activate
    'created_at': '2025-10-03 ...',  # ✓ Set
    'updated_at': '2025-10-03 ...'   # ✓ Set
}
```

The record exists but is mostly empty. Users must run `/setup` to fill in their profile.

## All Commands Using This Pattern

| Command | Implementation |
|---------|---------------|
| `/activate` | ✅ Calls `ensure_player_exists()` in modal submit |
| `/setup` | ✅ Calls `ensure_player_exists()` at command start |
| `/setcountry` | ✅ Calls `ensure_player_exists()` at command start |
| `/termsofservice` | ✅ Calls `ensure_player_exists()` at command start |
| `/leaderboard` | ✅ Calls `ensure_player_exists()` at command start |

## Benefits

### Before (Without Pattern)
```python
# Command would need to check:
if not user_service.player_exists(user_id):
    # Create player? Error message? Different logic?
    pass
else:
    # Continue with normal logic
    pass
```

### After (With Pattern)
```python
# Simply ensure they exist
user_service.ensure_player_exists(user_id)
# Now we know they exist, continue with logic
```

## Testing

The method has been tested and verified:

1. **New user**: Creates minimal record, returns new data
2. **Existing user**: Returns existing data, no duplicate creation
3. **Idempotent**: Calling multiple times is safe

Example test output:
```
1. Testing with new user (discord_uid=888888)
   ✓ Player created: {...}
   - Discord UID: 888888
   - Player Name: None
   - Completed Setup: 0

2. Testing with existing user (discord_uid=888888)
   ✓ Player retrieved: {...}
   - Same record: True

3. Testing with existing test user (discord_uid=100001)
   ✓ Existing player retrieved: AlphaStrike
   - Discord UID: 100001
   - Player Name: AlphaStrike
```

## Database Impact

- **First command**: Creates 1 minimal record
- **Subsequent commands**: Just reads existing record
- **No duplicates**: Discord UID is unique constraint
- **Clean data**: No orphaned records or missing references

## Future Commands

When adding new commands:

1. Add this at the start of every command handler:
   ```python
   user_info_service.ensure_player_exists(interaction.user.id)
   ```

2. That's it! The user is guaranteed to have a database record.

---

**Summary**: Every slash command now automatically ensures the user has a database record before proceeding. This creates a clean, consistent pattern across all bot interactions.

