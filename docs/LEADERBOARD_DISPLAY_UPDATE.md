# Leaderboard Display Update

**Date**: October 20, 2025  
**Request**: Update leaderboard display format to show race emotes and flag emotes  
**Status**: ✅ **IMPLEMENTED**

---

## Changes Made

### 1. Removed Triple Backticks (`src/bot/commands/leaderboard_command.py`)

**Before**:
```python
leaderboard_text = "```\n"
for player in formatted_players:
    leaderboard_text += f"{player['rank']:2d}. {player['player_id']} - {player['mmr']} MMR ({player['race']}, {player['country']})\n"
leaderboard_text += "```"
```

**After**:
```python
leaderboard_text = ""
for player in formatted_players:
    # Get race emote and flag emote
    race_emote = self._get_race_emote(player.get('race_code', ''))
    flag_emote = self._get_flag_emote(player.get('country', ''))
    
    # Format: - 1. {race_emote} {flag_emote} Master88 ({MMR number})
    leaderboard_text += f"- {player['rank']}. {race_emote} {flag_emote} {player['player_id']} ({player['mmr']})\n"
```

### 2. Updated Display Format

**Before**:
```
` 1. Master89 - 2000 MMR (BW Terran, BG)`
```

**After**:
```
- 1. 🏗️ 🇧🇬 Master88 (2000)
```

### 3. Added Helper Methods (`src/bot/commands/leaderboard_command.py`)

```python
def _get_race_emote(self, race_code: str) -> str:
    """Get the Discord emote for a race code."""
    from src.bot.utils.discord_utils import get_race_emote
    return get_race_emote(race_code)

def _get_flag_emote(self, country_code: str) -> str:
    """Get the Discord flag emote for a country code."""
    from src.bot.utils.discord_utils import get_flag_emote
    return get_flag_emote(country_code)
```

### 4. Enhanced Backend Data (`src/backend/services/leaderboard_service.py`)

Added `race_code` field to formatted player data:

```python
formatted_players.append({
    "rank": rank,
    "player_id": player.get('player_id', 'Unknown'),
    "mmr": mmr_display,
    "race": self.race_service.format_race_name(player.get('race', 'Unknown')),
    "race_code": player.get('race', 'Unknown'),  # Include race code for emotes
    "country": player.get('country', 'Unknown')
})
```

---

## Technical Details

### Race Emotes
- Uses `get_race_emote()` from `discord_utils.py`
- Looks up race codes like `bw_terran`, `sc2_zerg` in `emotes.json`
- Returns Discord custom emote markdown (e.g., `<:bw_terran:123456789>`)

### Flag Emotes
- Uses `get_flag_emote()` from `discord_utils.py`
- For standard country codes (US, KR, etc.): Returns Unicode flag emojis (🇺🇸, 🇰🇷)
- For special codes (XX, ZZ): Returns custom emotes from `emotes.json`

### Display Format
- **Rank**: `1.`, `2.`, etc.
- **Race Emote**: Custom Discord emote for race
- **Flag Emote**: Unicode flag or custom emote for country
- **Player Name**: Player ID
- **MMR**: MMR value in parentheses

---

## Example Output

### Before
```
```
 1. Master89 - 2000 MMR (BW Terran, BG)
 2. Player123 - 1950 MMR (SC2 Zerg, US)
 3. TestUser - 1900 MMR (BW Protoss, KR)
```
```

### After
```
- 1. 🏗️ 🇧🇬 Master89 (2000)
- 2. 🐛 🇺🇸 Player123 (1950)
- 3. 🔮 🇰🇷 TestUser (1900)
```

---

## Files Modified

1. **`src/bot/commands/leaderboard_command.py`**
   - Removed triple backticks from leaderboard display
   - Updated format to use race and flag emotes
   - Added helper methods for emote retrieval

2. **`src/backend/services/leaderboard_service.py`**
   - Added `race_code` field to formatted player data
   - Maintains backward compatibility with existing `race` field

---

## Benefits

✅ **Visual Appeal**: Race and flag emotes make leaderboard more engaging  
✅ **Space Efficient**: Removed verbose text descriptions  
✅ **Emote Support**: No more triple backticks blocking emote display  
✅ **Consistent Format**: Matches other parts of the bot that use emotes  
✅ **Backward Compatible**: Existing functionality preserved  

---

## Testing

The changes should be tested to verify:

1. **Race Emotes Display**: Verify correct race emotes show for each race
2. **Flag Emotes Display**: Verify correct flag emotes show for each country
3. **Format Consistency**: Ensure all leaderboard entries follow the new format
4. **Pagination**: Verify emotes work across all pages
5. **Filtering**: Verify emotes work with race/country filters

---

## Notes

- Race emotes are loaded from `data/misc/emotes.json`
- Flag emotes use Unicode for standard countries, custom emotes for special cases
- The format is more compact and visually appealing
- No breaking changes to existing functionality
