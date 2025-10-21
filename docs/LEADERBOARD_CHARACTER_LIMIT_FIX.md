# Leaderboard Character Limit Fix

**Date**: October 20, 2025  
**Issue**: Discord's 1024 character limit per field exceeded due to emotes  
**Solution**: Split players into chunks of 10 per field  
**Status**: ✅ **IMPLEMENTED**

---

## Problem

Discord has a **1024 character limit per embed field**. With race emotes, flag emotes, and player names, the leaderboard was hitting this limit and getting truncated.

**Example of long lines**:
```
- 1. <:bw_terran:123456789> 🇺🇸 PlayerName123 (2000)
- 2. <:sc2_zerg:987654321> 🇰🇷 AnotherPlayer (1950)
- 3. <:bw_protoss:456789123> 🇩🇪 GermanPlayer (1900)
```

Each line can be 50-80 characters, so 20 players = 1000-1600 characters (over the limit).

---

## Solution

### Split Into Multiple Fields

**Before** (Single field):
```
**Leaderboard**
- 1. 🏗️ 🇺🇸 Player1 (2000)
- 2. 🐛 🇰🇷 Player2 (1950)
... (truncated at 1024 chars)
```

**After** (Multiple fields):
```
**Leaderboard**
- 1. 🏗️ 🇺🇸 Player1 (2000)
- 2. 🐛 🇰🇷 Player2 (1950)
... (10 players)

**Leaderboard (11-20)**
- 11. 🔮 🇩🇪 Player11 (1800)
- 12. 🏗️ 🇫🇷 Player12 (1750)
... (10 players)
```

### Implementation

```python
# Split players into chunks of 10 to avoid Discord's 1024 character limit
players_per_field = 10
for i in range(0, len(formatted_players), players_per_field):
    chunk = formatted_players[i:i + players_per_field]
    field_text = ""
    
    for player in chunk:
        # Get race emote and flag emote
        race_emote = self._get_race_emote(player.get('race_code', ''))
        flag_emote = self._get_flag_emote(player.get('country', ''))
        
        # Format: - 1. {race_emote} {flag_emote} Master88 ({MMR number})
        field_text += f"- {player['rank']}. {race_emote} {flag_emote} {player['player_id']} ({player['mmr']})\n"
    
    # Create field name based on position
    if i == 0:
        field_name = "Leaderboard"
    else:
        start_rank = chunk[0]['rank']
        end_rank = chunk[-1]['rank']
        field_name = f"Leaderboard ({start_rank}-{end_rank})"
    
    embed.add_field(
        name=field_name,
        value=field_text,
        inline=False
    )
```

---

## Field Naming Strategy

### First Field
- **Name**: `Leaderboard`
- **Content**: Ranks 1-10

### Subsequent Fields
- **Name**: `Leaderboard (11-20)`, `Leaderboard (21-30)`, etc.
- **Content**: Next 10 players

### Benefits
✅ **Clear Continuation**: Users can see the ranking continues  
✅ **No Truncation**: All players display properly  
✅ **Visual Continuity**: Fields flow naturally  
✅ **Discord Compliant**: Stays under character limits  

---

## Character Count Analysis

### Per Player Line
```
- 1. <:bw_terran:123456789> 🇺🇸 PlayerName123 (2000)
```
- **Length**: ~50-80 characters
- **With 10 players**: 500-800 characters
- **Safety margin**: Well under 1024 limit

### Field Limits
- **Discord limit**: 1024 characters per field
- **Our usage**: ~500-800 characters per field
- **Safety margin**: 200-500 characters remaining

---

## Files Modified

1. **`src/bot/commands/leaderboard_command.py`**
   - Added chunking logic for players
   - Dynamic field naming based on rank ranges
   - Maintains all existing functionality

---

## Testing Scenarios

### Scenario 1: 5 Players
- **Result**: Single "Leaderboard" field
- **Content**: All 5 players in one field

### Scenario 2: 15 Players  
- **Result**: Two fields
- **Field 1**: "Leaderboard" (ranks 1-10)
- **Field 2**: "Leaderboard (11-15)" (ranks 11-15)

### Scenario 3: 25 Players
- **Result**: Three fields
- **Field 1**: "Leaderboard" (ranks 1-10)
- **Field 2**: "Leaderboard (11-20)" (ranks 11-20)
- **Field 3**: "Leaderboard (21-25)" (ranks 21-25)

---

## Benefits

✅ **Discord Compliant**: Stays under character limits  
✅ **Visual Clarity**: Clear separation between player groups  
✅ **Maintains Emotes**: All race and flag emotes still display  
✅ **Scalable**: Works for any number of players  
✅ **No Data Loss**: All players still shown  

---

## Notes

- **Chunk size**: 10 players per field (optimal balance)
- **Field naming**: Dynamic based on rank ranges
- **Backward compatible**: No changes to backend services
- **Performance**: Minimal overhead for chunking logic

The leaderboard will now display properly without hitting Discord's field character limits!
