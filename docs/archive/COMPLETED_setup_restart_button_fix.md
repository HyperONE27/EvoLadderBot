# Setup Restart Button Fix

## Problem
When users pressed the "restart" button during `/setup`, the modal would not correctly populate with their current input values. Instead, it would either show empty fields or stale database defaults, forcing users to re-enter all information from scratch.

## Root Cause
The issue occurred in three locations where restart buttons were created:

1. **`SetupModal.on_submit`** - When validation errors occurred, the `ErrorView` was created with `self.existing_data` (old database values) instead of capturing the current user input from the modal fields.

2. **`UnifiedSetupView.__init__`** - When creating the restart button for the country/region selection screen, it passed an empty `SetupModal()` without any existing data.

3. **`create_setup_confirmation_view`** - When creating the preview confirmation screen, the restart button was initialized with an empty `SetupModal()` instead of the current input values.

## Solution
Updated all three locations to capture and pass the **current user input** to the restart button:

### 1. SetupModal Error Handling
**File**: `src/bot/interface/commands/setup_command.py`

Added a `current_input` dictionary at the start of `on_submit()` that captures all modal field values:

```python
async def on_submit(self, interaction: discord.Interaction):
    # Capture current input values for restart functionality
    current_input = {
        'player_name': self.user_id.value,
        'battletag': self.battle_tag.value,
        'alt_player_name_1': self.alt_id_1.value.strip() if self.alt_id_1.value else '',
        'alt_player_name_2': self.alt_id_2.value.strip() if self.alt_id_2.value else '',
        # Preserve country/region from existing data if present
        'country': self.existing_data.get('country', ''),
        'region': self.existing_data.get('region', '')
    }
```

Then, all `ErrorView` instances now receive `current_input` instead of `self.existing_data`:

```python
view=ErrorView(error, current_input)
```

**Locations updated**:
- Line 131: User ID validation error
- Line 146: BattleTag validation error
- Line 165: Alternative ID 1 validation error
- Line 182: Alternative ID 2 validation error
- Line 198: Duplicate IDs error

### 2. UnifiedSetupView Restart Button
**File**: `src/bot/interface/commands/setup_command.py`

Added preparation of `existing_data` dict before creating the restart button:

```python
# Prepare existing data for restart button
existing_data = {
    'player_name': self.user_id,
    'battletag': self.battle_tag,
    'alt_player_name_1': self.alt_ids[0] if len(self.alt_ids) > 0 else '',
    'alt_player_name_2': self.alt_ids[1] if len(self.alt_ids) > 1 else '',
    'country': self.selected_country['code'] if self.selected_country else '',
    'region': self.selected_region['code'] if self.selected_region else ''
}

# Add action buttons using the unified approach
buttons = ConfirmRestartCancelButtons.create_buttons(
    confirm_callback=self.confirm_callback,
    reset_target=SetupModal(existing_data=existing_data),
    # ... rest of button configuration
)
```

**Location**: Lines 424-437

### 3. Confirmation View Restart Button
**File**: `src/bot/interface/commands/setup_command.py`

Added preparation of `existing_data` dict in `create_setup_confirmation_view()`:

```python
def create_setup_confirmation_view(user_id: str, alt_ids: list, battle_tag: str, 
                                   country: dict, region: dict) -> ConfirmEmbedView:
    # ... existing code ...
    
    # Prepare existing data for restart button
    existing_data = {
        'player_name': user_id,
        'battletag': battle_tag,
        'alt_player_name_1': alt_ids[0] if len(alt_ids) > 0 else '',
        'alt_player_name_2': alt_ids[1] if len(alt_ids) > 1 else '',
        'country': country['code'],
        'region': region['code']
    }
    
    # ... existing code ...
    
    return ConfirmEmbedView(
        # ... other parameters ...
        reset_target=SetupModal(existing_data=existing_data)
    )
```

**Location**: Lines 570-635

## Impact
✅ **Fixed**: Restart buttons now correctly populate the modal with current user input  
✅ **Improved UX**: Users don't have to re-enter all information when fixing validation errors  
✅ **Consistent behavior**: All restart buttons throughout the setup flow behave the same way  

## Testing
Created and ran `test_setup_restart_fix.py` to verify:
- Current input capture logic works correctly
- UnifiedSetupView data structure is correct
- Confirmation view data structure is correct
- Edge cases (empty/partial alt IDs) are handled properly

All tests passed ✅

## Files Modified
1. `src/bot/interface/commands/setup_command.py` - Updated restart button initialization in 3 locations

## User Experience Flow (After Fix)
1. User opens `/setup` and enters their information
2. If validation fails, they see an error with a "Try Again" button
3. Clicking "Try Again" opens the modal **with their previous input pre-filled**
4. User can fix the error without re-entering everything
5. Same behavior applies to restart buttons on country/region selection and confirmation screens

## Notes
- The fix preserves country/region selections when restarting from validation errors
- Database defaults are still correctly loaded on the initial `/setup` command
- The fix only affects the restart button behavior, not the initial setup flow

