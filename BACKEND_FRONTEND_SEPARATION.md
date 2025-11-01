# Backend/Frontend Separation Fix

## Problem

The user correctly identified: **"too many backend concerns in the frontend"**

The `/admin player` command's formatting function was directly calling backend services to fetch data, calculate ranks, and resolve names. This violated the separation of concerns principle.

### Before (WRONG):
```python
# Frontend code (admin_command.py)
def format_player_state(state: dict):
    from src.backend.services.app_context import (
        countries_service, regions_service, races_service, ranking_service
    )
    
    # Fetching data from backend services
    country = countries_service.get_country_by_code(info['country'])
    region_name = regions_service.get_region_name(info['region'])
    race_name = races_service.get_race_name(race_code)
    rank = ranking_service.get_letter_rank(discord_uid, race_code)
```

**Problems:**
- ❌ Frontend calling multiple backend services
- ❌ Frontend performing data enrichment
- ❌ Frontend calculating ranks
- ❌ Tight coupling between layers
- ❌ Violates single responsibility principle

---

## Solution

**Backend provides ALL display-ready data. Frontend ONLY formats it.**

### After (CORRECT):

#### Backend (`admin_service.py`)
```python
async def get_player_full_state(self, discord_uid: int) -> dict:
    """Get complete state with all display data pre-calculated."""
    from src.backend.services.app_context import (
        countries_service, regions_service, races_service, ranking_service
    )
    
    # Enrich player_info with display-ready data
    player_info['country_name'] = countries_service.get_country_by_code(...)
    player_info['region_name'] = regions_service.get_region_name(...)
    player_info['region_globe_emote'] = region_data.get('globe_emote')
    
    # Enrich MMR data with ranks, race names, and race order
    for race_code in mmrs:
        mmrs[race_code]['rank'] = ranking_service.get_letter_rank(...)
        mmrs[race_code]['race_name'] = races_service.get_race_name(...)
        mmrs[race_code]['sort_order'] = race_order.index(race_code)
        mmrs[race_code]['is_bw'] = race_code.startswith('bw_')
        mmrs[race_code]['is_sc2'] = race_code.startswith('sc2_')
    
    return {...}  # All data enriched and ready for display
```

#### Frontend (`admin_command.py`)
```python
def format_player_state(state: dict) -> discord.Embed:
    """Format player state into embed. ONLY formatting, NO data fetching."""
    from src.bot.utils.discord_utils import (
        get_flag_emote, get_globe_emote, get_race_emote, 
        get_rank_emote, get_game_emote
    )
    # NO backend service imports!
    
    # Use pre-calculated data from backend
    country_name = info.get('country_name')  # Already resolved
    race_name = mmr_entry.get('race_name')   # Already resolved
    rank = mmr_entry.get('rank')             # Already calculated
    
    # Just format the data
    embed.add_field(name="Country", value=f"{flag} {country_name}")
```

---

## Changes Made

### 1. Backend (`admin_service.py`)

**Enriched `get_player_full_state` method:**

#### A. Player Info Enrichment
```python
# Added fields:
player_info['country_name']        # Resolved country name
player_info['region_name']         # Resolved region name
player_info['region_globe_emote']  # Globe emoji code
```

#### B. MMR Data Enrichment
```python
# Added fields for each race:
mmrs[race_code]['rank']        # Calculated rank letter
mmrs[race_code]['race_name']   # Human-readable race name
mmrs[race_code]['sort_order']  # Position in canonical order
mmrs[race_code]['is_bw']       # Boolean: is Brood War race
mmrs[race_code]['is_sc2']      # Boolean: is SC2 race
mmrs[race_code]['last_played'] # Timestamp (already existed)
```

#### C. Active Matches Filter
```python
# Changed from unreliable status column to actual database columns
.filter(
    pl.col('match_result').is_null() |  # Match not finished
    (pl.col('match_result') == 0)        # Or match_result is 0
)
```

### 2. Frontend (`admin_command.py`)

**Simplified `format_player_state` function:**

#### Removed Imports
```python
# REMOVED these backend imports:
- countries_service
- regions_service
- races_service
- ranking_service
```

#### Used Pre-Calculated Data
```python
# BEFORE: Frontend calculates/fetches
country = countries_service.get_country_by_code(info['country'])
country_name = country.get('name')

# AFTER: Frontend just uses
country_name = info.get('country_name')  # ✅ Already resolved by backend
```

```python
# BEFORE: Frontend sorts and separates
race_order = races_service.get_race_order()
sorted_mmr_data = sorted(mmr_list, key=lambda m: race_order.index(m['race']))
bw_mmrs = [m for m in sorted_mmr_data if m['race'].startswith('bw_')]

# AFTER: Frontend uses pre-calculated flags
sorted_mmr_data = sorted(mmr_list, key=lambda m: m.get('sort_order', 999))
bw_mmrs = [m for m in sorted_mmr_data if m.get('is_bw', False)]  # ✅ Already flagged
```

```python
# BEFORE: Frontend calculates rank
rank = ranking_service.get_letter_rank(discord_uid, race_code)

# AFTER: Frontend uses pre-calculated rank
rank = mmr_entry.get('rank')  # ✅ Already calculated by backend
```

