# Leaderboard Alignment and Dynamic Titles Fix

**Date**: October 20, 2025  
**Request**: Even spacing between rank and race emote, dynamic field titles based on page  
**Status**: ✅ **IMPLEMENTED**

---

## Changes Made

### 1. Fixed Left-Side Alignment

**Before** (uneven spacing):
```
- 1. 🏗️ 🇧🇬 Master89 (2000)
- 2. 🐛 ❓ Competitive765 (1985)
- 10. 🔮 🇫🇷 Master474 (1981)
```

**After** (even spacing):
```
-  1. 🏗️ 🇧🇬 Master89 (2000)
-  2. 🐛 ❓ Competitive765 (1985)
- 10. 🔮 🇫🇷 Master474 (1981)
```

**Key Changes**:
- **Rank padding**: `{player['rank']:2d}` ensures 2-digit width for all ranks
- **Left alignment**: Consistent spacing between rank and race emote
- **MMR untouched**: Kept original MMR formatting as requested

### 2. Dynamic Field Titles Based on Page

**Before** (static titles):
```
**Leaderboard (1-10)**  # Always showed 1-10
**Leaderboard (11-20)** # Always showed 11-20
```

**After** (dynamic titles):
```
**Leaderboard (1-20)**   # Page 1: ranks 1-20
**Leaderboard (21-40)**  # Page 2: ranks 21-40
**Leaderboard (41-60)**  # Page 3: ranks 41-60
```

**Implementation**:
```python
# Create field name based on position and current page
if i == 0:
    # First field: show range based on current page and page size
    current_page = self.leaderboard_service.current_page
    start_rank = (current_page - 1) * page_size + 1
    end_rank = min(start_rank + players_per_field - 1, current_page * page_size)
    field_name = f"Leaderboard ({start_rank}-{end_rank})"
else:
    # Subsequent fields: blank name for visual continuity
    field_name = ""
```

---

## Page Size and Current Page Logic

### Page 1 (page_size=20)
- **Field 1**: `Leaderboard (1-20)`
- **Field 2**: `Leaderboard (21-40)` (if more than 20 players)

### Page 2 (page_size=20)
- **Field 1**: `Leaderboard (21-40)`
- **Field 2**: `Leaderboard (41-60)` (if more than 40 players)

### Page 3 (page_size=20)
- **Field 1**: `Leaderboard (41-60)`
- **Field 2**: `Leaderboard (61-80)` (if more than 60 players)

### Formula
- **Start rank**: `(current_page - 1) * page_size + 1`
- **End rank**: `min(start_rank + players_per_field - 1, current_page * page_size)`

---

## Visual Improvements

### Alignment
- **Rank**: 2-digit padding (` 1`, ` 2`, `10`, `11`)
- **Spacing**: Consistent gap between rank and race emote
- **MMR**: Unchanged (kept original formatting)

### Field Titles
- **First field**: Dynamic range based on current page
- **Subsequent fields**: Blank for visual continuity
- **Responsive**: Adapts to any page size setting

---

## Example Outputs

### Page 1 (page_size=20)
```
**Leaderboard (1-20)**
-  1. 🏗️ 🇧🇬 Master89 (2000)
-  2. 🐛 ❓ Competitive765 (1985)
-  3. 🔮 🇫🇷 Master474 (1981)
... (up to rank 20)

**Leaderboard (21-40)**
- 21. 🏗️ 🇺🇸 Player21 (1600)
- 22. 🐛 🇰🇷 Player22 (1550)
... (up to rank 40)
```

### Page 2 (page_size=20)
```
**Leaderboard (21-40)**
- 21. 🏗️ 🇺🇸 Player21 (1600)
- 22. 🐛 🇰🇷 Player22 (1550)
... (up to rank 40)

**Leaderboard (41-60)**
- 41. 🔮 🇩🇪 Player41 (1400)
- 42. 🏗️ 🇫🇷 Player42 (1350)
... (up to rank 60)
```

---

## Benefits

✅ **Even Alignment**: Consistent spacing between rank and race emote  
✅ **Dynamic Titles**: Field titles respond to current page and page size  
✅ **MMR Preserved**: Kept original MMR formatting as requested  
✅ **Visual Continuity**: Subsequent fields blend seamlessly  
✅ **Responsive**: Works with any page size setting  

---

## Files Modified

1. **`src/bot/commands/leaderboard_command.py`**
   - Fixed rank padding for even left-side alignment
   - Added dynamic field title calculation based on current page
   - Maintained MMR formatting as requested

---

## Technical Details

### Rank Padding
```python
f"- {player['rank']:2d}. {race_emote} {flag_emote} {player['player_id']} ({player['mmr']})\n"
```
- `:2d` ensures 2-digit width with leading space for single digits
- Creates consistent spacing between rank and race emote

### Dynamic Title Calculation
```python
current_page = self.leaderboard_service.current_page
start_rank = (current_page - 1) * page_size + 1
end_rank = min(start_rank + players_per_field - 1, current_page * page_size)
```
- Calculates start rank based on current page and page size
- Ensures end rank doesn't exceed the page boundary
- Works with any page size setting

The leaderboard now has perfect left-side alignment and dynamic titles that respond to the current page and page size!
