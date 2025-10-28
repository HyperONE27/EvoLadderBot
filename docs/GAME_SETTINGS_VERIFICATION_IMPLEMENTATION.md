# Game Settings Verification Implementation - Complete

## Overview

Successfully implemented comprehensive game settings verification for replay validation. The system now checks that replays meet specific game configuration requirements:

- `game_privacy` must be `"Normal"`
- `game_speed` must be `"Faster"`
- `game_duration_setting` must be `"Unlimited"`
- `locked_alliances` must be `"Yes"`

All verification results are displayed in the Discord replay details embed with clear pass/fail indicators.

---

## Changes Made

### 1. Configuration Layer
**File**: `src/backend/core/config.py`

Added four new configuration constants that define the expected game settings:
```python
EXPECTED_GAME_PRIVACY = "Normal"
EXPECTED_GAME_SPEED = "Faster"
EXPECTED_GAME_DURATION = "Unlimited"
EXPECTED_LOCKED_ALLIANCES = "Yes"
```

**Rationale**: Centralizing these values in config allows for easy adjustment without code changes.

---

### 2. Type Definitions
**File**: `src/backend/core/types.py`

#### New Type: `GameSettingVerificationDetail`
```python
class GameSettingVerificationDetail(TypedDict):
    """Detailed result of a single game setting verification check."""
    success: bool
    expected: str
    found: str
```

This type provides a consistent structure for reporting on each game setting check with:
- `success`: Boolean indicating if the check passed
- `expected`: The expected value for the setting
- `found`: The actual value found in the replay

#### Updated Type: `VerificationResult`
Extended to include four new fields:
```python
class VerificationResult(TypedDict):
    # ... existing fields ...
    game_privacy: GameSettingVerificationDetail
    game_speed: GameSettingVerificationDetail
    game_duration: GameSettingVerificationDetail
    locked_alliances: GameSettingVerificationDetail
```

---

### 3. Backend Verification Logic
**File**: `src/backend/services/match_completion_service.py`

#### Imports Added
```python
from src.backend.core.types import GameSettingVerificationDetail
from src.backend.core.config import (
    EXPECTED_GAME_PRIVACY,
    EXPECTED_GAME_SPEED,
    EXPECTED_GAME_DURATION,
    EXPECTED_LOCKED_ALLIANCES
)
```

#### New Method: `_verify_game_setting()`
```python
def _verify_game_setting(
    self,
    replay_details: Dict[str, any],
    field_name: str,
    expected_value: str
) -> GameSettingVerificationDetail:
    """
    Verifies a specific game setting against an expected value.
    
    Args:
        replay_details: Replay data from the database
        field_name: The name of the field to verify
        expected_value: The expected value for the field
        
    Returns:
        GameSettingVerificationDetail with success status
    """
    actual_value = replay_details.get(field_name)
    is_valid = actual_value == expected_value
    
    return GameSettingVerificationDetail(
        success=is_valid,
        expected=expected_value,
        found=actual_value
    )
```

#### Updated Method: `verify_replay_data()`
The method now:
1. Calls `_verify_game_setting()` for each of the four game settings
2. Includes the four new verification details in the `VerificationResult`
3. Updates the `all_passed` check to include all four game setting checks
4. Logs all verification results including the new game setting checks

**Flow**:
```python
# Verify game settings
privacy_detail = self._verify_game_setting(replay_data, "game_privacy", EXPECTED_GAME_PRIVACY)
speed_detail = self._verify_game_setting(replay_data, "game_speed", EXPECTED_GAME_SPEED)
duration_detail = self._verify_game_setting(replay_data, "game_duration_setting", EXPECTED_GAME_DURATION)
alliances_detail = self._verify_game_setting(replay_data, "locked_alliances", EXPECTED_LOCKED_ALLIANCES)

# Include in VerificationResult
result = VerificationResult(
    races=races_detail,
    map=map_detail,
    timestamp=timestamp_detail,
    observers=observers_detail,
    game_privacy=privacy_detail,
    game_speed=speed_detail,
    game_duration=duration_detail,
    locked_alliances=alliances_detail
)
```

---

### 4. Frontend Display
**File**: `src/bot/components/replay_details_embed.py`

#### Updated Method: `_format_verification_results()`
The method now includes formatting for the four new game setting checks:

1. **Game Privacy Check**:
   - Pass: `"- ✅ **Privacy:** `Normal`"`
   - Fail: `"- ❌ **Privacy:** Expected `Normal`, but found `Public`."`

2. **Game Speed Check**:
   - Pass: `"- ✅ **Game Speed:** `Faster`"`
   - Fail: `"- ❌ **Game Speed:** Expected `Faster`, but found `Normal`."`

3. **Game Duration Check**:
   - Pass: `"- ✅ **Duration:** `Unlimited`"`
   - Fail: `"- ❌ **Duration:** Expected `Unlimited`, but found `Timed`."`

