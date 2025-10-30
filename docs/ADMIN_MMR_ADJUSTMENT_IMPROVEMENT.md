# Admin MMR Adjustment - Operation Types

## Overview
Enhanced the admin MMR adjustment command to support three intuitive operation types instead of just setting absolute values.

## New Operation Types

### 1. Set (Original Behavior)
- Sets MMR to a specific absolute value
- Example: Set player's MMR to 2000
- Use case: Initial MMR corrections, resetting after recalibration

### 2. Add
- Adds a value to the current MMR
- Example: Add 50 MMR (current: 1500 → new: 1550)
- Use case: Bonus MMR for participation, compensation for technical issues

### 3. Subtract
- Subtracts a value from the current MMR
- Example: Subtract 100 MMR (current: 1500 → new: 1400)
- Use case: Penalties for violations, MMR corrections

## Command Usage

```
/admin adjust_mmr
  discord_id: <player's Discord ID>
  race: <race code (e.g., bw_terran, sc2_zerg)>
  operation: [Set to specific value | Add to current MMR | Subtract from current MMR]
  value: <MMR amount>
  reason: <explanation for audit log>
```

## Features

### Safety Checks
- **Negative MMR Prevention**: Operations that would result in negative MMR are rejected
- **Confirmation Flow**: All adjustments require admin confirmation with preview
- **Audit Logging**: Full details logged including operation type, value, and resulting change

### Confirmation Display
Shows:
- Player mention
- Race being adjusted
- Operation type and value (e.g., "Add +50" or "Subtract 100")
- Reason for adjustment

### Success Display
Shows:
- Operation type performed
- Old MMR value
- New MMR value
- Net change (with +/- sign)
- Reason for adjustment

## Implementation Details

### Frontend (`admin_command.py`)
- Added `operation` parameter with three choices
- Changed `new_mmr` to `value` (more generic)
- Updated confirmation message to show operation type
- Updated success message to include operation details

### Backend (`admin_service.py`)
- Added operation type handling ('set', 'add', 'subtract')
- Calculates final MMR based on operation
- Validates result before applying
- Logs operation type and value in audit trail

### Audit Log Enhancement
Logs now include:
- `operation`: Type of operation performed
- `value`: Value used in operation
- `old_mmr`: MMR before adjustment
- `new_mmr`: MMR after adjustment
- `change`: Net change (calculated)

## Examples

### Before (Old System)
Admin wants to give 50 MMR bonus:
1. Check current MMR manually: 1500
2. Calculate: 1500 + 50 = 1550
3. Use command with value 1550
4. Risk of calculation errors

### After (New System)
Admin wants to give 50 MMR bonus:
1. Use command with operation="Add" and value=50
2. System automatically calculates: current + 50
3. No manual calculation needed
4. Clear intent in audit log

## Benefits
1. **Intuitive**: Directly express intent (add/subtract vs mental math)
2. **Safe**: Prevents negative MMR, shows preview before applying
3. **Auditable**: Operation type clearly logged for review
4. **Flexible**: Supports all use cases (set, bonus, penalty)

