"""
Creates the SQLite database tables based on schema.md.

This script drops and recreates all tables, then populates with mock data.
All subsequent database operations should go through db_reader_writer.py.
"""

import sqlite3
import os
import json
from datetime import datetime


def create_database(db_path: str = "evoladder.db") -> None:
    """
    Create the SQLite database with all tables from schema.md.
    Drops existing tables and recreates them with mock data.

    Args:
        db_path: Path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Drop all existing tables
    print("🗑️  Dropping existing tables...")
    cursor.execute("DROP TABLE IF EXISTS preferences_1v1")
    cursor.execute("DROP TABLE IF EXISTS matches_1v1")
    cursor.execute("DROP TABLE IF EXISTS mmrs_1v1")
    cursor.execute("DROP TABLE IF EXISTS player_action_logs")
    cursor.execute("DROP TABLE IF EXISTS players")
    cursor.execute("DROP TABLE IF EXISTS replays")
    cursor.execute("DROP TABLE IF EXISTS command_calls")

    # Create players table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS players (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_uid             INTEGER NOT NULL UNIQUE,
            discord_username        TEXT NOT NULL,
            player_name             TEXT,
            battletag               TEXT,
            alt_player_name_1       TEXT,
            alt_player_name_2       TEXT,
            country                 TEXT,
            region                  TEXT,
            accepted_tos            BOOLEAN DEFAULT FALSE,
            accepted_tos_date       TIMESTAMP,
            completed_setup         BOOLEAN DEFAULT FALSE,
            completed_setup_date    TIMESTAMP,
            activation_code         TEXT,
            created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Create player_action_logs table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS player_action_logs (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_uid             INTEGER NOT NULL,
            player_name             TEXT NOT NULL,
            setting_name            TEXT NOT NULL,
            old_value               TEXT,
            new_value               TEXT,
            changed_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            changed_by              TEXT DEFAULT 'player'
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE command_calls (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_uid             INTEGER NOT NULL,
            player_name             TEXT NOT NULL,
            command                 TEXT NOT NULL,
            called_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Create mmrs_1v1 table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mmrs_1v1 (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_uid             INTEGER NOT NULL,
            player_name             TEXT NOT NULL,
            race                    TEXT NOT NULL,
            mmr                     INTEGER NOT NULL,
            games_played            INTEGER DEFAULT 0,
            games_won               INTEGER DEFAULT 0,
            games_lost              INTEGER DEFAULT 0,
            games_drawn             INTEGER DEFAULT 0,
            last_played             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(discord_uid, race)
        )
    """
    )

    # Create matches_1v1 table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS matches_1v1 (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            player_1_discord_uid    INTEGER NOT NULL,
            player_2_discord_uid    INTEGER NOT NULL,
            player_1_mmr            INTEGER NOT NULL,
            player_2_mmr            INTEGER NOT NULL,
            winner_discord_uid      INTEGER,
            mmr_change              INTEGER NOT NULL,
            map_played              TEXT NOT NULL,
            server_used             TEXT NOT NULL,
            played_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            player_1_replay_path    TEXT,
            player_1_replay_time    TIMESTAMP,          -- stores the timestamp when player_1 uploaded
            player_2_replay_path    TEXT,
            player_2_replay_time    TIMESTAMP           -- stores the timestamp when player_2 uploaded
        )
    """
    )

    # Create preferences_1v1 table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS preferences_1v1 (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_uid             INTEGER NOT NULL UNIQUE,
            last_chosen_races       TEXT,
            last_chosen_vetoes      TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE replays (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            replay_path             TEXT NOT NULL,
            replay_hash             TEXT NOT NULL,
            replay_date             TIMESTAMP NOT NULL,
            player_1_name           TEXT NOT NULL,
            player_2_name           TEXT NOT NULL,
            player_1_race           TEXT NOT NULL,
            player_2_race           TEXT NOT NULL,
            result                  INTEGER NOT NULL,
            player_1_handle         TEXT NOT NULL,
            player_2_handle         TEXT NOT NULL,
            observers               TEXT NOT NULL,
            map_name                TEXT NOT NULL,
            duration                INTEGER NOT NULL
        )
    """
    )

    print("✅ All tables created successfully")

    # Create and populate mock data
    print("📊 Creating mock player data...")
    mock_data = create_mock_data()

    # Save mock data to JSON file
    mock_data_path = os.path.join(os.path.dirname(__file__), "mock_data.json")
    with open(mock_data_path, "w") as f:
        json.dump(mock_data, f, indent=2)
    print(f"💾 Mock data saved to: {mock_data_path}")

    # Populate database with mock data
    populate_database(cursor, mock_data)

    conn.commit()
    conn.close()

    print(
        f"🎉 Database created and populated successfully at: {os.path.abspath(db_path)}"
    )


