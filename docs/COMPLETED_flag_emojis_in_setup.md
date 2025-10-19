# Completed: Flag Emojis in /setup and /setcountry Commands

## Summary

Added flag emojis to country selections in the `/setup` and `/setcountry` commands, including proper support for the special XX (Nonrepresenting) and ZZ (Other) flags.

---

## What Was Implemented

### 1. `/setup` Command - Country Dropdowns

**Files Modified:**
- `src/bot/interface/commands/setup_command.py`

**Changes:**
- Added flag emojis to `CountryPage1Select` dropdown (countries 1-25)
- Added flag emojis to `CountryPage2Select` dropdown (countries 26-50)
- Uses `get_flag_emote()` function to get appropriate emoji for each country

**Visual Result:**
```
Country Dropdown (Page 1):
🇺🇸 United States
🇨🇦 Canada
🇰🇷 Korea, Republic of
🇯🇵 Japan
...
[Custom XX Emote] Nonrepresenting
[Custom ZZ Emote] Other
```

### 2. `/setcountry` Command - Confirmation Embeds

**Files Modified:**
- `src/bot/interface/commands/setcountry_command.py`

**Changes:**
- Added flag emoji to preview confirmation embed
- Added flag emoji to post-confirmation success embed
- Imported `get_flag_emote` function

**Visual Result:**
```
Preview Confirmation:
🗺️ Country of Citizenship/Nationality
🇺🇸 United States

After Confirmation:
🗺️ Selected Country
🇺🇸 United States (US)
```

---

## How It Works

### Flag Emoji System

The `get_flag_emote()` function in `discord_utils.py` handles two types of flags:

1. **Standard Country Codes (US, CA, KR, etc.)**
   - Returns Unicode flag emoji (🇺🇸, 🇨🇦, 🇰🇷)
   - Generated from 2-letter country codes
   - Works automatically for all standard ISO country codes

2. **Special Codes (XX, ZZ)**
   - Returns custom Discord emotes from `emotes.json`
   - XX (Nonrepresenting): `<:xx:1425037165414322186>`
   - ZZ (Other): `<:zz:1425037183403823114>`
   - These are uploaded as custom emotes to your Discord server

### Integration in Dropdowns

```python
# In CountryPage1Select and CountryPage2Select
from src.bot.utils.discord_utils import get_flag_emote

options = [
    discord.SelectOption(
        label=country['name'],
        value=country['code'],
        emoji=get_flag_emote(country['code']),  # ← Flag emoji added here
        default=(country['code'] == selected_country)
    )
    for country in page_countries
]
```

Discord automatically displays the emoji next to the label in the dropdown.

### Integration in Embeds

```python
# In setcountry_command
flag_emoji = get_flag_emote(country_code)
embed.add_field(
    name=":map: **Country of Citizenship/Nationality**",
    value=f"{flag_emoji} {country['name']}",  # ← Flag emoji added here
    inline=False
)
```

---

## Testing

### Test Script Created

**File:** `test_flag_emotes.py`

Run it to verify:
```powershell
python test_flag_emotes.py
```

**Output:**
```
======================================================================
FLAG EMOTE TEST FOR /SETUP COMMAND
======================================================================

[Standard Countries - Unicode Flags]
   [OK] US: Unicode flag emoji (len=2)
   [OK] CA: Unicode flag emoji (len=2)
   [OK] KR: Unicode flag emoji (len=2)
   ...

[Special Codes - Custom Emotes]
   [OK] XX (Nonrepresenting): <:xx:1425037165414322186>
        Custom emote format confirmed
   [OK] ZZ (Other): <:zz:1425037183403823114>
        Custom emote format confirmed
```

### Manual Testing in Discord

1. **Test /setup command:**
   - Run `/setup`
   - Navigate to country selection
   - Verify flag emojis appear in both dropdown pages
   - Verify XX and ZZ have custom emotes

2. **Test /setcountry command:**
   - Run `/setcountry` and type a country name
   - Verify flag emoji appears in preview embed
   - Confirm change
   - Verify flag emoji appears in success message

---

## Country Data

All country data is in `data/misc/countries.json`:

**Standard Countries:** 240+ countries with standard ISO codes
**Special Codes:**
```json
{
  "code": "XX",
  "name": "Nonrepresenting",
  "common": false
},
{
  "code": "ZZ",
  "name": "Other",
  "common": true
}
```

---

## Custom Emotes Configuration

Custom emotes are defined in `data/misc/emotes.json`:

```json
{
  "name": "flag_xx",
  "markdown": "<:xx:1425037165414322186>"
},
{
  "name": "flag_zz",
  "markdown": "<:zz:1425037183403823114>"
}
```

**Requirements:**
- These emotes must be uploaded to your Discord server
- The emote IDs must match the IDs in `emotes.json`
- Users must be members of the server that has these emotes

---

## User Experience Improvements

### Before
```
Dropdown:
- United States
- Canada
- Korea, Republic of
- Nonrepresenting
- Other
```

### After
```
Dropdown:
🇺🇸 United States
🇨🇦 Canada
🇰🇷 Korea, Republic of
[XX Icon] Nonrepresenting
[ZZ Icon] Other
```

**Benefits:**
- ✅ Faster visual scanning - flags are instantly recognizable
- ✅ More professional appearance
- ✅ Consistent with Discord's design language
- ✅ Special XX/ZZ codes have distinctive custom icons
- ✅ Accessibility - flags supplement text, don't replace it

---

## Technical Details

### Discord SelectOption Emoji Parameter

Discord.py supports the `emoji` parameter in `SelectOption`:
- Accepts Unicode emoji strings (e.g., "🇺🇸")
- Accepts custom emoji format (e.g., "<:name:id>")
- Automatically renders in the dropdown UI

### Why Local Imports?

```python
# Import inside __init__ to avoid circular imports
from src.bot.utils.discord_utils import get_flag_emote
```

The import is done inside the `__init__` method to avoid potential circular dependency issues between modules.

---

## Files Modified

1. ✅ `src/bot/interface/commands/setup_command.py`
   - `CountryPage1Select.__init__()` - Added emoji to dropdown
   - `CountryPage2Select.__init__()` - Added emoji to dropdown

2. ✅ `src/bot/interface/commands/setcountry_command.py`
   - Added `get_flag_emote` import
   - Preview embed - Added flag emoji to country display
   - Confirmation embed - Added flag emoji to success message

3. ✅ Created `test_flag_emotes.py` - Test script for verification

---

## Related Existing Code

The following were already in place and used by this implementation:

- `src/bot/utils/discord_utils.py` - `get_flag_emote()` function
- `data/misc/emotes.json` - Custom emote definitions
- `data/misc/countries.json` - Country data including XX and ZZ

---

## Next Steps (Optional Enhancements)

If you want to further enhance country/flag displays:

1. **Add flags to leaderboard** - Show flag next to player country in leaderboard
2. **Add flags to profile command** - When you implement `/profile`, show flag there
3. **Add flags to match embeds** - Show player flags in match found/result embeds
4. **Add region flags** - Create custom emotes for server regions (Americas, Europe, Asia, etc.)

These would use the same `get_flag_emote()` function pattern.

---

## Verification

All changes are:
- ✅ Implemented
- ✅ Tested (test script passes)
- ✅ Linter clean (no errors)
- ✅ Production ready

The `/setup` and `/setcountry` commands now display beautiful flag emojis for all countries, including proper custom emotes for XX (Nonrepresenting) and ZZ (Other)! 🎌

