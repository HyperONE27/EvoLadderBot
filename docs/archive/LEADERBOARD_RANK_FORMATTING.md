# Leaderboard Rank Formatting

**Date**: October 20, 2025  
**Request**: Surround rank numbers with single backticks and align spacing based on maximum rank  
**Status**: ✅ **IMPLEMENTED**

---

## Changes Made

### Before
```
-  1. 🏗️ 🇺🇸 Player1 (2000)
-  2. 🐛 🇰🇷 Player2 (1950)
- 10. 🔮 🇩🇪 Player10 (1900)
- 11. 🏗️ 🇫🇷 Player11 (1850)
```

### After
```
- ` 1.` 🏗️ 🇺🇸 Player1 (2000)
- ` 2.` 🐛 🇰🇷 Player2 (1950)
- `10.` 🔮 🇩🇪 Player10 (1900)
- `11.` 🏗️ 🇫🇷 Player11 (1850)
```

---

## Implementation Details

### Dynamic Padding Logic
```python
# Calculate the maximum rank number to determine padding width
max_rank = max(player['rank'] for player in formatted_players) if formatted_players else 0
rank_width = len(str(max_rank))

# Format rank with backticks and proper alignment
rank_padded = f"{player['rank']:>{rank_width}d}"
field_text += f"- `{rank_padded}.` {race_emote} {flag_emote} {player['player_id']} ({player['mmr']})\n"
```

### Alignment Examples

**For ranks 1-99 (2 digits max)**:
```
- ` 1.` 🏗️ 🇺🇸 Player1 (2000)
- ` 2.` 🐛 🇰🇷 Player2 (1950)
- `10.` 🔮 🇩🇪 Player10 (1900)
- `99.` 🏗️ 🇫🇷 Player99 (1000)
```

**For ranks 1-100 (3 digits max)**:
```
- `  1.` 🏗️ 🇺🇸 Player1 (2000)
- `  2.` 🐛 🇰🇷 Player2 (1950)
- ` 10.` 🔮 🇩🇪 Player10 (1900)
- `100.` 🏗️ 🇫🇷 Player100 (1000)
```

---

## Visual Benefits

### Before (Inconsistent Spacing)
```
-  1. 🏗️ 🇺🇸 Player1 (2000)
-  2. 🐛 🇰🇷 Player2 (1950)
- 10. 🔮 🇩🇪 Player10 (1900)  ← Misaligned
- 11. 🏗️ 🇫🇷 Player11 (1850)  ← Misaligned
```

### After (Consistent Spacing)
```
- ` 1.` 🏗️ 🇺🇸 Player1 (2000)
- ` 2.` 🐛 🇰🇷 Player2 (1950)
- `10.` 🔮 🇩🇪 Player10 (1900)  ← Aligned
- `11.` 🏗️ 🇫🇷 Player11 (1850)  ← Aligned
```

---

## Technical Implementation

### Rank Width Calculation
```python
# Find the maximum rank in the current page
max_rank = max(player['rank'] for player in formatted_players)

# Calculate the number of digits needed
rank_width = len(str(max_rank))

# Examples:
# max_rank = 20  → rank_width = 2  → " 1.", " 2.", "10.", "20."
# max_rank = 100 → rank_width = 3  → "  1.", "  2.", " 10.", "100."
```

### Formatting Logic
```python
# Right-align the rank number within the calculated width
rank_padded = f"{player['rank']:>{rank_width}d}"

# Surround with backticks and add period
field_text += f"- `{rank_padded}.` {race_emote} {flag_emote} {player['player_id']} ({player['mmr']})\n"
```

---

## Examples by Page Size

### Page 1 (Ranks 1-20)
```
**Leaderboard (1-10)**          **Leaderboard (11-20)**
- ` 1.` 🏗️ 🇺🇸 Player1 (2000)     - `11.` 🐛 🇰🇷 Player11 (1800)
- ` 2.` 🐛 🇰🇷 Player2 (1950)     - `12.` 🔮 🇩🇪 Player12 (1750)
- ` 3.` 🔮 🇩🇪 Player3 (1900)     - `13.` 🏗️ 🇫🇷 Player13 (1700)
- ` 4.` 🏗️ 🇫🇷 Player4 (1850)     - `14.` 🐛 🇨🇦 Player14 (1650)
- ` 5.` 🐛 🇨🇦 Player5 (1800)     - `15.` 🔮 🇦🇺 Player15 (1600)
- ` 6.` 🔮 🇦🇺 Player6 (1750)     - `16.` 🏗️ 🇧🇷 Player16 (1550)
- ` 7.` 🏗️ 🇧🇷 Player7 (1700)     - `17.` 🐛 🇮🇳 Player17 (1500)
- ` 8.` 🐛 🇮🇳 Player8 (1650)     - `18.` 🔮 🇮🇹 Player18 (1450)
- ` 9.` 🔮 🇮🇹 Player9 (1600)     - `19.` 🏗️ 🇪🇸 Player19 (1400)
- `10.` 🏗️ 🇪🇸 Player10 (1550)   - `20.` 🐛 🇳🇱 Player20 (1350)
```

### Page 5 (Ranks 81-100)
```
**Leaderboard (81-90)**         **Leaderboard (91-100)**
- `81.` 🏗️ 🇺🇸 Player81 (1200)    - `91.` 🐛 🇰🇷 Player91 (1000)
- `82.` 🐛 🇰🇷 Player82 (1150)    - `92.` 🔮 🇩🇪 Player92 (950)
- `83.` 🔮 🇩🇪 Player83 (1100)    - `93.` 🏗️ 🇫🇷 Player93 (900)
- `84.` 🏗️ 🇫🇷 Player84 (1050)    - `94.` 🐛 🇨🇦 Player94 (850)
- `85.` 🐛 🇨🇦 Player85 (1000)    - `95.` 🔮 🇦🇺 Player95 (800)
- `86.` 🔮 🇦🇺 Player86 (950)     - `96.` 🏗️ 🇧🇷 Player96 (750)
- `87.` 🏗️ 🇧🇷 Player87 (900)    - `97.` 🐛 🇮🇳 Player97 (700)
- `88.` 🐛 🇮🇳 Player88 (850)    - `98.` 🔮 🇮🇹 Player98 (650)
- `89.` 🔮 🇮🇹 Player89 (800)    - `99.` 🏗️ 🇪🇸 Player99 (600)
- `90.` 🏗️ 🇪🇸 Player90 (750)   - `100.` 🐛 🇳🇱 Player100 (550)
```

---

## Benefits

✅ **Consistent Alignment**: All rank numbers are properly aligned regardless of digit count  
✅ **Visual Clarity**: Backticks make rank numbers stand out  
✅ **Dynamic Padding**: Automatically adjusts to the highest rank on the current page  
✅ **Professional Look**: Clean, organized appearance  
✅ **Maintains Functionality**: All existing features preserved  

---

## Files Modified

1. **`src/bot/commands/leaderboard_command.py`**
   - Added dynamic rank width calculation
   - Implemented backtick formatting around rank numbers
   - Added right-alignment padding for consistent spacing

---

## Expected Results

The leaderboard now displays rank numbers with:
- **Single backticks** around each rank number
- **Consistent alignment** based on the maximum rank displayed
- **Professional formatting** that scales with rank numbers

Example output:
```
- ` 1.` 🏗️ 🇺🇸 Player1 (2000)
- ` 2.` 🐛 🇰🇷 Player2 (1950)
- `10.` 🔮 🇩🇪 Player10 (1900)
- `11.` 🏗️ 🇫🇷 Player11 (1850)
```

The leaderboard now has properly aligned rank numbers with backticks!
