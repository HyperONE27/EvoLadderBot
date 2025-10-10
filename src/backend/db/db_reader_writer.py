"""
Implements a reader/writer for the database.

Backend services must use these classes to read and write to the database.
All SQL queries MUST be contained inside this module.
All SQL queries use named parameters for safety and maintainability.
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
        conn.execute("PRAGMA journal_mode=WAL;") # Enable Write-Ahead Logging
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
                "SELECT * FROM players WHERE discord_uid = :discord_uid",
                {"discord_uid": discord_uid}
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_player_by_activation_code(self, activation_code: str) -> Optional[Dict[str, Any]]:
        """Get player by activation code."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM players WHERE activation_code = :activation_code",
                {"activation_code": activation_code}
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def player_exists(self, discord_uid: int) -> bool:
        """Check if a player exists."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM players WHERE discord_uid = :discord_uid LIMIT 1",
                {"discord_uid": discord_uid}
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
                    "SELECT * FROM player_action_logs WHERE discord_uid = :discord_uid "
                    "ORDER BY changed_at DESC LIMIT :limit",
                    {"discord_uid": discord_uid, "limit": limit}
                )
            else:
                cursor.execute(
                    "SELECT * FROM player_action_logs "
                    "ORDER BY changed_at DESC LIMIT :limit",
                    {"limit": limit}
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
                    "SELECT * FROM mmrs_1v1 WHERE discord_uid = :discord_uid AND race = :race",
                    {"discord_uid": discord_uid, "race": race}
                )
            else:
                cursor.execute(
                    "SELECT * FROM mmrs_1v1 WHERE discord_uid = :discord_uid",
                    {"discord_uid": discord_uid}
                )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_player_mmrs_1v1(self, discord_uid: int) -> List[Dict[str, Any]]:
        """Get all 1v1 MMRs for a player."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM mmrs_1v1 WHERE discord_uid = :discord_uid",
                {"discord_uid": discord_uid}
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
            params = {}
            
            if race:
                query += " AND m.race = :race"
                params["race"] = race
            
            if country:
                query += " AND p.country = :country"
                params["country"] = country
            
            query += " ORDER BY m.mmr DESC LIMIT :limit OFFSET :offset"
            params["limit"] = limit
            params["offset"] = offset
            
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
            params = {}
            
            if race:
                query += " AND m.race = :race"
                params["race"] = race
            
            if country:
                query += " AND p.country = :country"
                params["country"] = country
            
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
                "WHERE player_1_discord_uid = :discord_uid OR player_2_discord_uid = :discord_uid "
                "ORDER BY played_at DESC LIMIT :limit",
                {"discord_uid": discord_uid, "limit": limit}
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_match_1v1(self, match_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific 1v1 match by ID."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM matches_1v1 WHERE id = :match_id",
                {"match_id": match_id}
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # ========== Preferences 1v1 Table ==========
    
    def get_preferences_1v1(self, discord_uid: int) -> Optional[Dict[str, Any]]:
        """Get 1v1 preferences for a player."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM preferences_1v1 WHERE discord_uid = :discord_uid",
                {"discord_uid": discord_uid}
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
                VALUES (:discord_uid, :discord_username, :player_name, :battletag, :country, :region, :activation_code)
                """,
                {
                    "discord_uid": discord_uid,
                    "discord_username": discord_username,
                    "player_name": player_name,
                    "battletag": battletag,
                    "country": country,
                    "region": region,
                    "activation_code": activation_code
                }
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
            params = {}
            
            if discord_username is not None:
                updates.append("discord_username = :discord_username")
                params["discord_username"] = discord_username
            
            if player_name is not None:
                updates.append("player_name = :player_name")
                params["player_name"] = player_name
            
            if battletag is not None:
                updates.append("battletag = :battletag")
                params["battletag"] = battletag
            
            if alt_player_name_1 is not None:
                updates.append("alt_player_name_1 = :alt_player_name_1")
                # Convert empty string to None for proper NULL storage
                params["alt_player_name_1"] = alt_player_name_1 if alt_player_name_1.strip() else None
            
            if alt_player_name_2 is not None:
                updates.append("alt_player_name_2 = :alt_player_name_2")
                # Convert empty string to None for proper NULL storage
                params["alt_player_name_2"] = alt_player_name_2 if alt_player_name_2.strip() else None
            
            if country is not None:
                updates.append("country = :country")
                params["country"] = country
            
            if region is not None:
                updates.append("region = :region")
                params["region"] = region
            
            if accepted_tos is not None:
                updates.append("accepted_tos = :accepted_tos")
                params["accepted_tos"] = accepted_tos
                # Only set accepted_tos_date if it's currently NULL (can't be overwritten)
                if accepted_tos:
                    updates.append("accepted_tos_date = COALESCE(accepted_tos_date, :accepted_tos_date)")
                    params["accepted_tos_date"] = get_timestamp()
            
            if completed_setup is not None:
                updates.append("completed_setup = :completed_setup")
                params["completed_setup"] = completed_setup
                # Only set completed_setup_date if it's currently NULL (can't be overwritten)
                if completed_setup:
                    updates.append("completed_setup_date = COALESCE(completed_setup_date, :completed_setup_date)")
                    params["completed_setup_date"] = get_timestamp()
            
            if activation_code is not None:
                updates.append("activation_code = :activation_code")
                params["activation_code"] = activation_code
            
            if not updates:
                return False
            
            # Always update the updated_at timestamp
            updates.append("updated_at = :updated_at")
            params["updated_at"] = get_timestamp()
            
            # Add discord_uid to params
            params["discord_uid"] = discord_uid
            
            query = f"UPDATE players SET {', '.join(updates)} WHERE discord_uid = :discord_uid"
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
                VALUES (:discord_uid, :player_name, :setting_name, :old_value, :new_value, :changed_by)
                """,
                {
                    "discord_uid": discord_uid,
                    "player_name": player_name,
                    "setting_name": setting_name,
                    "old_value": old_value,
                    "new_value": new_value,
                    "changed_by": changed_by
                }
            )
            
            # Update the updated_at timestamp in players table
            cursor.execute(
                """
                UPDATE players 
                SET updated_at = :updated_at
                WHERE discord_uid = :discord_uid
                """,
                {
                    "updated_at": get_timestamp(),
                    "discord_uid": discord_uid
                }
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
                VALUES (:discord_uid, :player_name, :race, :mmr, :games_played, :games_won, :games_lost, :games_drawn, :last_played)
                ON CONFLICT(discord_uid, race) DO UPDATE SET
                    player_name = excluded.player_name,
                    mmr = excluded.mmr,
                    games_played = excluded.games_played,
                    games_won = excluded.games_won,
                    games_lost = excluded.games_lost,
                    games_drawn = excluded.games_drawn,
                    last_played = excluded.last_played
                """,
                {
                    "discord_uid": discord_uid,
                    "player_name": player_name,
                    "race": race,
                    "mmr": mmr,
                    "games_played": games_played,
                    "games_won": games_won,
                    "games_lost": games_lost,
                    "games_drawn": games_drawn,
                    "last_played": get_timestamp()
                }
            )
            conn.commit()
            return True
    
    def update_mmr_after_match(
        self,
        discord_uid: int,
        race: str,
        new_mmr: int,
        won: bool = False,
        lost: bool = False,
        drawn: bool = False
    ) -> bool:
        """
        Update a player's MMR and match statistics after a match.
        
        Args:
            discord_uid: Player's Discord UID
            race: Race played
            new_mmr: New MMR value
            won: Whether the player won
            lost: Whether the player lost
            drawn: Whether the match was a draw
            
        Returns:
            True if successful
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get current stats
            cursor.execute(
                "SELECT games_played, games_won, games_lost, games_drawn FROM mmrs_1v1 WHERE discord_uid = :discord_uid AND race = :race",
                {"discord_uid": discord_uid, "race": race}
            )
            result = cursor.fetchone()
            
            if result:
                games_played, games_won, games_lost, games_drawn = result
                # Increment stats
                games_played += 1
                if won:
                    games_won += 1
                elif lost:
                    games_lost += 1
                elif drawn:
                    games_drawn += 1
            else:
                # No existing record, start with 1 game
                games_played = 1
                games_won = 1 if won else 0
                games_lost = 1 if lost else 0
                games_drawn = 1 if drawn else 0
            
            # Update or create the record
            cursor.execute(
                """
                INSERT INTO mmrs_1v1 (
                    discord_uid, player_name, race, mmr,
                    games_played, games_won, games_lost, games_drawn, last_played
                )
                VALUES (:discord_uid, :player_name, :race, :mmr, :games_played, :games_won, :games_lost, :games_drawn, :last_played)
                ON CONFLICT(discord_uid, race) DO UPDATE SET
                    mmr = excluded.mmr,
                    games_played = excluded.games_played,
                    games_won = excluded.games_won,
                    games_lost = excluded.games_lost,
                    games_drawn = excluded.games_drawn,
                    last_played = excluded.last_played
                """,
                {
                    "discord_uid": discord_uid,
                    "player_name": f"Player{discord_uid}",
                    "race": race,
                    "mmr": new_mmr,
                    "games_played": games_played,
                    "games_won": games_won,
                    "games_lost": games_lost,
                    "games_drawn": games_drawn,
                    "last_played": get_timestamp()
                }
            )
            conn.commit()
            return True
    
    # ========== Matches 1v1 Table ==========
    
    def create_match_1v1(
        self,
        player_1_discord_uid: int,
        player_2_discord_uid: int,
        player_1_race: str,
        player_2_race: str,
        map_played: str,
        server_used: str,
        player_1_mmr: int,
        player_2_mmr: int,
        mmr_change: int
    ) -> int:
        """
        Create a new 1v1 match record.
        
        Args:
            player_1_discord_uid: Discord UID of player 1
            player_2_discord_uid: Discord UID of player 2
            player_1_race: Race of player 1
            player_2_race: Race of player 2
            map_played: Name of the map played
            server_used: Server used for the match
            player_1_mmr: MMR of player 1 at match time
            player_2_mmr: MMR of player 2 at match time
            mmr_change: MMR change amount (positive = player 1 gained, negative = player 2 gained)
        
        Returns:
            The ID of the newly created match.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO matches_1v1 (
                    player_1_discord_uid, player_2_discord_uid,
                    player_1_race, player_2_race,
                    player_1_mmr, player_2_mmr,
                    mmr_change, map_played, server_used
                )
                VALUES (
                    :player_1_discord_uid, :player_2_discord_uid,
                    :player_1_race, :player_2_race,
                    :player_1_mmr, :player_2_mmr,
                    :mmr_change, :map_played, :server_used
                )
                """,
                {
                    "player_1_discord_uid": player_1_discord_uid,
                    "player_2_discord_uid": player_2_discord_uid,
                    "player_1_race": player_1_race,
                    "player_2_race": player_2_race,
                    "player_1_mmr": player_1_mmr,
                    "player_2_mmr": player_2_mmr,
                    "mmr_change": mmr_change,
                    "map_played": map_played,
                    "server_used": server_used
                }
            )
            conn.commit()
            return cursor.lastrowid
    
    # ========== Preferences 1v1 Table ==========
    
    def update_player_report_1v1(
        self,
        match_id: int,
        player_discord_uid: int,
        report_value: int
    ) -> bool:
        """
        Update a player's report for a 1v1 match.
        
        Args:
            match_id: The ID of the match to update.
            player_discord_uid: The Discord UID of the player reporting.
            report_value: The report value (1 = player_1 won, 2 = player_2 won, 0 = draw).
        
        Returns:
            True if the update was successful, False otherwise.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get match details to determine which player is which
            cursor.execute(
                "SELECT player_1_discord_uid, player_2_discord_uid FROM matches_1v1 WHERE id = :match_id",
                {"match_id": match_id}
            )
            match_data = cursor.fetchone()
            if not match_data:
                return False
            
            player_1_uid, player_2_uid = match_data
            
            # Determine which report column to update
            if player_discord_uid == player_1_uid:
                column = "player_1_report"
            elif player_discord_uid == player_2_uid:
                column = "player_2_report"
            else:
                return False  # Player not in this match
            
            # Update the appropriate report column
            cursor.execute(
                f"UPDATE matches_1v1 SET {column} = :report_value WHERE id = :match_id",
                {"report_value": report_value, "match_id": match_id}
            )
            
            # Check if both players have reported and calculate match_result
            cursor.execute(
                "SELECT player_1_report, player_2_report FROM matches_1v1 WHERE id = :match_id",
                {"match_id": match_id}
            )
            reports = cursor.fetchone()
            if reports and reports[0] is not None and reports[1] is not None:
                p1_report, p2_report = reports
                if p1_report == p2_report:
                    # Reports match
                    match_result = p1_report
                else:
                    # Reports don't match - conflict
                    match_result = -1
                
                # Update match_result
                cursor.execute(
                    "UPDATE matches_1v1 SET match_result = :match_result WHERE id = :match_id",
                    {"match_result": match_result, "match_id": match_id}
                )
            
            conn.commit()
            return cursor.rowcount > 0
    
    def update_match_replay_1v1(
        self,
        match_id: int,
        player_discord_uid: int,
        replay_data: bytes,
        replay_timestamp: str
    ) -> bool:
        """
        Update a player's replay for a 1v1 match.
        
        Args:
            match_id: The ID of the match to update.
            player_discord_uid: The Discord UID of the player uploading the replay.
            replay_data: The replay file data as bytes.
            replay_timestamp: Timestamp when the replay was uploaded.
        
        Returns:
            True if the update was successful, False otherwise.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get match details to determine which player is which
            cursor.execute(
                "SELECT player_1_discord_uid, player_2_discord_uid FROM matches_1v1 WHERE id = :match_id",
                {"match_id": match_id}
            )
            match_data = cursor.fetchone()
            if not match_data:
                return False
            
            player_1_uid, player_2_uid = match_data
            
            # Determine which replay column to update
            if player_discord_uid == player_1_uid:
                replay_column = "player_1_replay"
                timestamp_column = "player_1_replay_time"
            elif player_discord_uid == player_2_uid:
                replay_column = "player_2_replay"
                timestamp_column = "player_2_replay_time"
            else:
                return False  # Player not in this match
            
            # Update the appropriate replay columns
            cursor.execute(
                f"UPDATE matches_1v1 SET {replay_column} = :replay_data, {timestamp_column} = :replay_timestamp WHERE id = :match_id",
                {"replay_data": replay_data, "replay_timestamp": replay_timestamp, "match_id": match_id}
            )
            
            conn.commit()
            rows_affected = cursor.rowcount
            return rows_affected > 0
    
    def update_match_mmr_change(
        self,
        match_id: int,
        mmr_change: int
    ) -> bool:
        """
        Update the MMR change for a 1v1 match.
        
        Args:
            match_id: The ID of the match to update.
            mmr_change: The MMR change amount (positive = player 1 gained, negative = player 2 gained).
        
        Returns:
            True if the update was successful, False otherwise.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE matches_1v1 
                SET mmr_change = :mmr_change
                WHERE id = :match_id
                """,
                {"mmr_change": mmr_change, "match_id": match_id}
            )
            conn.commit()
            return cursor.rowcount > 0

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
            params = {"discord_uid": discord_uid}
            
            if last_chosen_races is not None:
                updates.append("last_chosen_races = :last_chosen_races")
                params["last_chosen_races"] = last_chosen_races
            
            if last_chosen_vetoes is not None:
                updates.append("last_chosen_vetoes = :last_chosen_vetoes")
                params["last_chosen_vetoes"] = last_chosen_vetoes
            
            if not updates:
                return False
            
            # Try to update first
            update_query = f"""
                UPDATE preferences_1v1
                SET {', '.join(updates)}
                WHERE discord_uid = :discord_uid
            """
            cursor.execute(update_query, params)
            
            # If no rows were updated, insert
            if cursor.rowcount == 0:
                cursor.execute(
                    """
                    INSERT INTO preferences_1v1 (
                        discord_uid, last_chosen_races, last_chosen_vetoes
                    )
                    VALUES (:discord_uid, :last_chosen_races, :last_chosen_vetoes)
                    """,
                    {
                        "discord_uid": discord_uid,
                        "last_chosen_races": last_chosen_races,
                        "last_chosen_vetoes": last_chosen_vetoes
                    }
                )
            
            conn.commit()
            return True
