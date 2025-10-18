"""
This script adds the 'replays' table to the SQLite database.
"""

import sqlite3

def add_replays_table(db_path: str = "evoladder.db") -> None:
    """
    Adds the 'replays' table to the SQLite database if it doesn't already exist.
    
    Args:
        db_path: Path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create replays table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS replays (
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
    """)

    conn.commit()
    conn.close()
    
    print("'replays' table created successfully (if it didn't exist).")

if __name__ == "__main__":
    add_replays_table()
