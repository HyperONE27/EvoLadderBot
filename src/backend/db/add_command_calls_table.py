"""
This script adds the 'command_calls' table to the SQLite database.
"""

import sqlite3


def add_command_calls_table(db_path: str = "evoladder.db") -> None:
    """Create the command_calls table if it does not already exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS command_calls (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_uid             INTEGER NOT NULL,
            player_name             TEXT NOT NULL,
            command                 TEXT NOT NULL,
            called_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()

    print("'command_calls' table created successfully (if it didn't exist).")


if __name__ == "__main__":
    add_command_calls_table()
