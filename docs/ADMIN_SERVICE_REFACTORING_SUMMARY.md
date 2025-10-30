# Admin Service Refactoring: Separation of Concerns

## Problem
The `AdminService` (backend) contained too many frontend concerns, violating separation of concerns principles:
- Creating Discord embeds
- Formatting strings for display
- Sending Discord DMs
- Discord-specific imports

This made the backend tightly coupled to Discord and difficult to test or reuse with other frontends.

## Solution
Properly separated backend business logic from frontend presentation logic.

### Backend (`admin_service.py`)
**NOW CONTAINS ONLY:**
- Business logic
- Data access and manipulation
- State management
- Audit logging
- Raw data return values

**REMOVED:**
- All `discord` imports
- All formatting methods (`format_system_snapshot`, `format_conflict_match`, `format_player_state`)
- All Discord embed creation
- All notification sending logic (`_send_player_notification`)

**NEW PATTERN:**
Methods now return `notification_data` dict in their response when player notifications are needed:

```python
return {
    'success': True,
    'discord_uid': discord_uid,
    'race': race,
    'old_mmr': current_mmr,
    'new_mmr': new_mmr,
    'change': new_mmr - current_mmr,
    'notification_data': {
        'player_uid': discord_uid,
        'player_name': 'PlayerName',
        'admin_name': 'AdminName',
        'operation': 'add',
        'value': 50,
        'reason': 'Compensation'
    }
}
```

### Frontend (`admin_command.py`)
**NOW CONTAINS:**
- All Discord-specific code
- All formatting functions (moved from backend)
- Discord embed creation
- Player notification sending
- Display logic

**NEW FUNCTIONS:**
1. `send_player_notification(bot, discord_uid, embed)` - Sends DM to player
2. `format_system_snapshot(snapshot)` - Formats snapshot for display
3. `format_conflict_match(conflict)` - Formats conflict for display
4. `format_player_state(state)` - Formats player state for display

**UPDATED PATTERN:**
Command callbacks now:
1. Call backend service methods
2. Check for `notification_data` in response
3. Create appropriate Discord embeds for notifications
4. Send notifications to affected players
5. Display results to admin

## Example: MMR Adjustment

### Before (BAD - Backend doing frontend work)
```python
# In admin_service.py
notification_embed = discord.Embed(...)  # ❌ Creating Discord embed in backend
await self._send_player_notification(...)  # ❌ Sending Discord DM in backend
return {'success': True, ...}
```

### After (GOOD - Proper separation)
```python
# In admin_service.py (BACKEND)
return {
    'success': True,
    'notification_data': {  # ✅ Returns raw data
        'player_uid': uid,
        'admin_name': 'AdminName',
        'operation': 'add',
        'value': 50,
        'reason': reason
    }
}

# In admin_command.py (FRONTEND)
result = await admin_service.adjust_player_mmr(...)
if result['success'] and 'notification_data' in result:
    notif = result['notification_data']
    
    # ✅ Frontend creates Discord embed
    player_embed = discord.Embed(
        title="📊 Admin Action: MMR Adjusted",
        description=f"Your MMR has been {operation_text}...",
        color=discord.Color.blue()
    )
    # ... add fields ...
    
    # ✅ Frontend sends notification
    await send_player_notification(interaction.client, notif['player_uid'], player_embed)
```

## Benefits

### 1. **Proper Separation of Concerns**
- Backend: Pure business logic, framework-agnostic
- Frontend: All Discord-specific code

### 2. **Better Testability**
- Backend can be tested without Discord mocks
- Can verify notification data in responses without sending actual DMs

### 3. **Flexibility**
- Backend can be reused with different frontends (web, CLI, Slack, etc.)
- Formatting can be changed without touching backend

### 4. **Maintainability**
- Clear boundaries between layers
- Easier to understand and modify
- No hidden coupling

### 5. **Type Safety**
- Backend returns plain dicts (can be typed with TypedDict)
- No Discord-specific types in backend

## Commands Updated

All admin commands now properly handle notifications in frontend:

1. **`/admin adjust_mmr`** - Notifies player of MMR change
2. **`/admin remove_queue`** - Notifies player of queue removal
3. **`/admin reset_aborts`** - Notifies player of abort reset
4. **`/admin clear_queue`** - Notifies all removed players
5. **`/admin resolve`** - Notifies both players in match conflict

## File Changes

### `src/backend/services/admin_service.py`
- ❌ Removed: `import discord`
- ❌ Removed: `_send_player_notification()` method
- ❌ Removed: `format_system_snapshot()` method
- ❌ Removed: `format_conflict_match()` method
- ❌ Removed: `format_player_state()` method
- ❌ Removed: `_format_report()` helper
- ❌ Removed: `_calc_success_rate()` helper
- ✅ Updated: All methods return `notification_data` in response
- ✅ Updated: `resolve_user()` made public and returns player info dict
- ✅ Added: Clear docstring stating "ONLY business logic, returns raw data"

### `src/bot/commands/admin_command.py`
- ✅ Added: `send_player_notification()` function
- ✅ Added: `format_system_snapshot()` function
- ✅ Added: `format_conflict_match()` function
- ✅ Added: `format_player_state()` function
- ✅ Updated: All command callbacks create embeds and send notifications
- ✅ Updated: All user resolution calls use `admin_service.resolve_user()`

## Verification

**Backend is now completely Discord-free:**
```bash
grep -r "import discord" src/backend/services/admin_service.py
# Returns: (nothing)
```

**No formatting methods in backend:**
```bash
grep -r "def format_" src/backend/services/admin_service.py
# Returns: (nothing)
```

**All notifications handled in frontend:**
```bash
grep -r "send_player_notification" src/bot/commands/admin_command.py
# Returns: Multiple calls in command callbacks
```

## Architecture Principle

**Backend:**
- Domain logic
- Data access
- Business rules
- Returns structured data

**Frontend:**
- User interaction
- Display formatting
- Platform-specific code (Discord)
- Consumes structured data

This is a classic **Clean Architecture** pattern where the core business logic has no dependencies on external frameworks or UI concerns.