4. **Locked Alliances Check**:
   - Pass: `"- ✅ **Locked Alliances:** `Yes`"`
   - Fail: `"- ❌ **Locked Alliances:** Expected `Yes`, but found `No`."`

#### Overall Verification Status
Updated the final "Verification Complete" or "Verification Issues" message to account for all eight checks (existing four + new four).

---

## Data Flow

```
replay_data (from parsing)
    ↓
match_completion_service.verify_replay_data()
    ↓
_verify_game_setting() called 4 times
    ├→ game_privacy check
    ├→ game_speed check
    ├→ game_duration_setting check
    └→ locked_alliances check
    ↓
VerificationResult created with all 8 checks
    ↓
replay_details_embed._format_verification_results()
    ↓
Discord Embed with all 8 verification lines
    ↓
Player sees complete verification report
```

---

## Verification Results Scenarios

### All Checks Pass
```
☑️ Replay Verification

- ✅ **Races Match:** Played races correspond to queued races.
- ✅ **Map Matches:** Correct map was used.
- ✅ **Timestamp Valid:** Match started within 5.2 minutes of assignment (within 20-minute window).
- ✅ **No Observers:** No unauthorized observers detected.
- ✅ **Privacy:** `Normal`
- ✅ **Game Speed:** `Faster`
- ✅ **Duration:** `Unlimited`
- ✅ **Locked Alliances:** `Yes`

✅ **Verification Complete:** All checks passed. Please report the match result manually.
```

### Some Checks Fail
```
☑️ Replay Verification

- ✅ **Races Match:** Played races correspond to queued races.
- ✅ **Map Matches:** Correct map was used.
- ✅ **Timestamp Valid:** Match started within 5.2 minutes of assignment (within 20-minute window).
- ✅ **No Observers:** No unauthorized observers detected.
- ❌ **Privacy:** Expected `Normal`, but found `Public`.
- ✅ **Game Speed:** `Faster`
- ✅ **Duration:** `Unlimited`
- ⚠️ **Locked Alliances:** Expected `Yes`, but found `No`.

⚠️ **Verification Issues:** One or more checks failed. Please review the issues above and ensure match parameters are correct for future games.
```

---

## Testing

Created comprehensive test suite: `tests/test_game_settings_verification.py`

All tests passing (EXIT CODE 0):
- ✓ Configuration constants defined correctly
- ✓ GameSettingVerificationDetail type structure correct
- ✓ VerificationResult includes all 4 game setting checks
- ✓ Game setting verification results can be created
- ✓ Failure scenarios handled correctly
- ✓ Embed formatting logic compatible with new checks

---

## Files Modified

1. **`src/backend/core/config.py`**
   - Added 4 configuration constants for expected game settings

2. **`src/backend/core/types.py`**
   - Added `GameSettingVerificationDetail` TypedDict
   - Updated `VerificationResult` with 4 new fields

3. **`src/backend/services/match_completion_service.py`**
   - Updated imports to include new types and config constants
   - Added `_verify_game_setting()` helper method
   - Updated `verify_replay_data()` to verify and include game settings

4. **`src/bot/components/replay_details_embed.py`**
   - Updated `_format_verification_results()` to format game setting checks
   - Updated overall verification status logic

5. **`tests/test_game_settings_verification.py`** (NEW)
   - Comprehensive test suite for game settings verification

---

## Key Properties

1. **Type Safe**: All verification results use proper TypedDict definitions
2. **Centralized Config**: Expected values configurable from one location
3. **Consistent Pattern**: Game setting verification follows the same pattern as existing checks
4. **Clear Feedback**: Discord embed clearly shows pass/fail for each setting
5. **Non-breaking**: Existing replay verification logic unchanged; new checks are additive
6. **Detailed Logging**: Backend logs all verification results for debugging

---

## How to Use

When a replay is uploaded:

1. **Parse Phase**: Replay settings are extracted from the replay file
2. **Verification Phase**: `verify_replay_data()` is called and checks all 8 items including the 4 new game settings
3. **Display Phase**: Discord embed shows all 8 verification results with clear indicators
4. **Response**: Players see whether their replay meets all requirements

---

## Configuration Customization

To change the expected game settings, only modify `src/backend/core/config.py`:

```python
EXPECTED_GAME_PRIVACY = "Normal"  # Change this value
EXPECTED_GAME_SPEED = "Faster"     # Change this value
EXPECTED_GAME_DURATION = "Unlimited"  # Change this value
EXPECTED_LOCKED_ALLIANCES = "Yes"  # Change this value
```

All downstream code will automatically use the new expected values.

---

## Error Handling

If a replay is missing a game setting field (value is `None`):
- The check will fail with `"found": None`
- The error message will show: `Expected `Normal`, but found `None`.`
- The overall verification will include this failed check

---

## Future Extensions

The `_verify_game_setting()` helper method is generic and can be reused for:
- Additional game setting validations
- Other replay field validations
- Configuration-driven verification logic
