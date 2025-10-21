# Realistic Mock Data Generation

**Date**: October 20, 2025  
**Request**: Generate 250 players with 4 races each (1000 total combinations) using realistic values  
**Status**: ✅ **COMPLETED**

---

## Generated Data Summary

### 📊 Data Volume
- **Players**: 250
- **MMR Records**: 1000 (4 races per player)
- **Preferences**: 250
- **Total Combinations**: 1000 player-race combinations

### 🎯 Validation Compliance
- ✅ **Player Names**: All respect 3-12 character limit
- ✅ **MMR Values**: All within realistic ranges (800-2500)
- ✅ **Country Codes**: Real-world country codes
- ✅ **Regions**: Realistic StarCraft regions
- ✅ **Races**: All 6 races (BW + SC2)
- ✅ **Maps**: Realistic StarCraft map names
- ⚠️ **Duplicate Names**: 38 duplicates (acceptable for mock data)

---

## Realistic Data Features

### 🏆 Player Names
**Generated using realistic patterns:**
- **Single Words**: Pro, Ace, Star, King, Lord, Hero, Elite, Prime, Alpha, Beta, Gamma, Delta
- **Compound Names**: ProGamer, MasterKing, ChampionLord, LegendHero, ElitePrime, etc.
- **Length Distribution**: 3-12 characters (respects validation rules)
- **Examples**: `TeraHero`, `Count`, `MegaGiga`, `King`, `GigaTera`, `Peta`

### 🌍 Geographic Data
**Real-world country and region distribution:**
- **Countries**: 100+ real country codes (US, KR, CN, DE, FR, GB, CA, AU, etc.)
- **Regions**: 17 realistic StarCraft regions (NAE, NAW, EUW, EUE, KRJ, SEA, OCE, etc.)
- **Distribution**: Weighted toward major StarCraft regions

### 🎮 Race Distribution
**Each player has 4 races (randomly selected from 6 total):**
- **Brood War**: bw_terran, bw_protoss, bw_zerg
- **StarCraft 2**: sc2_terran, sc2_protoss, sc2_zerg
- **Coverage**: 1000 total player-race combinations

### 📈 MMR Distribution
**Realistic MMR ranges by race:**
- **Brood War**: 800-2400 MMR
- **StarCraft 2**: 1000-2500 MMR
- **Distribution**: Normal distribution with slight skew toward higher MMRs
- **Examples**: 1200-1800 MMR (most common), 2000+ MMR (elite players)

### 🎯 Game Statistics
**Realistic game counts and win rates:**
- **Games Played**: 10-200+ games (correlates with MMR)
- **Win Rate**: 5%-95% (correlates with MMR)
- **Draws**: 0-5 games (realistic for RTS)
- **Formula**: Higher MMR = more games + higher win rate

### 🗺️ Map Preferences
**Realistic veto patterns:**
- **Vetoes**: 0-3 maps per player (most have 1-2)
- **Maps**: 35 realistic StarCraft maps
- **Popular Vetoes**: Fighting Spirit, Circuit Breaker, Neo, Khione, Pylon, Arkanoid

---

## Data Structure

### Players Table
```json
{
  "discord_uid": 100000000,
  "discord_username": "Player1",
  "player_name": "TeraHero",
  "battletag": "TeraHero#1234",
  "country": "NG",
  "region": "AFR",
  "accepted_tos": true,
  "completed_setup": true
}
```

### MMR Records
```json
{
  "discord_uid": 100000000,
  "player_name": "TeraHero",
  "race": "bw_terran",
  "mmr": 1850,
  "games_played": 45,
  "games_won": 32,
  "games_lost": 11,
  "games_drawn": 2
}
```

### Preferences
```json
{
  "discord_uid": 100000000,
  "last_chosen_races": "[\"bw_terran\", \"sc2_zerg\", \"bw_protoss\", \"sc2_protoss\"]",
  "last_chosen_vetoes": "[\"Fighting Spirit\", \"Circuit Breaker\"]"
}
```

---

## Validation Results

### ✅ Passed Validations
- **Player Name Length**: All names are 3-12 characters
- **MMR Ranges**: All MMRs are within realistic ranges
- **Data Volume**: Exactly 1000 player-race combinations
- **Required Fields**: All required fields present
- **Data Types**: All data types correct

### ⚠️ Acceptable Warnings
- **Duplicate Names**: 38 duplicate player names (acceptable for mock data)
- **Name Distribution**: Some names more common than others (realistic)

---

## Files Generated

1. **`scripts/generate_realistic_mock_data.py`**
   - Comprehensive mock data generator
   - Respects all validation rules
   - Uses realistic values and distributions

2. **`src/backend/db/realistic_mock_data.json`**
   - Generated realistic mock data
   - 250 players, 1000 MMR records, 250 preferences

3. **`src/backend/db/mock_data.json`**
   - Updated with realistic data (replaces old data)

---

## Usage

### Generate New Data
```bash
python scripts/generate_realistic_mock_data.py
```

### Populate Database
```bash
python scripts/populate_supabase.py
```

---

## Benefits

✅ **Realistic Testing**: Data reflects real-world player patterns  
✅ **Validation Compliant**: All data respects system rules  
✅ **Comprehensive Coverage**: 1000 player-race combinations  
✅ **Geographic Diversity**: Global player distribution  
✅ **MMR Realism**: Realistic skill distribution  
✅ **Game Statistics**: Realistic play patterns  
✅ **Map Preferences**: Realistic veto patterns  

---

## Expected Results

The leaderboard will now display:
- **Realistic Player Names**: All 3-12 characters, properly formatted
- **Geographic Diversity**: Players from around the world
- **Skill Distribution**: Realistic MMR ranges
- **Race Variety**: All 6 races represented
- **Proper Formatting**: Names will align correctly in leaderboard

The mock data now provides a realistic testing environment that respects all validation rules and uses real-world values!
