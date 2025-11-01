# Admin Player Command Refactor

## Summary

Refactored the `/admin player` command embed to match the beautiful layout and styling of the `/profile` command, while preserving admin-specific functionality.

---

## Changes Made

### File: `src/bot/commands/admin_command.py`

#### 1. Refactored `format_player_state` Function

**Before:**
- Returned a dict with `'title'` and `'fields'`
- Plain text formatting with minimal emojis
- Separate inline fields for basic info, MMRs, queue status
- No overall statistics
- No rank/race emojis
- No Discord timestamp formatting

**After:**
- Returns a complete `discord.Embed` object
- Full profile-style layout with rich emojis and formatting
- Sections with proper spacing (`\u3164` spacers)
- Overall statistics with win rates
- Rank emojis, race emojis, game emojis, flag emojis
- Discord timestamps for last played dates
- Preserved admin-specific sections (Queue Status, Active Matches)

#### 2. Updated `admin_player` Command

**Before:**
```python
formatted = format_player_state(state)
embed = discord.Embed(
    title=formatted['title'],
    color=discord.Color.blue()
)
for field in formatted['fields']:
    embed.add_field(...)
```

**After:**
```python
embed = format_player_state(state)
await interaction.followup.send(embed=embed)
```

**Much cleaner!** The formatting function now handles all embed creation.

---

## New Embed Layout

### Structure

1. **Title**
   - Format: `{status_icon} [Admin] Player Profile: {player_name}`
   - Color: Green (completed setup) or Orange (incomplete setup)

2. **📋 Basic Information**
   - User ID (mention)
   - Player Name
   - BattleTag
   - Alt IDs (if any)
   - **Remaining Aborts** (admin-specific) ⚠️

3. **{globe_emote} Location**
   - Citizenship / Nationality (with flag emoji)
   - Region of Residence

4. **📈 Overall Statistics**
   - Total Games
   - Record (W-L-D)
   - Win Rate
   - Last Played (Discord timestamp)

5. **{bw_emote} Brood War MMR**
   - Per race:
     - Rank emoji + Race emoji + Race name
     - MMR value
     - W-L-D record with win rate
     - Last played (Discord timestamp)

6. **{sc2_emote} StarCraft II MMR**
   - Same format as Brood War section

7. **🎯 Queue Status** (admin-specific)
   - In Queue: ✅ Yes / ❌ No
   - Wait Time
   - Races selected

8. **⚔️ Active Matches** (admin-specific)
   - Match ID
   - Player's report
   - Opponent's report

---

## Key Features

### Emojis & Visual Styling

- ✅ Status icons based on setup completion
- 🅴 🅳 🅲 🅱 🅰 Rank emojis
- 🔴 🟢 🟡 Race emojis
- 🇰🇷 🇺🇸 🇩🇪 Flag emojis
- 🌐 🌏 🌎 Globe emojis
- 🎮 📀 Game emojis

### Data Formatting

- **Race Order:** Follows canonical order (Terran → Zerg → Protoss)
- **Game Separation:** BW and SC2 separated with spacers
- **Win Rates:** Displayed as percentages (e.g., `67.3%`)
- **Discord Timestamps:** Relative time display (e.g., "2 hours ago")
- **No Games Played:** Shows "No MMR • No games played" instead of 0s

### Admin-Specific Enhancements

- **Remaining Aborts:** Shows `X/3` format in Basic Information
- **Queue Status:** Real-time queue state with wait time
- **Active Matches:** Lists all ongoing matches with report states

---

## Example Output

```
✅ [Admin] Player Profile: HyperONE

📋 Basic Information
- User ID: @HyperONE
- Player Name: HyperONE
- BattleTag: HyperONE#1234
- Remaining Aborts: 3/3

🌐 Location
- Citizenship / Nationality: 🇺🇸 United States
- Region of Residence: North America

📈 Overall Statistics
- Total Games: 42
- Record: 28W-12L-2D
- Win Rate: 66.7%
- Last Played: 2 hours ago

🎮 Brood War MMR
- 🅴 🔴 Terran: 1534 MMR • 15W-5L-0D (75.0%)
  - Last Played: 2 hours ago
- 🅳 🟢 Zerg: 1489 MMR • 8W-4L-1D (61.5%)
  - Last Played: 3 days ago
- 🅲 🟡 Protoss: No MMR • No games played

📀 StarCraft II MMR
- 🅴 🔴 Terran: 1521 MMR • 5W-3L-1D (55.6%)
  - Last Played: 5 hours ago

🎯 Queue Status
In Queue: ❌ No

⚔️ Active Matches
(none)
```

---

## Benefits

### For Admins
✅ **Consistent UI** - Matches player-facing `/profile` command
✅ **More Information** - Overall statistics, win rates, last played
✅ **Better Readability** - Emojis and spacing improve scanning
✅ **Professional Look** - Polished, production-quality embeds

### For Code Quality
✅ **DRY Principle** - Reuses services from profile command
✅ **Single Responsibility** - `format_player_state` handles all formatting
✅ **Maintainability** - Changes to profile styling can easily propagate

---

## Technical Details

### Imports Added

```python
from src.bot.utils.discord_utils import (
    get_flag_emote, get_globe_emote, get_race_emote, 
    get_rank_emote, get_game_emote
)
from src.backend.services.app_context import (
    countries_service, regions_service, races_service, ranking_service
)
from datetime import timezone
```

### Services Used

- `countries_service` - Country name and flag lookup
- `regions_service` - Region name and globe emoji lookup
- `races_service` - Race names and canonical ordering
- `ranking_service` - Player rank calculation

### Embed Limits Respected

- Used spacer fields (`\u3164`) to avoid inline formatting issues
- Each section is a full-width field for clarity
- Text length is naturally limited by game data (unlikely to exceed Discord's 6000 char embed limit)

---

## Testing Checklist

- [ ] `/admin player @user` - View complete profile
- [ ] Player with no games - Shows "No MMR • No games played"
- [ ] Player with BW games only - Only BW section shown
- [ ] Player with SC2 games only - Only SC2 section shown
- [ ] Player with both BW and SC2 - Both sections shown with spacer
- [ ] Player in queue - Queue status shows wait time and races
- [ ] Player with active match - Match details displayed
- [ ] Player not found - Error embed shown
- [ ] All emojis render correctly - Ranks, races, flags, etc.
- [ ] Discord timestamps work - Relative time display

---

## Compilation Status

```bash
python -m py_compile src/bot/commands/admin_command.py
```

**Exit Code: 0** ✅

---

## Files Modified

1. `src/bot/commands/admin_command.py`
   - Refactored `format_player_state` function (240 lines)
   - Simplified `admin_player` command (26 → 18 lines)

**Total Lines Changed:** ~250

---

## Future Enhancements

### Potential Additions

1. **Player Avatar Thumbnail** - Add `embed.set_thumbnail()` with Discord avatar
2. **Recent Matches** - Show last 3 matches with results
3. **Match History Link** - Button to view full match history
4. **Quick Actions** - Buttons for common admin tasks (adjust MMR, reset aborts, etc.)
5. **Peak MMR Display** - Show historical peak for each race

### Style Consistency

Any future changes to `/profile` command styling should be mirrored in `/admin player` to maintain visual consistency across player and admin views.

