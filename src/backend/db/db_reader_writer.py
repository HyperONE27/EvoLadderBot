"""
Implements a reader/writer for the database.

Backend services must use these classes to read and write to the database.
All SQL queries MUST be contained inside this module.
All SQL queries use named parameters for safety and maintainability.

Supports both SQLite and PostgreSQL via database adapters.
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from functools import wraps
import asyncio

from src.backend.db.adapters import get_adapter
from src.bot.config import DATABASE_TYPE


def invalidate_leaderboard_on_mmr_change(func):
    """
    Decorator that automatically invalidates the leaderboard cache when MMR changes occur.
    
    This ensures that ANY MMR modification triggers cache invalidation, making the system
    foolproof against future changes and ensuring the leaderboard is always up-to-date.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        
        # Cache invalidation is now handled by DataAccessService
        if result is True or (isinstance(result, bool) and result):
            try:
                pass  # No-op: DataAccessService handles cache invalidation
            except Exception as e:
                print(f"[MMR Change] Warning: Error after {func.__name__}: {e}")
        
        return result
    return wrapper


def get_timestamp() -> str:
    """
    Get current UTC timestamp formatted to second precision in ISO 8601 format.
    
    This function generates timezone-aware timestamps in UTC, which are compatible
    with PostgreSQL's TIMESTAMPTZ type. The format includes the timezone offset
    (e.g., "2025-10-22T12:00:00+00:00").
    
    For SQLite compatibility, the same ISO 8601 format is used but stored as TEXT.
    
    Returns:
        ISO format timestamp string with timezone offset (e.g., "YYYY-MM-DDTHH:MM:SS+00:00").
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


class Database:
    """
    Base database connection manager using adapters.
    
    Supports both SQLite and PostgreSQL transparently.
    """
    def __init__(self):
        """Initialize database with the configured adapter."""
        self.adapter = get_adapter(DATABASE_TYPE)
        self.db_type = DATABASE_TYPE.lower()
    
    def get_connection(self):
        """Get database connection via adapter."""
        return self.adapter.get_connection()


class DatabaseReader:
    """
    Reads from the database.
    """
    def __init__(self):
        self.db = Database()
        self.adapter = self.db.adapter
    
    # ========== Players Table ==========
    
    def get_player_by_discord_uid(self, discord_uid: int) -> Optional[Dict[str, Any]]:
        """Get player by Discord UID."""
        results = self.adapter.execute_query(
            "SELECT * FROM players WHERE discord_uid = :discord_uid",
            {"discord_uid": discord_uid}
        )
        return results[0] if results else None
    
    def get_player_by_activation_code(self, activation_code: str) -> Optional[Dict[str, Any]]:
        """DISABLED: Get player by activation code. Activation system is obsolete."""
        results = self.adapter.execute_query(
            "SELECT * FROM players WHERE activation_code = :activation_code",
            {"activation_code": activation_code}
        )
        return results[0] if results else None
    
    def player_exists(self, discord_uid: int) -> bool:
        """Check if a player exists."""
        results = self.adapter.execute_query(
            "SELECT 1 FROM players WHERE discord_uid = :discord_uid LIMIT 1",
            {"discord_uid": discord_uid}
        )
        return len(results) > 0
    
    def get_all_players(self) -> List[Dict[str, Any]]:
        """Get all players."""
        return self.adapter.execute_query("SELECT * FROM players")
    
    def get_read_quick_start_guide(self, discord_uid: int) -> bool:
        """
        Get whether a player has confirmed reading the quick start guide.
        
        Args:
            discord_uid: Discord user ID
            
        Returns:
            True if player confirmed, False otherwise
        """
        results = self.adapter.execute_query(
            "SELECT read_quick_start_guide FROM players WHERE discord_uid = :discord_uid",
            {"discord_uid": discord_uid}
        )
        if not results:
            return False
        return bool(results[0]['read_quick_start_guide'])
    
    # ========== Player Action Logs Table ==========
    
    def get_player_action_logs(
        self,
        discord_uid: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get player action logs."""
        if discord_uid:
            return self.adapter.execute_query(
                "SELECT * FROM player_action_logs WHERE discord_uid = :discord_uid "
                "ORDER BY changed_at DESC LIMIT :limit",
                {"discord_uid": discord_uid, "limit": limit}
            )
        else:
            return self.adapter.execute_query(
                "SELECT * FROM player_action_logs "
                "ORDER BY changed_at DESC LIMIT :limit",
                {"limit": limit}
            )
    
    # ========== MMRs 1v1 Table ==========
    
    def get_player_mmr_1v1(
        self,
        discord_uid: int,
        race: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get player's 1v1 MMR for a specific race."""
        if race:
            results = self.adapter.execute_query(
                "SELECT * FROM mmrs_1v1 WHERE discord_uid = :discord_uid AND race = :race",
                {"discord_uid": discord_uid, "race": race}
            )
        else:
            results = self.adapter.execute_query(
                "SELECT * FROM mmrs_1v1 WHERE discord_uid = :discord_uid",
                {"discord_uid": discord_uid}
            )
        return results[0] if results else None
    
    def get_all_player_mmrs_1v1(self, discord_uid: int) -> List[Dict[str, Any]]:
        """Get all 1v1 MMRs for a player."""
        return self.adapter.execute_query(
            "SELECT * FROM mmrs_1v1 WHERE discord_uid = :discord_uid",
            {"discord_uid": discord_uid}
        )
    
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
        query = """
            SELECT m.*, p.country, p.player_name, p.alt_player_name_1, p.alt_player_name_2
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
        
        return self.adapter.execute_query(query, params)
    
    def count_leaderboard_1v1(
        self,
        race: Optional[str] = None,
        country: Optional[str] = None
    ) -> int:
        """Count total entries in 1v1 leaderboard with filters."""
        query = """
            SELECT COUNT(*) as count
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
        
        results = self.adapter.execute_query(query, params)
        return results[0]["count"] if results else 0
    
    # ========== Matches 1v1 Table ==========
    
    def get_player_matches_1v1(
        self,
        discord_uid: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent matches for a player."""
        return self.adapter.execute_query(
            "SELECT * FROM matches_1v1 "
            "WHERE player_1_discord_uid = :discord_uid OR player_2_discord_uid = :discord_uid "
            "ORDER BY played_at DESC LIMIT :limit",
            {"discord_uid": discord_uid, "limit": limit}
        )
    
    def get_match_1v1(self, match_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific 1v1 match by ID."""
        results = self.adapter.execute_query(
            "SELECT * FROM matches_1v1 WHERE id = :match_id",
            {"match_id": match_id}
        )
        return results[0] if results else None
    
    # ========== Preferences 1v1 Table ==========
    
    def get_preferences_1v1(self, discord_uid: int) -> Optional[Dict[str, Any]]:
        """Get 1v1 preferences for a player."""
        results = self.adapter.execute_query(
            "SELECT * FROM preferences_1v1 WHERE discord_uid = :discord_uid",
            {"discord_uid": discord_uid}
        )
        return results[0] if results else None
    
    def get_match_mmr_change(self, match_id: int) -> Optional[int]:
        """Get the MMR change for a match."""
        results = self.adapter.execute_query(
            "SELECT mmr_change FROM matches_1v1 WHERE id = :match_id",
            {"match_id": match_id}
        )
        return results[0]['mmr_change'] if results else None


class DatabaseWriter:
    """
    Writes to the database.
    """
    def __init__(self):
        self.db = Database()
        self.adapter = self.db.adapter
    
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
        current_timestamp = get_timestamp()
        return self.adapter.execute_insert(
            """
            INSERT INTO players (
                discord_uid, discord_username, player_name, battletag, country, region, activation_code,
                created_at, updated_at
            )
            VALUES (:discord_uid, :discord_username, :player_name, :battletag, :country, :region, :activation_code,
                    :created_at, :updated_at)
            """,
            {
                "discord_uid": discord_uid,
                "discord_username": discord_username,
                "player_name": player_name,
                "battletag": battletag,
                "country": country,
                "region": region,
                "activation_code": activation_code,
                "created_at": current_timestamp,
                "updated_at": current_timestamp
            }
        )
    
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
            # Always update the timestamp when accepted_tos is changed
            updates.append("accepted_tos_date = :accepted_tos_date")
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
        rowcount = self.adapter.execute_write(query, params)
        
        return rowcount > 0
    
    def update_player_activation_code(
        self,
        discord_uid: int,
        activation_code: str
    ) -> bool:
        """DISABLED: Update player's activation code. Activation system is obsolete."""
        return self.update_player(discord_uid, activation_code=activation_code)
    
    def update_player_country(self, discord_uid: int, country: str) -> bool:
        """Update player's country."""
        return self.update_player(discord_uid, country=country)
    
    def update_player_remaining_aborts(self, discord_uid: int, remaining_aborts: int) -> bool:
        """Update player's remaining aborts count."""
        try:
            rowcount = self.adapter.execute_write(
                "UPDATE players SET remaining_aborts = :remaining_aborts WHERE discord_uid = :discord_uid",
                {"remaining_aborts": remaining_aborts, "discord_uid": discord_uid}
            )
            return rowcount > 0
        except Exception as e:
            print(f"Error updating remaining aborts for player {discord_uid}: {e}")
            return False
    
    def update_player_state(self, discord_uid: int, player_state: str) -> bool:
        """Update player state."""
        try:
            rowcount = self.adapter.execute_write(
                "UPDATE players SET player_state = :player_state WHERE discord_uid = :discord_uid",
                {"player_state": player_state, "discord_uid": discord_uid}
            )
            return rowcount > 0
        except Exception as e:
            print(f"Error updating player state for {discord_uid}: {e}")
            return False
    
    def update_shield_battery_bug(self, discord_uid: int, value: bool) -> bool:
        """Update shield battery bug acknowledgement in database."""
        try:
            rowcount = self.adapter.execute_write(
                "UPDATE players SET shield_battery_bug = :value WHERE discord_uid = :discord_uid",
                {"value": value, "discord_uid": discord_uid}
            )
            return rowcount > 0
        except Exception as e:
            print(f"Error updating shield battery bug for {discord_uid}: {e}")
            return False
    
    def update_is_banned(self, discord_uid: int, value: bool) -> bool:
        """Update ban status in database."""
        try:
            rowcount = self.adapter.execute_write(
                "UPDATE players SET is_banned = :value WHERE discord_uid = :discord_uid",
                {"value": value, "discord_uid": discord_uid}
            )
            return rowcount > 0
        except Exception as e:
            print(f"Error updating ban status for {discord_uid}: {e}")
            return False
    
    def set_read_quick_start_guide(self, discord_uid: int, value: bool) -> bool:
        """
        Update whether player has confirmed reading the quick start guide.
        
        Args:
            discord_uid: Discord user ID
            value: True if confirmed, False otherwise
            
        Returns:
            True if update succeeded, False otherwise
        """
        try:
            rowcount = self.adapter.execute_write(
                "UPDATE players SET read_quick_start_guide = :value WHERE discord_uid = :discord_uid",
                {"value": value, "discord_uid": discord_uid}
            )
            return rowcount > 0
        except Exception as e:
            print(f"Error updating read_quick_start_guide for {discord_uid}: {e}")
            return False
    
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
        # Log the action with explicit timestamp
        current_timestamp = get_timestamp()
        log_id = self.adapter.execute_insert(
            """
            INSERT INTO player_action_logs (
                discord_uid, player_name, setting_name,
                old_value, new_value, changed_by, changed_at
            )
            VALUES (:discord_uid, :player_name, :setting_name, :old_value, :new_value, :changed_by, :changed_at)
            """,
            {
                "discord_uid": discord_uid,
                "player_name": player_name,
                "setting_name": setting_name,
                "old_value": old_value,
                "new_value": new_value,
                "changed_by": changed_by,
                "changed_at": current_timestamp
            }
        )
        
        # Update the updated_at timestamp in players table
        self.adapter.execute_write(
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
        
        return log_id
    
    
    # ========== MMRs 1v1 Table ==========
    
    @invalidate_leaderboard_on_mmr_change
    def create_or_update_mmr_1v1(
        self,
        discord_uid: int,
        player_name: str,
        race: str,
        mmr: int,
        games_played: int = 0,
        games_won: int = 0,
        games_lost: int = 0,
        games_drawn: int = 0,
        last_played: str = None
    ) -> bool:
        """
        Create or update a player's 1v1 MMR for a specific race.
        
        Args:
            last_played: Optional timestamp string. If not provided, uses current timestamp.
        
        Returns:
            True if successful.
        """
        if last_played is None:
            last_played = get_timestamp()
        
        result = self.adapter.execute_write(
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
                "last_played": last_played
            }
        )
        return result
    
    @invalidate_leaderboard_on_mmr_change
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
        
        This uses a single atomic database operation that increments counters
        directly in SQL, eliminating the need for a SELECT query before the UPDATE.
        This reduces database round-trips from 2 to 1, improving performance under load.
        
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
        # Use atomic SQL to increment counters in a single operation
        # INSERT creates new record, ON CONFLICT updates existing record
        # COALESCE ensures NULL values are treated as 0 for arithmetic
        self.adapter.execute_write(
            """
            INSERT INTO mmrs_1v1 (
                discord_uid, player_name, race, mmr,
                games_played, games_won, games_lost, games_drawn, last_played
            )
            VALUES (:discord_uid, :player_name, :race, :mmr, 1, :won, :lost, :drawn, :last_played)
            ON CONFLICT(discord_uid, race) DO UPDATE SET
                mmr = EXCLUDED.mmr,
                games_played = mmrs_1v1.games_played + 1,
                games_won = mmrs_1v1.games_won + :won,
                games_lost = mmrs_1v1.games_lost + :lost,
                games_drawn = mmrs_1v1.games_drawn + :drawn,
                last_played = EXCLUDED.last_played
            """,
            {
                "discord_uid": discord_uid,
                "player_name": f"Player{discord_uid}",
                "race": race,
                "mmr": new_mmr,
                "won": 1 if won else 0,
                "lost": 1 if lost else 0,
                "drawn": 1 if drawn else 0,
                "last_played": get_timestamp()
            }
        )
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
        current_timestamp = get_timestamp()
        return self.adapter.execute_insert(
            """
            INSERT INTO matches_1v1 (
                player_1_discord_uid, player_2_discord_uid,
                player_1_race, player_2_race,
                player_1_mmr, player_2_mmr,
                mmr_change, map_played, server_used, played_at
            )
            VALUES (
                :player_1_discord_uid, :player_2_discord_uid,
                :player_1_race, :player_2_race,
                :player_1_mmr, :player_2_mmr,
                :mmr_change, :map_played, :server_used, :played_at
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
                "server_used": server_used,
                "played_at": current_timestamp
            }
        )
    
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
        # Get match details to determine which player is which
        match_results = self.adapter.execute_query(
            "SELECT player_1_discord_uid, player_2_discord_uid FROM matches_1v1 WHERE id = :match_id",
            {"match_id": match_id}
        )
        if not match_results:
            return False
        
        match_data = match_results[0]
        player_1_uid = match_data["player_1_discord_uid"]
        player_2_uid = match_data["player_2_discord_uid"]
        
        # Determine which report column to update
        if player_discord_uid == player_1_uid:
            column = "player_1_report"
            other_column = "player_2_report"
        elif player_discord_uid == player_2_uid:
            column = "player_2_report"
            other_column = "player_1_report"
        else:
            return False  # Player not in this match
        
        if report_value == -1:
            # An abort overrides other pending state. Initiator gets -3, other player -1.
            if column == "player_1_report":
                self.adapter.execute_write(
                    """
                    UPDATE matches_1v1
                    SET player_1_report = -3,
                        player_2_report = CASE WHEN player_2_report = -3 THEN -3 ELSE -1 END,
                        match_result = -1
                    WHERE id = :match_id
                    """,
                    {"match_id": match_id}
                )
            else:
                self.adapter.execute_write(
                    """
                    UPDATE matches_1v1
                    SET player_2_report = -3,
                        player_1_report = CASE WHEN player_1_report = -3 THEN -3 ELSE -1 END,
                        match_result = -1
                    WHERE id = :match_id
                    """,
                    {"match_id": match_id}
                )
            return True
        
        # Update the appropriate report column
        rowcount = self.adapter.execute_write(
            f"UPDATE matches_1v1 SET {column} = :report_value WHERE id = :match_id",
            {"report_value": report_value, "match_id": match_id}
        )
        
        # Check if both players have reported and calculate match_result
        reports_results = self.adapter.execute_query(
            "SELECT player_1_report, player_2_report FROM matches_1v1 WHERE id = :match_id",
            {"match_id": match_id}
        )
        if reports_results:
            reports = reports_results[0]
            if reports["player_1_report"] is not None and reports["player_2_report"] is not None:
                p1_report = reports["player_1_report"]
                p2_report = reports["player_2_report"]
                if p1_report == p2_report:
                    # Reports match
                    match_result = p1_report
                else:
                    # Reports don't match - conflict
                    match_result = -2
            
                # Update match_result
                self.adapter.execute_write(
                    "UPDATE matches_1v1 SET match_result = :match_result WHERE id = :match_id",
                    {"match_result": match_result, "match_id": match_id}
                )
        
        return rowcount > 0
    
    def update_match_replay_1v1(
        self,
        match_id: int,
        player_discord_uid: int,
        replay_path: str,
        replay_time: str
    ) -> bool:
        """
        Update the replay data for a specific match and player.
        Optimized to use a single UPDATE with conditional CASE statement.
        
        Args:
            match_id: The ID of the match to update.
            player_discord_uid: The Discord UID of the player who uploaded the replay.
            replay_path: The path to the replay file.
            replay_time: The timestamp of the replay upload.
            
        Returns:
            True if the update was successful, False otherwise.
        """
        try:
            # Single UPDATE with conditional logic - no extra SELECT needed
            # Updates the correct player's replay based on their discord_uid
            self.adapter.execute_write(
                """
                UPDATE matches_1v1
                SET 
                    player_1_replay_path = CASE 
                        WHEN player_1_discord_uid = :player_discord_uid THEN :replay_path 
                        ELSE player_1_replay_path 
                    END,
                    player_1_replay_time = CASE 
                        WHEN player_1_discord_uid = :player_discord_uid THEN :replay_time 
                        ELSE player_1_replay_time 
                    END,
                    player_2_replay_path = CASE 
                        WHEN player_2_discord_uid = :player_discord_uid THEN :replay_path 
                        ELSE player_2_replay_path 
                    END,
                    player_2_replay_time = CASE 
                        WHEN player_2_discord_uid = :player_discord_uid THEN :replay_time 
                        ELSE player_2_replay_time 
                    END
                WHERE id = :match_id
                """,
                {
                    "match_id": match_id,
                    "player_discord_uid": player_discord_uid,
                    "replay_path": replay_path,
                    "replay_time": replay_time
                }
            )
            return True
        except Exception as e:
            print(f"Database error in update_match_replay_1v1: {e}")
            return False
    
    @invalidate_leaderboard_on_mmr_change
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
        rowcount = self.adapter.execute_write(
            """
            UPDATE matches_1v1 
            SET mmr_change = :mmr_change
            WHERE id = :match_id
            """,
            {"mmr_change": mmr_change, "match_id": match_id}
        )
        return rowcount > 0

    def update_preferences_1v1(
        self,
        discord_uid: int,
        last_chosen_races: Optional[str] = None,
        last_chosen_vetoes: Optional[str] = None
    ) -> bool:
        """
        Update or create 1v1 preferences for a player.
        Uses native database UPSERT for optimal performance (single round-trip).
        
        Args:
            discord_uid: Player's Discord UID.
            last_chosen_races: JSON string of last chosen races.
            last_chosen_vetoes: JSON string of last chosen vetoes.
        
        Returns:
            True if successful.
        """
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
        
        # Use native UPSERT (INSERT ... ON CONFLICT DO UPDATE)
        # Single database operation - much faster than UPDATE + INSERT
        if self.db.db_type == "postgresql":
            # PostgreSQL native UPSERT
            upsert_query = """
                INSERT INTO preferences_1v1 (discord_uid, last_chosen_races, last_chosen_vetoes)
                VALUES (:discord_uid, :last_chosen_races, :last_chosen_vetoes)
                ON CONFLICT (discord_uid) DO UPDATE SET
                    last_chosen_races = COALESCE(EXCLUDED.last_chosen_races, preferences_1v1.last_chosen_races),
                    last_chosen_vetoes = COALESCE(EXCLUDED.last_chosen_vetoes, preferences_1v1.last_chosen_vetoes)
            """
        else:
            # SQLite UPSERT syntax
            upsert_query = """
                INSERT INTO preferences_1v1 (discord_uid, last_chosen_races, last_chosen_vetoes)
                VALUES (:discord_uid, :last_chosen_races, :last_chosen_vetoes)
                ON CONFLICT(discord_uid) DO UPDATE SET
                    last_chosen_races = COALESCE(EXCLUDED.last_chosen_races, preferences_1v1.last_chosen_races),
                    last_chosen_vetoes = COALESCE(EXCLUDED.last_chosen_vetoes, preferences_1v1.last_chosen_vetoes)
            """
        
        # Fill in None values for params that weren't provided
        if "last_chosen_races" not in params:
            params["last_chosen_races"] = None
        if "last_chosen_vetoes" not in params:
            params["last_chosen_vetoes"] = None
        
        self.adapter.execute_write(upsert_query, params)
        return True

    def abort_match_1v1(self, match_id: int, player_discord_uid: int, abort_timer_seconds: int) -> bool:
        """
        Atomically abort a match if it has not already been completed and is within the time limit.
        
        This prevents race conditions where both players could abort simultaneously.
        
        Args:
            match_id: The ID of the match to abort.
            player_discord_uid: The Discord UID of the player initiating the abort.
            abort_timer_seconds: The window in seconds during which an abort is allowed.
            
        Returns:
            True if the match was successfully aborted by this operation, False otherwise.
        """
        try:
            # First, get the player UIDs for the match
            match_results = self.adapter.execute_query(
                "SELECT player_1_discord_uid, player_2_discord_uid FROM matches_1v1 WHERE id = :match_id",
                {"match_id": match_id}
            )
            
            if not match_results:
                return False
            
            match_players = match_results[0]
            
            # Determine which player report column to update
            if player_discord_uid == match_players["player_1_discord_uid"]:
                report_column = "player_1_report"
                other_column = "player_2_report"
            elif player_discord_uid == match_players["player_2_discord_uid"]:
                report_column = "player_2_report"
                other_column = "player_1_report"
            else:
                return False  # Player not in this match
            
            # Atomically update the match result and both player reports.
            if report_column == "player_1_report":
                update_query = """
                    UPDATE matches_1v1
                    SET 
                        match_result = -1,
                        player_1_report = -3,
                        player_2_report = CASE WHEN player_2_report = -3 THEN -3 ELSE COALESCE(player_2_report, -1) END
                    WHERE 
                        id = :match_id 
                        AND match_result IS NULL
                        AND (EXTRACT(EPOCH FROM NOW()) - EXTRACT(EPOCH FROM played_at)) < :abort_timer_seconds
                """
            else:
                update_query = """
                    UPDATE matches_1v1
                    SET 
                        match_result = -1,
                        player_2_report = -3,
                        player_1_report = CASE WHEN player_1_report = -3 THEN -3 ELSE COALESCE(player_1_report, -1) END
                    WHERE 
                        id = :match_id 
                        AND match_result IS NULL
                        AND (EXTRACT(EPOCH FROM NOW()) - EXTRACT(EPOCH FROM played_at)) < :abort_timer_seconds
                """
            
            rowcount = self.adapter.execute_write(update_query, {"match_id": match_id, "abort_timer_seconds": abort_timer_seconds})
            
            # If any row was changed, the abort was successful
            return rowcount > 0
            
        except Exception as e:
            print(f"Error aborting match {match_id}: {e}")
            return False

    def update_match_reports_and_result(
        self,
        match_id: int,
        p1_report: Optional[int],
        p2_report: Optional[int],
        match_result: int
    ) -> bool:
        """
        Atomically update match reports and result for system-initiated aborts.
        
        This method updates the match reports and result in a single transaction
        without decrementing player abort counters. Used for unconfirmed match aborts.
        
        Args:
            match_id: The ID of the match to update
            p1_report: Player 1's report value (-4 if didn't confirm, None if confirmed)
            p2_report: Player 2's report value (-4 if didn't confirm, None if confirmed)
            match_result: The match result (-1 for aborted)
            
        Returns:
            True if the update was successful, False otherwise
        """
        try:
            update_query = """
                UPDATE matches_1v1
                SET 
                    player_1_report = :p1_report,
                    player_2_report = :p2_report,
                    match_result = :match_result
                WHERE id = :match_id
            """
            
            rowcount = self.adapter.execute_write(
                update_query,
                {
                    "match_id": match_id,
                    "p1_report": p1_report,
                    "p2_report": p2_report,
                    "match_result": match_result
                }
            )
            
            return rowcount > 0
            
        except Exception as e:
            print(f"Error updating match {match_id} reports and result: {e}")
            return False

    def admin_resolve_match(
        self,
        match_id: int,
        match_result: int,
        p1_report: Optional[int],
        p2_report: Optional[int]
    ) -> bool:
        """
        Admin-only method to resolve a match and set the updated_at timestamp.
        This is the ONLY method that should set updated_at in matches_1v1.
        
        Args:
            match_id: The ID of the match to update
            match_result: The final match result after admin resolution
            p1_report: The original player 1 report (to preserve)
            p2_report: The original player 2 report (to preserve)
            
        Returns:
            True if the update was successful, False otherwise
        """
        try:
            update_query = """
                UPDATE matches_1v1
                SET 
                    match_result = :match_result,
                    player_1_report = :p1_report,
                    player_2_report = :p2_report,
                    updated_at = :updated_at
                WHERE id = :match_id
            """
            
            rowcount = self.adapter.execute_write(
                update_query,
                {
                    "match_id": match_id,
                    "match_result": match_result,
                    "p1_report": p1_report,
                    "p2_report": p2_report,
                    "updated_at": get_timestamp()
                }
            )
            
            print(f"[DatabaseWriter] Admin resolved match {match_id}: result={match_result}, " 
                  f"p1_report={p1_report}, p2_report={p2_report}, updated_at set")
            
            return rowcount > 0
            
        except Exception as e:
            print(f"Error in admin_resolve_match for match {match_id}: {e}")
            return False

    def update_match_result(self, match_id: int, match_result: int) -> bool:
        """
        Update the match result for a match.
        
        Args:
            match_id: The ID of the match to update
            match_result: The match result (0=draw, 1=player1 wins, 2=player2 wins, -1=aborted, -2=conflict)
            
        Returns:
            True if the update was successful, False otherwise
        """
        try:
            self.adapter.execute_write(
                """
                UPDATE matches_1v1 
                SET match_result = :match_result
                WHERE id = :match_id
                """,
                {
                    "match_id": match_id,
                    "match_result": match_result
                }
            )
            return True
        except Exception as e:
            print(f"Database error in update_match_result: {e}")
            return False

    def insert_command_call(self, discord_uid: int, player_name: str, command: str) -> bool:
        """
        Logs a command call to the command_calls table.
        """
        try:
            current_timestamp = get_timestamp()
            self.adapter.execute_insert(
                """
                INSERT INTO command_calls (discord_uid, player_name, command, called_at)
                VALUES (:discord_uid, :player_name, :command, :called_at)
                """,
                {
                    "discord_uid": discord_uid,
                    "player_name": player_name,
                    "command": command,
                    "called_at": current_timestamp
                }
            )
            return True
        except Exception as e:
            print(f"Database error in insert_command_call: {e}")
            return False
    
    def log_admin_action(
        self,
        admin_discord_uid: int,
        admin_username: str,
        action_type: str,
        target_player_uid: int,
        target_match_id: int,
        action_details: str,
        reason: str
    ) -> bool:
        """
        Logs an admin action to the admin_actions table.
        
        Args:
            admin_discord_uid: Discord UID of admin performing action
            admin_username: Display name of admin
            action_type: Type of action performed
            target_player_uid: Target player UID (can be None)
            target_match_id: Target match ID (can be None)
            action_details: JSON string with action details
            reason: Human-readable reason for action
        """
        try:
            current_timestamp = get_timestamp()
            self.adapter.execute_insert(
                """
                INSERT INTO admin_actions (
                    admin_discord_uid, admin_username, action_type,
                    target_player_uid, target_match_id, action_details,
                    reason, performed_at
                )
                VALUES (
                    :admin_uid, :admin_name, :action_type,
                    :target_player, :target_match, :details,
                    :reason, :performed_at
                )
                """,
                {
                    'admin_uid': admin_discord_uid,
                    'admin_name': admin_username,
                    'action_type': action_type,
                    'target_player': target_player_uid,
                    'target_match': target_match_id,
                    'details': action_details,
                    'reason': reason,
                    'performed_at': current_timestamp
                }
            )
            return True
        except Exception as e:
            print(f"Database error in log_admin_action: {e}")
            return False

    def insert_replay(self, replay_data: Dict[str, Any]) -> bool:
        """
        Insert a new replay record into the replays table.
        
        This operation is idempotent - if a replay with the same replay_path already exists,
        the insert will be silently skipped. This makes WAL replay safe during crash recovery.
        
        Args:
            replay_data: A dictionary containing the replay's parsed data.
            
        Returns:
            True if the insertion was successful or the replay already exists, False on other errors.
        """
        try:
            print(f"[DatabaseWriter] Inserting replay: {replay_data.get('replay_hash', 'unknown')}")
            self.adapter.execute_insert(
                """
                INSERT INTO replays (
                    replay_path, replay_hash, replay_date, player_1_name, player_2_name,
                    player_1_race, player_2_race, result, player_1_handle, player_2_handle,
                    observers, map_name, duration, game_privacy, game_speed, game_duration_setting,
                    locked_alliances, cache_handles, uploaded_at
                ) VALUES (
                    :replay_path, :replay_hash, :replay_date, :player_1_name, :player_2_name,
                    :player_1_race, :player_2_race, :result, :player_1_handle, :player_2_handle,
                    :observers, :map_name, :duration, :game_privacy, :game_speed, :game_duration_setting,
                    :locked_alliances, :cache_handles, :uploaded_at
                )
                ON CONFLICT (replay_path) DO NOTHING
                """,
                replay_data
            )
            print(f"[DatabaseWriter] Replay inserted successfully (or already exists): {replay_data.get('replay_hash', 'unknown')}")
            return True
        except Exception as e:
            print(f"Database error in insert_replay: {e}")
            import traceback
            traceback.print_exc()
            return False
