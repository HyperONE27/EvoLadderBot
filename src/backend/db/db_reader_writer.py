"""
Implements a reader/writer for the database.

Backend services must use these classes to read and write to the database.
All SQL queries MUST be contained inside this module.
"""

import sqlite3
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from contextlib import contextmanager


def get_timestamp() -> str:
    """
    Get current timestamp formatted to second precision.
    
    Returns:
        ISO format timestamp string truncated to seconds.
    """
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class Database:
    """
    Base database connection manager.
    """
    def __init__(self, db_path: str = "evoladder.db"):
        self.db_path = db_path
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()


class DatabaseReader:
    """
    Reads from the database.
    """
    def __init__(self, db_path: str = "evoladder.db"):
        self.db = Database(db_path)
    
    # ========== Players Table ==========
    
    def get_player_by_discord_uid(self, discord_uid: int) -> Optional[Dict[str, Any]]:
        """Get player by Discord UID."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM players WHERE discord_uid = ?",
                (discord_uid,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_player_by_activation_code(self, activation_code: str) -> Optional[Dict[str, Any]]:
        """Get player by activation code."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM players WHERE activation_code = ?",
                (activation_code,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def player_exists(self, discord_uid: int) -> bool:
        """Check if a player exists."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM players WHERE discord_uid = ? LIMIT 1",
                (discord_uid,)
            )
            return cursor.fetchone() is not None
    
    def get_all_players(self) -> List[Dict[str, Any]]:
        """Get all players."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM players")
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== Player Action Logs Table ==========
    
    def get_player_action_logs(
        self,
        discord_uid: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get player action logs."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if discord_uid:
                cursor.execute(
                    "SELECT * FROM player_action_logs WHERE discord_uid = ? "
                    "ORDER BY changed_at DESC LIMIT ?",
                    (discord_uid, limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM player_action_logs "
                    "ORDER BY changed_at DESC LIMIT ?",
                    (limit,)
                )
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== MMRs 1v1 Table ==========
    
    def get_player_mmr_1v1(
        self,
        discord_uid: int,
        race: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get player's 1v1 MMR for a specific race."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if race:
                cursor.execute(
                    "SELECT * FROM mmrs_1v1 WHERE discord_uid = ? AND race = ?",
                    (discord_uid, race)
                )
            else:
                cursor.execute(
                    "SELECT * FROM mmrs_1v1 WHERE discord_uid = ?",
                    (discord_uid,)
                )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_player_mmrs_1v1(self, discord_uid: int) -> List[Dict[str, Any]]:
        """Get all 1v1 MMRs for a player."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM mmrs_1v1 WHERE discord_uid = ?",
                (discord_uid,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_leaderboard_1v1(
        self,
        race: Optional[str] = None,
        country: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get 1v1 leaderboard with optional filters.
        
        Args:
            race: Filter by race (optional).
            country: Filter by country (optional).
            limit: Maximum number of records to return.
            offset: Number of records to skip.
        
        Returns:
            List of player MMR records sorted by MMR descending.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT m.*, p.country, p.player_name
                FROM mmrs_1v1 m
                LEFT JOIN players p ON m.discord_uid = p.discord_uid
                WHERE 1=1
            """
            params = []
            
            if race:
                query += " AND m.race = ?"
                params.append(race)
            
            if country:
                query += " AND p.country = ?"
                params.append(country)
            
            query += " ORDER BY m.mmr DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def count_leaderboard_1v1(
        self,
        race: Optional[str] = None,
        country: Optional[str] = None
    ) -> int:
        """Count total entries in 1v1 leaderboard with filters."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT COUNT(*)
                FROM mmrs_1v1 m
                LEFT JOIN players p ON m.discord_uid = p.discord_uid
                WHERE 1=1
            """
            params = []
            
            if race:
                query += " AND m.race = ?"
                params.append(race)
            
            if country:
                query += " AND p.country = ?"
                params.append(country)
            
            cursor.execute(query, params)
            return cursor.fetchone()[0]
    
    # ========== Matches 1v1 Table ==========
    
    def get_player_matches_1v1(
        self,
        discord_uid: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent matches for a player."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM matches_1v1 "
                "WHERE player_1_discord_uid = ? OR player_2_discord_uid = ? "
                "ORDER BY played_at DESC LIMIT ?",
                (discord_uid, discord_uid, limit)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== Preferences 1v1 Table ==========
    
    def get_preferences_1v1(self, discord_uid: int) -> Optional[Dict[str, Any]]:
        """Get 1v1 preferences for a player."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM preferences_1v1 WHERE discord_uid = ?",
                (discord_uid,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None


class DatabaseWriter:
    """
    Writes to the database.
    """
    def __init__(self, db_path: str = "evoladder.db"):
        self.db = Database(db_path)
    
    # ========== Players Table ==========
    
    def create_player(
        self,
        discord_uid: int,
        discord_username: str = "Unknown",
        player_name: Optional[str] = None,
        battletag: Optional[str] = None,
        country: Optional[str] = None,
        region: Optional[str] = None,
        activation_code: Optional[str] = None
    ) -> int:
        """
        Create a new player.
        
        Args:
            discord_uid: Discord user ID (unique identifier).
            discord_username: Discord username (e.g., "username" from username#1234 or @username).
                              Defaults to "Unknown" if not provided.
            player_name: In-game player name (optional).
            battletag: Battle.net BattleTag (optional).
            country: Country code (optional).
            region: Region code (optional).
            activation_code: Activation code (optional).
        
        Returns:
            The ID of the newly created player.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO players (
                    discord_uid, discord_username, player_name, battletag, country, region, activation_code
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (discord_uid, discord_username, player_name, battletag, country, region, activation_code)
            )
            conn.commit()
            return cursor.lastrowid
    
    def update_player(
        self,
        discord_uid: int,
        discord_username: Optional[str] = None,
        player_name: Optional[str] = None,
        battletag: Optional[str] = None,
        alt_player_name_1: Optional[str] = None,
        alt_player_name_2: Optional[str] = None,
        country: Optional[str] = None,
        region: Optional[str] = None,
        accepted_tos: Optional[bool] = None,
        completed_setup: Optional[bool] = None,
        activation_code: Optional[str] = None
    ) -> bool:
        """
        Update player information.
        
        Protected fields (cannot be overwritten once set):
        - created_at: Set automatically on creation, cannot be modified
        - accepted_tos_date: Set once when accepted_tos becomes True, cannot be overwritten
        - completed_setup_date: Set once when completed_setup becomes True, cannot be overwritten
        
        Returns:
            True if the player was updated, False otherwise.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build dynamic update query
            updates = []
            params = []
            
            if discord_username is not None:
                updates.append("discord_username = ?")
                params.append(discord_username)
            
            if player_name is not None:
                updates.append("player_name = ?")
                params.append(player_name)
            
            if battletag is not None:
                updates.append("battletag = ?")
                params.append(battletag)
            
            if alt_player_name_1 is not None:
                updates.append("alt_player_name_1 = ?")
                params.append(alt_player_name_1)
            
            if alt_player_name_2 is not None:
                updates.append("alt_player_name_2 = ?")
                params.append(alt_player_name_2)
            
            if country is not None:
                updates.append("country = ?")
                params.append(country)
            
            if region is not None:
                updates.append("region = ?")
                params.append(region)
            
            if accepted_tos is not None:
                updates.append("accepted_tos = ?")
                params.append(accepted_tos)
                # Only set accepted_tos_date if it's currently NULL (can't be overwritten)
                if accepted_tos:
                    updates.append("accepted_tos_date = COALESCE(accepted_tos_date, ?)")
                    params.append(get_timestamp())
            
            if completed_setup is not None:
                updates.append("completed_setup = ?")
                params.append(completed_setup)
                # Only set completed_setup_date if it's currently NULL (can't be overwritten)
                if completed_setup:
                    updates.append("completed_setup_date = COALESCE(completed_setup_date, ?)")
                    params.append(get_timestamp())
            
            if activation_code is not None:
                updates.append("activation_code = ?")
                params.append(activation_code)
            
            if not updates:
                return False
            
            # Always update the updated_at timestamp
            updates.append("updated_at = ?")
            params.append(get_timestamp())
            
            # Add discord_uid to params
            params.append(discord_uid)
            
            query = f"UPDATE players SET {', '.join(updates)} WHERE discord_uid = ?"
            cursor.execute(query, params)
            conn.commit()
            
            return cursor.rowcount > 0
    
    def update_player_activation_code(
        self,
        discord_uid: int,
        activation_code: str
    ) -> bool:
        """Update player's activation code."""
        return self.update_player(discord_uid, activation_code=activation_code)
    
    def update_player_country(self, discord_uid: int, country: str) -> bool:
        """Update player's country."""
        return self.update_player(discord_uid, country=country)
    
    def accept_terms_of_service(self, discord_uid: int) -> bool:
        """Mark player as having accepted terms of service."""
        return self.update_player(discord_uid, accepted_tos=True)
    
    def complete_setup(self, discord_uid: int) -> bool:
        """Mark player as having completed setup."""
        return self.update_player(discord_uid, completed_setup=True)
    
    # ========== Player Action Logs Table ==========
    
    def log_player_action(
        self,
        discord_uid: int,
        player_name: str,
        setting_name: str,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        changed_by: str = "player"
    ) -> int:
        """
        Log a player action and update the updated_at timestamp.
        
        Returns:
            The ID of the newly created log entry.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Log the action
            cursor.execute(
                """
                INSERT INTO player_action_logs (
                    discord_uid, player_name, setting_name,
                    old_value, new_value, changed_by
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (discord_uid, player_name, setting_name, old_value, new_value, changed_by)
            )
            
            # Update the updated_at timestamp in players table
            cursor.execute(
                """
                UPDATE players 
                SET updated_at = ? 
                WHERE discord_uid = ?
                """,
                (get_timestamp(), discord_uid)
            )
            
            conn.commit()
            return cursor.lastrowid
    
    
    # ========== MMRs 1v1 Table ==========
    
    def create_or_update_mmr_1v1(
        self,
        discord_uid: int,
        player_name: str,
        race: str,
        mmr: int,
        games_played: int = 0,
        games_won: int = 0,
        games_lost: int = 0,
        games_drawn: int = 0
    ) -> bool:
        """
        Create or update a player's 1v1 MMR for a specific race.
        
        Returns:
            True if successful.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO mmrs_1v1 (
                    discord_uid, player_name, race, mmr,
                    games_played, games_won, games_lost, games_drawn, last_played
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(discord_uid, race) DO UPDATE SET
                    player_name = excluded.player_name,
                    mmr = excluded.mmr,
                    games_played = excluded.games_played,
                    games_won = excluded.games_won,
                    games_lost = excluded.games_lost,
                    games_drawn = excluded.games_drawn,
                    last_played = excluded.last_played
                """,
                (
                    discord_uid, player_name, race, mmr,
                    games_played, games_won, games_lost, games_drawn,
                    get_timestamp()
                )
            )
            conn.commit()
            return True
    
    # ========== Matches 1v1 Table ==========
    
    def create_match_1v1(
        self,
        player_1_discord_uid: int,
        player_2_discord_uid: int,
        map_played: str,
        server_used: str,
        winner_discord_uid: Optional[int] = None
    ) -> int:
        """
        Create a new 1v1 match record.
        
        Returns:
            The ID of the newly created match.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO matches_1v1 (
                    player_1_discord_uid, player_2_discord_uid,
                    winner_discord_uid, map_played, server_used
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    player_1_discord_uid, player_2_discord_uid,
                    winner_discord_uid, map_played, server_used
                )
            )
            conn.commit()
            return cursor.lastrowid
    
    # ========== Preferences 1v1 Table ==========
    
    def update_preferences_1v1(
        self,
        discord_uid: int,
        last_chosen_races: Optional[str] = None,
        last_chosen_vetoes: Optional[str] = None
    ) -> bool:
        """
        Update or create 1v1 preferences for a player.
        
        Args:
            discord_uid: Player's Discord UID.
            last_chosen_races: JSON string of last chosen races.
            last_chosen_vetoes: JSON string of last chosen vetoes.
        
        Returns:
            True if successful.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build dynamic update
            updates = []
            params = []
            
            if last_chosen_races is not None:
                updates.append("last_chosen_races = ?")
                params.append(last_chosen_races)
            
            if last_chosen_vetoes is not None:
                updates.append("last_chosen_vetoes = ?")
                params.append(last_chosen_vetoes)
            
            if not updates:
                return False
            
            params.append(discord_uid)
            
            # Try to update first
            update_query = f"""
                UPDATE preferences_1v1
                SET {', '.join(updates)}
                WHERE discord_uid = ?
            """
            cursor.execute(update_query, params)
            
            # If no rows were updated, insert
            if cursor.rowcount == 0:
                cursor.execute(
                    """
                    INSERT INTO preferences_1v1 (
                        discord_uid, last_chosen_races, last_chosen_vetoes
                    )
                    VALUES (?, ?, ?)
                    """,
                    (discord_uid, last_chosen_races, last_chosen_vetoes)
                )
            
            conn.commit()
            return True
