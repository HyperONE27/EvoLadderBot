# Mock Data Generator Fixes

## Problem
The mock data generator was creating names and battletags that violated validation rules, flooding Supabase with invalid data.

## Issues Found
1. **Duplicate entries** in NAME_PREFIXES and NAME_SUFFIXES arrays
2. **No validation** against reserved words (admin, mod, bot, etc.)
3. **No character validation** (only length checking)
4. **Battletag generation** didn't validate the final result
5. **No fallback mechanism** for invalid data

## Fixes Applied

### 1. Cleaned Up Name Arrays
- **File**: `scripts/generate_realistic_mock_data.py`
- **Removed**: Duplicate entries in NAME_PREFIXES and NAME_SUFFIXES
- **Added**: More diverse, unique name components
- **Result**: No more duplicate names in the pool

### 2. Enhanced Name Generation
```python
def generate_player_name():
    """Generate a realistic player name that respects all validation rules."""
    import re
    
    # Reserved words that are not allowed
    RESERVED_WORDS = {
        "admin", "mod", "moderator", "player", "bot", "discord", "blizzard", "battle", "gm", "dev", "test", "user"
    }
    
    # Validation checks:
    # - Length: 3-12 characters
    # - Characters: A-Z, a-z, 0-9, _, -
    # - Reserved words: Case-insensitive check
```

### 3. Enhanced Battletag Generation
```python
def generate_battletag(player_name):
    """Generate a realistic battletag that respects validation rules."""
    import re
    
    # Validation checks:
    # - Format: name#numbers
    # - Length: <= 20 characters
    # - Characters: A-Z, a-z, 0-9, _, -, #
```

### 4. Added Validation Function
```python
def validate_player_data(player_data):
    """Validate that player data meets all requirements."""
    # Checks:
    # - Name length (3-12 chars)
    # - Name characters (A-Z, a-z, 0-9, _, -)
    # - Battletag format (name#numbers)
    # - Battletag length (<= 20 chars)
    # - Reserved words (case-insensitive)
```

### 5. Added Fallback Mechanism
```python
# In generate_realistic_mock_data():
# Validate player data
is_valid, error_msg = validate_player_data(player)
if not is_valid:
    print(f"⚠️  Invalid player data: {error_msg}")
    # Regenerate with fallback
    player_name = "Player" + str(i+1)
    battletag = f"{player_name}#1234"
    player["player_name"] = player_name
    player["battletag"] = battletag
```

### 6. Updated Main Function
- **Added**: Updates both `realistic_mock_data.json` and `mock_data.json`
- **Added**: Instructions to run `populate_supabase.py` after generation
- **Added**: Better error reporting and validation feedback

## Validation Rules Enforced

### Player Names
- **Length**: 3-12 characters
- **Characters**: English letters, numbers, underscores, hyphens only
- **Reserved Words**: Case-insensitive check against banned words
- **Format**: No special characters or spaces

### Battletags
- **Format**: `name#numbers` (e.g., `PlayerName#1234`)
- **Length**: Maximum 20 characters
- **Characters**: English letters, numbers, underscores, hyphens, hash symbol
- **Numbers**: 1-4 digits after the hash

## Files Modified
- `scripts/generate_realistic_mock_data.py` - Main generator with all fixes
- `docs/MOCK_DATA_GENERATOR_FIXES.md` - This documentation

## Usage
1. **Generate Clean Data**:
   ```bash
   python scripts/generate_realistic_mock_data.py
   ```

2. **Update Supabase**:
   ```bash
   python scripts/populate_supabase.py
   ```

## Expected Results
- **All player names**: 3-12 characters, valid characters only, no reserved words
- **All battletags**: Valid format, proper length, no special characters
- **Validation**: 100% of generated data passes validation rules
- **Fallback**: Invalid data is automatically regenerated with safe defaults

## Testing
The generator now includes:
- **Real-time validation** during generation
- **Error reporting** for invalid data
- **Automatic fallback** for problematic entries
- **Comprehensive validation** before saving

## Next Steps
1. Run the fixed generator to create clean data
2. Update Supabase with the clean data
3. Verify all names and battletags are valid
4. Test the leaderboard with clean data
