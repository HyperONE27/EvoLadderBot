"""
Creates the SQLite database tables based on schema.md.

This script drops and recreates all tables, then populates with mock data.
All subsequent database operations should go through db_reader_writer.py.
"""

import sqlite3


def create_database(db_path: str = "evoladder.db") -> None:
    """
    Create the SQLite database with all tables from schema.md.
    Drops existing tables and recreates them with mock data.

    Args:
        db_path: Path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Drop existing matches_1v1 table if it exists
    cursor.execute("DROP TABLE IF EXISTS matches_1v1")

    # Create matches_1v1 table
    cursor.execute(
        """
        CREATE TABLE matches_1v1 (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            player_1_discord_uid    INTEGER NOT NULL,
            player_2_discord_uid    INTEGER NOT NULL,
            player_1_race           TEXT NOT NULL,
            player_2_race           TEXT NOT NULL,
            player_1_mmr            FLOAT NOT NULL,
            player_2_mmr            FLOAT NOT NULL,
            player_1_report         INTEGER,            -- NULL for not yet determined, 1 for player_1, 2 for player_2, 0 for draw, -1 for aborted match, -3 if player_1 initiated the abort
            player_2_report         INTEGER,            -- NULL for not yet determined, 1 for player_1, 2 for player_2, 0 for draw, -1 for aborted match, -3 if player_2 initiated the abort
            match_result            INTEGER,            -- NULL for not yet determined, 1 for player_1, 2 for player_2, 0 for draw, -1 for aborted match, -2 for conflict between player_1_report and player_2_report
            mmr_change              FLOAT NOT NULL,     -- Amount of MMR awarded. Positive value means player 1 gained MMR, negative value means player 2 gained MMR.
            map_played              TEXT NOT NULL,
            server_used             TEXT NOT NULL,
            played_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            player_1_replay_path    TEXT,
            player_1_replay_time    TIMESTAMP,          -- stores the timestamp when player_1 uploaded                      
            player_2_replay_path    TEXT,
            player_2_replay_time    TIMESTAMP          -- stores the timestamp when player_2 uploaded
        )
    """
    )

    conn.commit()
    conn.close()

    print("All tables created successfully")


if __name__ == "__main__":
    create_database()