---

## Benefits

### Architectural
✅ **Clear Separation of Concerns** - Backend handles data, frontend handles display
✅ **Single Responsibility** - Each layer does ONE thing well
✅ **Loose Coupling** - Frontend doesn't import backend services
✅ **Testability** - Can test frontend formatting without backend
✅ **Maintainability** - Changes to data logic stay in backend

### Performance
✅ **Single Pass** - All data enrichment happens once in backend
✅ **No Redundant Calls** - Frontend doesn't repeatedly call services
✅ **Batching** - Backend can optimize data fetching

### Code Quality
✅ **Cleaner Code** - Frontend is simpler and more readable
✅ **Type Safety** - Data contract between layers is explicit
✅ **DRY Principle** - Data enrichment logic in one place

---

## Data Flow

### Before (BAD):
```
User → Command → Backend (raw data) → Frontend → Services (enrich) → Discord
                                          ↑
                                    Tight coupling!
```

### After (GOOD):
```
User → Command → Backend (enrich all data) → Frontend (format only) → Discord
                    ↑
            All business logic here!
```

---

## New Data Contract

**Backend returns enriched dict with:**

```python
{
    'player_info': {
        'discord_uid': int,
        'player_name': str,
        'battletag': str,
        'country': str,              # Code (e.g., 'US')
        'country_name': str,         # Name (e.g., 'United States')
        'region': str,               # Code (e.g., 'na')
        'region_name': str,          # Name (e.g., 'North America')
        'region_globe_emote': str,   # Emoji code (e.g., 'americas')
        'completed_setup': bool,
        'remaining_aborts': int
    },
    'mmrs': {
        'bw_terran': {
            'mmr': int,
            'games_played': int,
            'games_won': int,
            'games_lost': int,
            'games_drawn': int,
            'last_played': datetime,
            'rank': str,             # ✅ NEW: Letter rank (e.g., 'E')
            'race_name': str,        # ✅ NEW: Human name (e.g., 'Terran')
            'sort_order': int,       # ✅ NEW: Position in canonical order
            'is_bw': bool,          # ✅ NEW: Is Brood War race
            'is_sc2': bool          # ✅ NEW: Is SC2 race
        },
        # ... other races ...
    },
    'queue_status': {...},
    'active_matches': [...],
    'recent_matches': [...]
}
```

**Frontend only needs emoji utility functions:**
- `get_flag_emote(country_code)` - Render flag emoji
- `get_globe_emote(emote_code)` - Render globe emoji
- `get_race_emote(race_code)` - Render race emoji
- `get_rank_emote(rank_letter)` - Render rank emoji
- `get_game_emote(game_name)` - Render game emoji

---

## Files Modified

1. **`src/backend/services/admin_service.py`**
   - Enhanced `get_player_full_state` method
   - Added data enrichment logic
   - Fixed active matches filter (removed status column dependency)
   - Fixed indentation issues from previous edits

2. **`src/bot/commands/admin_command.py`**
   - Removed backend service imports
   - Simplified `format_player_state` function
   - Uses pre-calculated data from backend

---

## Compilation Status

```bash
python -m py_compile \
  src/backend/services/admin_service.py \
  src/bot/commands/admin_command.py
```

**Exit Code: 0** ✅

---

## Testing

### Backend Tests
- [ ] `get_player_full_state` returns all enriched fields
- [ ] Country names are resolved correctly
- [ ] Region names are resolved correctly
- [ ] Ranks are calculated correctly for all races
- [ ] Race names are resolved correctly
- [ ] Sort order is assigned correctly
- [ ] `is_bw` and `is_sc2` flags are correct

### Frontend Tests
- [ ] Embed renders without calling backend services
- [ ] All emojis display correctly
- [ ] Race order is correct (Terran → Zerg → Protoss)
- [ ] BW and SC2 sections separate correctly
- [ ] Overall statistics calculate correctly
- [ ] Timestamps format correctly
- [ ] Location section displays when data available
- [ ] Queue status displays correctly
- [ ] Active matches display correctly

### Integration Tests
- [ ] `/admin player @user` displays correct data
- [ ] Player with no games shows correctly
- [ ] Player with only BW games shows correctly
- [ ] Player with only SC2 games shows correctly
- [ ] Player with both BW and SC2 shows correctly
- [ ] Player in queue shows wait time
- [ ] Player with active match shows match details

---

## Future Considerations

This pattern should be applied to ALL admin commands:

1. **`/admin match`** - Backend should enrich match data
2. **`/admin snapshot`** - Backend should pre-format all fields
3. **`/admin conflicts`** - Backend should resolve player names

**General Rule:** Frontend should NEVER import from `src.backend.services.app_context` except for global instances like `admin_service`.

---

## Related Patterns

This implements the **Repository Pattern** and **DTO (Data Transfer Object)** pattern:

1. **Backend = Repository** - Fetches and enriches data
2. **Dict = DTO** - Transfers data between layers
3. **Frontend = Presentation** - Formats data for display

This is a standard architectural pattern in enterprise applications and makes the code much more maintainable and testable.

