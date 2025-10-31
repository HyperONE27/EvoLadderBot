# ✅ Global Timeout Configuration Fix

## Issue
Admin commands were hardcoding timeout values instead of using the centralized `GLOBAL_TIMEOUT` configuration from `config.py`.

## What Was Wrong

### Before (Hardcoded) ❌
```python
# admin_command.py
class AdminConfirmationView(View):
    def __init__(self, timeout: int = 300):  # ❌ Hardcoded 300 seconds
        super().__init__(timeout=timeout)

# Later in code
view = AdminConfirmationView(timeout=60)  # ❌ Hardcoded 60 seconds
```

**Problems:**
1. Timeout values scattered across codebase
2. Inconsistent with other commands
3. Can't be configured from environment
4. Violates DRY (Don't Repeat Yourself)
5. Makes it hard to adjust all timeouts at once

## Solution

### After (Uses Global Config) ✅
```python
# admin_command.py
from src.bot.config import GLOBAL_TIMEOUT  # ✅ Import global constant

class AdminConfirmationView(View):
    def __init__(self, timeout: int = None):  # ✅ Default to None
        super().__init__(timeout=timeout or GLOBAL_TIMEOUT)  # ✅ Use global

# Later in code
view = AdminConfirmationView()  # ✅ Uses GLOBAL_TIMEOUT by default
```

## Pattern Used in Codebase

This follows the established pattern used in ALL other commands:

### Queue Command
```python
from src.bot.config import GLOBAL_TIMEOUT

class QueueView(discord.ui.View):
    def __init__(self, discord_user_id: int, ...):
        super().__init__(timeout=GLOBAL_TIMEOUT)
```

### Terms of Service Command
```python
from src.bot.config import GLOBAL_TIMEOUT

class TOSConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=GLOBAL_TIMEOUT)
```

### Leaderboard Command
```python
from src.bot.config import GLOBAL_TIMEOUT

class LeaderboardView(discord.ui.View):
    def __init__(self, ...):
        super().__init__(timeout=GLOBAL_TIMEOUT)
```

### Setup Command
```python
from src.bot.config import GLOBAL_TIMEOUT

class SetupModal(discord.ui.Modal):
    def __init__(self, ...):
        super().__init__(timeout=GLOBAL_TIMEOUT)
```

## Configuration Source

### `src/bot/config.py`
```python
# Global timeout for Discord interactions (in seconds)
GLOBAL_TIMEOUT = _get_required_int_env("GLOBAL_TIMEOUT")
```

### `.env` file
```bash
GLOBAL_TIMEOUT=300  # 5 minutes (configurable per environment)
```

**Benefits:**
- Single source of truth
- Environment-specific configuration
- Consistent across all commands
- Easy to adjust globally
- Railway/production can override

## Changes Made

### 1. Added Import
```python
from src.bot.config import GLOBAL_TIMEOUT
```

### 2. Updated Constructor
```python
def __init__(self, timeout: int = None):
    """
    Initialize admin confirmation view.
    
    Args:
        timeout: View timeout in seconds (default: GLOBAL_TIMEOUT from config)
    """
    super().__init__(timeout=timeout or GLOBAL_TIMEOUT)
```

### 3. Removed Hardcoded Values
```python
# BEFORE ❌
view = AdminConfirmationView(timeout=60)

# AFTER ✅
view = AdminConfirmationView()
```

## Verification

**No more hardcoded timeouts:**
```bash
$ grep "timeout=60\|timeout=300\|timeout=3600" src/bot/commands/admin_command.py
# (no matches) ✅
```

**Uses GLOBAL_TIMEOUT:**
```bash
$ grep "GLOBAL_TIMEOUT" src/bot/commands/admin_command.py
from src.bot.config import GLOBAL_TIMEOUT
super().__init__(timeout=timeout or GLOBAL_TIMEOUT)
```

**Consistent with other commands:**
```bash
$ grep "from src.bot.config import GLOBAL_TIMEOUT" src/bot/commands/*.py
queue_command.py:from src.bot.config import GLOBAL_TIMEOUT
termsofservice_command.py:from src.bot.config import GLOBAL_TIMEOUT
leaderboard_command.py:from src.bot.config import GLOBAL_TIMEOUT
setup_command.py:from src.bot.config import GLOBAL_TIMEOUT
setcountry_command.py:from src.bot.config import GLOBAL_TIMEOUT
activate_command.py:from src.bot.config import GLOBAL_TIMEOUT
prune_command.py:from src.bot.config import GLOBAL_TIMEOUT
admin_command.py:from src.bot.config import GLOBAL_TIMEOUT  ✅ Now included!
```

## Benefits

1. **Centralized Configuration**: Single place to change timeout
2. **Environment-Specific**: Dev can use 30s, prod can use 300s
3. **Consistency**: All commands use same timeout value
4. **Maintainability**: No need to search for hardcoded values
5. **Testability**: Can mock `config.GLOBAL_TIMEOUT` for tests
6. **Documentation**: Timeout value defined and explained in one place

## Related Configuration

The global timeout is used for:
- View timeouts (buttons/dropdowns)
- Modal timeouts (forms)
- Prune command (message age threshold)
- All interactive Discord UI components

## Status

✅ **COMPLETE** - All hardcoded timeouts replaced with `GLOBAL_TIMEOUT`
✅ **NO LINTER ERRORS** - All changes validated
✅ **CONSISTENT PATTERN** - Matches all other commands in codebase
✅ **CONFIGURATION DRIVEN** - Timeout controlled by environment variable

Admin commands now follow the centralized configuration pattern used throughout the bot.

