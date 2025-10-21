#!/usr/bin/env python3
"""
Generate realistic mock data for 250 players with 4 races each (1000 total combinations).
All data respects validation rules and uses real-world values.
"""

import json
import random
import sys
import os
import io
from datetime import datetime, timedelta

# Fix Windows console encoding for Unicode emojis
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Real-world data
COUNTRIES = [
    "US", "KR", "CN", "DE", "FR", "GB", "CA", "AU", "SE", "NO", "DK", "FI", "NL", "BE", "CH", "AT", "IT", "ES", "PL", "RU",
    "JP", "TW", "SG", "TH", "MY", "ID", "PH", "VN", "IN", "PK", "BD", "LK", "MM", "KH", "LA", "BN", "TL", "MN", "KZ", "UZ",
    "BR", "AR", "CL", "CO", "PE", "VE", "EC", "BO", "PY", "UY", "GY", "SR", "GF", "ZA", "EG", "NG", "KE", "GH", "MA", "TN",
    "DZ", "LY", "SD", "ET", "UG", "TZ", "RW", "BI", "DJ", "SO", "ER", "SS", "CF", "TD", "NE", "ML", "BF", "SN", "GM", "GN",
    "GW", "SL", "LR", "CI", "GH", "TG", "BJ", "NG", "CM", "GQ", "GA", "CG", "CD", "AO", "ZM", "ZW", "BW", "NA", "SZ", "LS",
    "MG", "MU", "SC", "KM", "YT", "RE", "MZ", "MW", "TZ", "KE", "UG", "RW", "BI", "DJ", "SO", "ER", "SS", "ET", "SD", "EG",
    "LY", "TN", "DZ", "MA", "EH", "MR", "ML", "BF", "NE", "NG", "TD", "CM", "CF", "GQ", "GA", "CG", "CD", "AO", "ZM", "ZW"
]

REGIONS = [
    "NAE", "NAW", "NAC", "EUW", "EUE", "EUN", "KRJ", "SEA", "OCE", "SAM", "AFR", "MEA", "CHN", "THM", "FER", "USB", "CAM"
]

RACES = [
    "bw_terran", "bw_protoss", "bw_zerg", "sc2_terran", "sc2_protoss", "sc2_zerg"
]

MAPS = [
    "Fighting Spirit", "Circuit Breaker", "Neo", "Khione", "Pylon", "Arkanoid", "Blue Storm", "Destination", "Eclipse",
    "Fortress", "Gaia", "Heartbreak Ridge", "Jade", "Korhal of Ceres", "Lost Temple", "Match Point", "Neo Hallucination",
    "Neo Moon Glaive", "Neo Requiem", "Neo Sniper Ridge", "Neo Transistor", "Neo Turf Wars", "Neo Valhalla", "Neo Vesper",
    "Neo World of Warcraft", "Neo World of Warcraft 2", "Neo World of Warcraft 3", "Neo World of Warcraft 4", "Neo World of Warcraft 5",
    "Neo World of Warcraft 6", "Neo World of Warcraft 7", "Neo World of Warcraft 8", "Neo World of Warcraft 9", "Neo World of Warcraft 10"
]

# Realistic MMR ranges by race (based on actual StarCraft data)
MMR_RANGES = {
    "bw_terran": (800, 2400),
    "bw_protoss": (800, 2400), 
    "bw_zerg": (800, 2400),
    "sc2_terran": (1000, 2500),
    "sc2_protoss": (1000, 2500),
    "sc2_zerg": (1000, 2500)
}

# Realistic player name components
NAME_PREFIXES = [
    "Pro", "Master", "Champion", "Legend", "King", "Lord", "Duke", "Count", "Baron", "Knight", "Warrior", "Fighter",
    "Gladiator", "Hero", "Ace", "Star", "Elite", "Prime", "Alpha", "Beta", "Gamma", "Delta", "Omega", "Nova", "Super",
    "Ultra", "Mega", "Giga", "Tera", "Peta", "Exa", "Zetta", "Yotta", "Kilo", "Swift", "Fast", "Quick", "Rapid", "Speed",
    "Light", "Dark", "Fire", "Ice", "Storm", "Thunder", "Lightning", "Shadow", "Steel", "Iron", "Gold", "Silver", "Bronze"
]