def create_mock_data():
    """Create mock player data for testing."""
    import random

    # Load regions and countries data
    # Get the project root directory (3 levels up from this file)
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    )
    regions_path = os.path.join(project_root, "data", "misc", "regions.json")
    countries_path = os.path.join(project_root, "data", "misc", "countries.json")

    with open(regions_path, "r") as f:
        regions_data = json.load(f)

    with open(countries_path, "r") as f:
        countries_data = json.load(f)

    # Get common countries
    common_countries = [
        country for country in countries_data if country.get("common", False)
    ]
    selected_countries = random.sample(common_countries, 10)

    # Get residential regions
    residential_regions = regions_data["residential_regions"]

    # All 4 races
    races = [
        "bw_terran",
        "bw_protoss",
        "bw_zerg",
        "sc2_terran",
        "sc2_protoss",
        "sc2_zerg",
    ]

    players = []
    mmrs = []
    preferences = []

    # Generate 50 players
    for i in range(50):
        discord_uid = 100000000 + i
        country = random.choice(selected_countries)
        region = random.choice(residential_regions)

        # Generate player names
        player_names = [
            "StarCraftPro",
            "BWMaster",
            "ZergRush",
            "TerranTank",
            "ProtossPylon",
            "SC2Champion",
            "BroodWarKing",
            "RTSLegend",
            "MicroGod",
            "MacroMaster",
            "BuildOrder",
            "RushPlayer",
            "DefenseKing",
            "AttackWave",
            "StrategyPro",
            "GameMaster",
            "LadderKing",
            "RankedPro",
            "Competitive",
            "Tournament",
            "ProGamer",
            "ElitePlayer",
            "SkillMaster",
            "Tactical",
            "Strategic",
            "Warrior",
            "Commander",
            "General",
            "Captain",
            "Admiral",
            "Champion",
            "Hero",
            "Legend",
            "Master",
            "Expert",
            "Veteran",
            "Rookie",
            "Novice",
            "Beginner",
            "Advanced",
            "Elite",
            "Pro",
            "SemiPro",
            "Amateur",
            "Casual",
            "Hardcore",
            "Competitive",
            "Ranked",
            "Ladder",
            "Tournament",
        ]

        player_name = random.choice(player_names) + str(random.randint(1, 999))
        discord_username = f"Player{i+1}"
        battletag = f"{player_name}#{random.randint(1000, 9999)}"

        # Create player
        player = {
            "discord_uid": discord_uid,
            "discord_username": discord_username,
            "player_name": player_name,
            "battletag": battletag,
            "country": country["code"],
            "region": region["code"],
            "accepted_tos": True,
            "completed_setup": True,
        }
        players.append(player)

        # Generate MMR for all 4 races (2 BW + 2 SC2)
        bw_races = ["bw_terran", "bw_protoss", "bw_zerg"]
        sc2_races = ["sc2_terran", "sc2_protoss", "sc2_zerg"]

        # Pick 2 BW races and 2 SC2 races
        selected_bw_races = random.sample(bw_races, 2)
        selected_sc2_races = random.sample(sc2_races, 2)
        selected_races = selected_bw_races + selected_sc2_races

        for race in selected_races:
            # Random MMR between 1000-2000
            mmr = random.randint(1000, 2000)

            # Random game stats
            games_played = random.randint(10, 100)
            games_won = random.randint(0, games_played)
            games_lost = (
                games_played - games_won - random.randint(0, 5)
            )  # Some draws possible
            games_drawn = games_played - games_won - games_lost

            mmr_entry = {
                "discord_uid": discord_uid,
                "player_name": player_name,
                "race": race,
                "mmr": mmr,
                "games_played": games_played,
                "games_won": games_won,
                "games_lost": games_lost,
                "games_drawn": max(0, games_drawn),
            }
            mmrs.append(mmr_entry)

        # Create preferences
        races_json = json.dumps(selected_races)
        # Random map vetoes (0-3 maps)
        map_names = [
            "Arkanoid",
            "Khione",
            "Pylon",
            "Neo",
            "Fighting Spirit",
            "Circuit Breaker",
        ]
        vetoed_maps = random.sample(map_names, random.randint(0, 3))
        vetoes_json = json.dumps(vetoed_maps)

        preference = {
            "discord_uid": discord_uid,
            "last_chosen_races": races_json,
            "last_chosen_vetoes": vetoes_json,
        }
        preferences.append(preference)

    return {"players": players, "mmrs": mmrs, "preferences": preferences}


