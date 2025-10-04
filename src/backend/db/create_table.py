"""
Creates the SQLite database tables based on schema.md.

This script should be run once to initialize the database.
All subsequent database operations should go through db_reader_writer.py.
"""

import sqlite3
import os
from datetime import datetime


def create_database(db_path: str = "evoladder.db") -> None:
    """
    Create the SQLite database with all tables from schema.md.
    
    Args:
        db_path: Path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create players table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_uid             INTEGER NOT NULL UNIQUE,
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
    """)
    
    # Create player_action_logs table
    cursor.execute("""
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
    """)
    
    # Create mmrs_1v1 table
    cursor.execute("""
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
    """)
    
    # Create matches_1v1 table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches_1v1 (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            player_1_discord_uid    INTEGER NOT NULL,
            player_2_discord_uid    INTEGER NOT NULL,
            winner_discord_uid      INTEGER,
            map_played              TEXT NOT NULL,
            server_used             TEXT NOT NULL,
            played_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create preferences_1v1 table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS preferences_1v1 (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_uid             INTEGER NOT NULL UNIQUE,
            last_chosen_races       TEXT,
            last_chosen_vetoes      TEXT
        )
    """)
    
    # Create mmrs_2v2 table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mmrs_2v2 (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            player_1_discord_uid    INTEGER NOT NULL,
            player_2_discord_uid    INTEGER,
            player_1_race           TEXT NOT NULL,
            player_2_race           TEXT,
            mmr                     INTEGER NOT NULL,
            last_played             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(player_1_discord_uid, player_2_discord_uid, player_1_race, player_2_race)
        )
    """)
    
    # Create matches_2v2 table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches_2v2 (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            player_1_discord_uid    INTEGER NOT NULL,
            player_2_discord_uid    INTEGER NOT NULL,
            player_3_discord_uid    INTEGER NOT NULL,
            player_4_discord_uid    INTEGER NOT NULL,
            winner_discord_uid      INTEGER,
            map_played              TEXT NOT NULL,
            server_used             TEXT NOT NULL,
            played_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create preferences_2v2 table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS preferences_2v2 (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            player_1_discord_uid    INTEGER NOT NULL,
            player_2_discord_uid    INTEGER,
            player_1_race           TEXT NOT NULL,
            player_2_race           TEXT,
            last_chosen_races       TEXT,
            last_chosen_vetoes      TEXT,
            UNIQUE(player_1_discord_uid, player_2_discord_uid)
        )
    """)
    
    conn.commit()
    conn.close()
    
    print(f"Database created successfully at: {os.path.abspath(db_path)}")


if __name__ == "__main__":
    create_database()