NAME_SUFFIXES = [
    "Gamer", "Player", "Master", "Champion", "Legend", "King", "Lord", "Duke", "Count", "Baron", "Knight",
    "Warrior", "Fighter", "Gladiator", "Hero", "Ace", "Star", "Elite", "Prime", "Alpha", "Beta", "Gamma", "Delta",
    "Omega", "Nova", "Super", "Ultra", "Mega", "Giga", "Tera", "Peta", "Exa", "Zetta", "Yotta", "Kilo", "Swift",
    "Fast", "Quick", "Rapid", "Speed", "Light", "Dark", "Fire", "Ice", "Storm", "Thunder", "Lightning", "Shadow"
]

# Realistic battletag formats
BATTLETAG_PATTERNS = [
    "{name}#{num:04d}",
    "{name}#{num:03d}",
    "{name}#{num:02d}",
    "{name}#{num:01d}",
    "{name}#{num:05d}"
]

def generate_player_name():
    """Generate a realistic player name that respects all validation rules."""
    import re
    
    # Reserved words that are not allowed
    RESERVED_WORDS = {
        "admin", "mod", "moderator", "player", "bot", "discord", "blizzard", "battle", "gm", "dev", "test", "user"
    }
    
    attempts = 0
    while attempts < 100:  # Prevent infinite loop
        if random.random() < 0.3:  # 30% chance for single word
            name = random.choice(NAME_PREFIXES + NAME_SUFFIXES)
        else:  # 70% chance for compound name
            prefix = random.choice(NAME_PREFIXES)
            suffix = random.choice(NAME_SUFFIXES)
            name = prefix + suffix
        
        # Validate name
        if (3 <= len(name) <= 12 and  # Length check
            re.match(r'^[A-Za-z0-9_-]+$', name) and  # Character check
            name.lower() not in RESERVED_WORDS):  # Reserved word check
            return name
        
        attempts += 1
    
    # Fallback to simple names that are guaranteed to be valid
    fallback_names = ["Pro", "Ace", "Star", "King", "Lord", "Hero", "Elite", "Prime", "Alpha", "Beta", "Gamma", "Delta"]
    return random.choice(fallback_names)

def generate_battletag(player_name):
    """Generate a realistic battletag that respects validation rules."""
    import re
    
    attempts = 0
    while attempts < 50:  # Prevent infinite loop
        pattern = random.choice(BATTLETAG_PATTERNS)
        num = random.randint(1, 9999)
        battletag = pattern.format(name=player_name, num=num)
        
        # Validate battletag format: name#numbers
        if re.match(r'^[A-Za-z0-9_-]+#[0-9]+$', battletag) and len(battletag) <= 20:
            return battletag
        
        attempts += 1
    
    # Fallback to simple format
    num = random.randint(1, 9999)
    return f"{player_name}#{num:04d}"

def validate_player_data(player_data):
    """Validate that player data meets all requirements."""
    import re
    
    # Check player name
    name = player_data['player_name']
    if not (3 <= len(name) <= 12):
        return False, f"Name length invalid: {len(name)}"
    if not re.match(r'^[A-Za-z0-9_-]+$', name):
        return False, f"Name contains invalid characters: {name}"
    
    # Check battletag
    battletag = player_data['battletag']
    if not re.match(r'^[A-Za-z0-9_-]+#[0-9]+$', battletag):
        return False, f"Battletag format invalid: {battletag}"
    if len(battletag) > 20:
        return False, f"Battletag too long: {len(battletag)}"
    
    # Check reserved words
    reserved_words = {"admin", "mod", "moderator", "player", "bot", "discord", "blizzard", "battle", "gm", "dev", "test", "user"}
    if name.lower() in reserved_words:
        return False, f"Name is reserved word: {name}"
    
    return True, "Valid"