def populate_database(cursor, mock_data):
    """Populate database with mock data."""
    # Insert players
    print("👥 Inserting mock players...")
    for player in mock_data["players"]:
        cursor.execute(
            """
            INSERT INTO players (
                discord_uid, discord_username, player_name, battletag,
                country, region, accepted_tos, completed_setup
            ) VALUES (:discord_uid, :discord_username, :player_name, :battletag, :country, :region, :accepted_tos, :completed_setup)
        """,
            {
                "discord_uid": player["discord_uid"],
                "discord_username": player["discord_username"],
                "player_name": player["player_name"],
                "battletag": player["battletag"],
                "country": player["country"],
                "region": player["region"],
                "accepted_tos": player["accepted_tos"],
                "completed_setup": player["completed_setup"],
            },
        )

    # Insert MMRs
    print("📊 Inserting mock MMR data...")
    for mmr in mock_data["mmrs"]:
        cursor.execute(
            """
            INSERT INTO mmrs_1v1 (
                discord_uid, player_name, race, mmr,
                games_played, games_won, games_lost, games_drawn
            ) VALUES (:discord_uid, :player_name, :race, :mmr, :games_played, :games_won, :games_lost, :games_drawn)
        """,
            {
                "discord_uid": mmr["discord_uid"],
                "player_name": mmr["player_name"],
                "race": mmr["race"],
                "mmr": mmr["mmr"],
                "games_played": mmr["games_played"],
                "games_won": mmr["games_won"],
                "games_lost": mmr["games_lost"],
                "games_drawn": mmr["games_drawn"],
            },
        )

    # Insert preferences
    print("⚙️  Inserting mock preferences...")
    for pref in mock_data["preferences"]:
        cursor.execute(
            """
            INSERT INTO preferences_1v1 (
                discord_uid, last_chosen_races, last_chosen_vetoes
            ) VALUES (:discord_uid, :last_chosen_races, :last_chosen_vetoes)
        """,
            {
                "discord_uid": pref["discord_uid"],
                "last_chosen_races": pref["last_chosen_races"],
                "last_chosen_vetoes": pref["last_chosen_vetoes"],
            },
        )

    # Insert matches_1v1
    print("🎮 Inserting mock matches_1v1 data...")
    for match in mock_data["matches_1v1"]:
        cursor.execute(
            """
            INSERT INTO matches_1v1 (
                player_1_discord_uid, player_2_discord_uid, player_1_mmr, player_2_mmr,
                mmr_change, map_played, server_used, played_at,
                player_1_replay_path, player_1_replay_time, player_2_replay_path, player_2_replay_time
            ) VALUES (
                :player_1_discord_uid, :player_2_discord_uid, :player_1_mmr, :player_2_mmr,
                :mmr_change, :map_played, :server_used, :played_at,
                :player_1_replay_path, :player_1_replay_time, :player_2_replay_path, :player_2_replay_time
            )
        """,
            {
                "player_1_discord_uid": match["player_1_discord_uid"],
                "player_2_discord_uid": match["player_2_discord_uid"],
                "player_1_mmr": match["player_1_mmr"],
                "player_2_mmr": match["player_2_mmr"],
                "mmr_change": match["mmr_change"],
                "map_played": match["map_played"],
                "server_used": match["server_used"],
                "played_at": match["played_at"],
                "player_1_replay_path": match["player_1_replay_path"],
                "player_1_replay_time": match["player_1_replay_time"],
                "player_2_replay_path": match["player_2_replay_path"],
                "player_2_replay_time": match["player_2_replay_time"],
            },
        )

    # Insert replays
    print("🎮 Inserting mock replays data...")
    for replay in mock_data["replays"]:
        cursor.execute(
            """
            INSERT INTO replays (
                replay_path, replay_hash, replay_date, player_1_name, player_2_name,
                player_1_race, player_2_race, result, player_1_handle, player_2_handle,
                observers, map_name, duration
            ) VALUES (
                :replay_path, :replay_hash, :replay_date, :player_1_name, :player_2_name,
                :player_1_race, :player_2_race, :result, :player_1_handle, :player_2_handle,
                :observers, :map_name, :duration
            )
        """,
            {
                "replay_path": replay["replay_path"],
                "replay_hash": replay["replay_hash"],
                "replay_date": replay["replay_date"],
                "player_1_name": replay["player_1_name"],
                "player_2_name": replay["player_2_name"],
                "player_1_race": replay["player_1_race"],
                "player_2_race": replay["player_2_race"],
                "result": replay["result"],
                "player_1_handle": replay["player_1_handle"],
                "player_2_handle": replay["player_2_handle"],
                "observers": replay["observers"],
                "map_name": replay["map_name"],
                "duration": replay["duration"],
            },
        )

    print("✅ Mock data population complete!")


def load_mock_data():
    """Load mock data from JSON file."""
    mock_data_path = os.path.join(os.path.dirname(__file__), "mock_data.json")
    try:
        with open(mock_data_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Mock data file not found: {mock_data_path}")
        print("💡 Run create_database() first to generate mock data")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing mock data JSON: {e}")
        return None


if __name__ == "__main__":
    create_database()