def generate_mmr(race):
    """Generate realistic MMR based on race."""
    min_mmr, max_mmr = MMR_RANGES[race]
    # Use normal distribution with slight skew toward higher MMRs
    base_mmr = random.normalvariate((min_mmr + max_mmr) / 2, (max_mmr - min_mmr) / 6)
    return max(min_mmr, min(max_mmr, int(base_mmr)))

def generate_games_stats(mmr):
    """Generate realistic game statistics based on MMR."""
    # Higher MMR players tend to have more games
    base_games = max(10, int(mmr / 10) + random.randint(-20, 50))
    games_played = max(1, base_games)
    
    # Win rate correlates with MMR (higher MMR = higher win rate)
    win_rate = min(0.95, max(0.05, (mmr - 800) / 2000 + random.uniform(-0.1, 0.1)))
    games_won = int(games_played * win_rate)
    games_lost = games_played - games_won
    games_drawn = random.randint(0, min(5, games_played // 10))
    
    return games_played, games_won, games_lost, games_drawn

def generate_preferences():
    """Generate realistic race preferences."""
    # Most players prefer 2-4 races
    num_races = random.choices([2, 3, 4], weights=[0.2, 0.5, 0.3])[0]
    chosen_races = random.sample(RACES, num_races)
    
    # Generate vetoes (most players have 0-3 vetoes)
    num_vetoes = random.choices([0, 1, 2, 3], weights=[0.3, 0.4, 0.2, 0.1])[0]
    vetoes = random.sample(MAPS, num_vetoes) if num_vetoes > 0 else []
    
    return chosen_races, vetoes

def generate_realistic_mock_data():
    """Generate 250 players with 4 races each (1000 total combinations)."""
    players = []
    mmrs = []
    preferences = []
    
    print("Generating 250 players with realistic data...")
    
    for i in range(250):
        discord_uid = 100000000 + i
        discord_username = f"Player{i+1}"
        player_name = generate_player_name()
        battletag = generate_battletag(player_name)
        country = random.choice(COUNTRIES)
        region = random.choice(REGIONS)
        
        # Generate player record
        player = {
            "discord_uid": discord_uid,
            "discord_username": discord_username,
            "player_name": player_name,
            "battletag": battletag,
            "country": country,
            "region": region,
            "accepted_tos": True,
            "completed_setup": True
        }
        
        # Validate player data
        is_valid, error_msg = validate_player_data(player)
        if not is_valid:
            print(f"⚠️  Invalid player data: {error_msg}")
            # Regenerate with fallback
            player_name = "Player" + str(i+1)
            battletag = f"{player_name}#1234"
            player["player_name"] = player_name
            player["battletag"] = battletag
        
        players.append(player)
        
        # Generate 4 races for each player
        player_races = random.sample(RACES, 4)
        for race in player_races:
            mmr = generate_mmr(race)
            games_played, games_won, games_lost, games_drawn = generate_games_stats(mmr)
            
            mmr_record = {
                "discord_uid": discord_uid,
                "player_name": player_name,
                "race": race,
                "mmr": mmr,
                "games_played": games_played,
                "games_won": games_won,
                "games_lost": games_lost,
                "games_drawn": games_drawn
            }
            mmrs.append(mmr_record)
        
        # Generate preferences
        chosen_races, vetoes = generate_preferences()
        preference = {
            "discord_uid": discord_uid,
            "last_chosen_races": json.dumps(chosen_races),
            "last_chosen_vetoes": json.dumps(vetoes)
        }
        preferences.append(preference)
        
        if (i + 1) % 50 == 0:
            print(f"Generated {i + 1}/250 players...")
    
    return {
        "players": players,
        "mmrs": mmrs,
        "preferences": preferences
    }

def validate_data(data):
    """Validate that all data respects the rules."""
    print("\nValidating generated data...")
    
    # Check player names
    invalid_names = []
    for player in data["players"]:
        name = player["player_name"]
        if not (3 <= len(name) <= 12):
            invalid_names.append(f"{name} ({len(name)} chars)")
    
    if invalid_names:
        print(f"❌ Found {len(invalid_names)} invalid player names:")
        for name in invalid_names[:10]:  # Show first 10
            print(f"  - {name}")
        if len(invalid_names) > 10:
            print(f"  ... and {len(invalid_names) - 10} more")
    else:
        print("✅ All player names respect 3-12 character limit")
    
    # Check MMR ranges
    invalid_mmrs = []
    for mmr_record in data["mmrs"]:
        race = mmr_record["race"]
        mmr = mmr_record["mmr"]
        min_mmr, max_mmr = MMR_RANGES[race]
        if not (min_mmr <= mmr <= max_mmr):
            invalid_mmrs.append(f"{mmr_record['player_name']} {race}: {mmr} (range: {min_mmr}-{max_mmr})")
    
    if invalid_mmrs:
        print(f"❌ Found {len(invalid_mmrs)} invalid MMR values:")
        for mmr in invalid_mmrs[:10]:  # Show first 10
            print(f"  - {mmr}")
        if len(invalid_mmrs) > 10:
            print(f"  ... and {len(invalid_mmrs) - 10} more")
    else:
        print("✅ All MMR values are within realistic ranges")
    
    # Check total combinations
    total_combinations = len(data["mmrs"])
    expected_combinations = len(data["players"]) * 4
    if total_combinations == expected_combinations:
        print(f"✅ Generated {total_combinations} player-race combinations (250 players × 4 races)")
    else:
        print(f"❌ Expected {expected_combinations} combinations, got {total_combinations}")
    
    # Check for duplicate names
    names = [p["player_name"] for p in data["players"]]
    duplicates = [name for name in set(names) if names.count(name) > 1]
    if duplicates:
        print(f"⚠️  Found {len(duplicates)} duplicate player names: {duplicates[:5]}")
    else:
        print("✅ All player names are unique")
    
    return len(invalid_names) == 0 and len(invalid_mmrs) == 0

def main():
    print("=" * 60)
    print("🎮 Realistic Mock Data Generator")
    print("=" * 60)
    print("Generating 250 players with 4 races each (1000 total combinations)")
    print("All data respects validation rules and uses real-world values")
    print("=" * 60)
    
    # Generate data
    data = generate_realistic_mock_data()
    
    # Validate data
    is_valid = validate_data(data)
    
    if is_valid:
        print("\n✅ Data generation successful!")
        print(f"📊 Generated {len(data['players'])} players")
        print(f"📊 Generated {len(data['mmrs'])} MMR records")
        print(f"📊 Generated {len(data['preferences'])} preference records")
        
        # Save to file
        output_file = "src/backend/db/realistic_mock_data.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Saved to {output_file}")
        
        # Also update the main mock_data.json
        main_output_file = "src/backend/db/mock_data.json"
        with open(main_output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 Also updated {main_output_file}")
        
        # Show sample data
        print("\n📋 Sample Data:")
        print(f"Player: {data['players'][0]['player_name']} ({data['players'][0]['country']})")
        print(f"MMR Records: {len([m for m in data['mmrs'] if m['discord_uid'] == data['players'][0]['discord_uid']])}")
        print(f"Races: {[m['race'] for m in data['mmrs'] if m['discord_uid'] == data['players'][0]['discord_uid']]}")
        print(f"Battletag: {data['players'][0]['battletag']}")
        
        print("\n🎉 Generation complete!")
        print("\n⚠️  IMPORTANT: Run 'python scripts/populate_supabase.py' to update Supabase with clean data")
        
        return 0
    else:
        print("\n❌ Data generation failed validation!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
