"""
DataAccessService - Unified data access layer with in-memory hot tables.

This service acts as a Facade pattern providing a single entry point for all
application data access. It manages in-memory Polars DataFrames for hot tables
(players, mmrs_1v1, preferences_1v1, matches_1v1, replays) and provides
asynchronous write-back to the persistent database.

Architecture:
- Hot tables are stored in-memory as Polars DataFrames for sub-millisecond reads
- All writes update the in-memory DataFrame instantly, then queue async DB writes
- Write-only tables (player_action_logs, command_calls) use async-only writes
- Single source of truth for all data access in the application

Performance Benefits:
- Player info lookups: <2ms (was 500-800ms)
- Abort count lookups: <2ms (was 400-600ms)
- Match data lookups: <2ms (was 200-300ms)
- All writes are non-blocking
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta, timezone

import aiosqlite
import polars as pl

from src.backend.core.config import WAL_PATH
from src.backend.db.db_reader_writer import DatabaseReader, DatabaseWriter


class WriteJobType(Enum):
    """Types of database write operations."""
    UPDATE_PLAYER = "update_player"
    CREATE_PLAYER = "create_player"
    UPDATE_MMR = "update_mmr"
    CREATE_MMR = "create_mmr"
    UPDATE_PREFERENCES = "update_preferences"
    CREATE_MATCH = "create_match"
    UPDATE_MATCH = "update_match"
    UPDATE_MATCH_REPORT = "update_match_report"
    UPDATE_MATCH_MMR_CHANGE = "update_match_mmr_change"
    INSERT_REPLAY = "insert_replay"
    LOG_PLAYER_ACTION = "log_player_action"
    INSERT_COMMAND_CALL = "insert_command_call"
    LOG_ADMIN_ACTION = "log_admin_action"
    ABORT_MATCH = "abort_match"
    SYSTEM_ABORT_UNCONFIRMED = "system_abort_unconfirmed"
    ADMIN_RESOLVE_MATCH = "admin_resolve_match"
    UPDATE_PLAYER_STATE = "update_player_state"
    UPDATE_SHIELD_BATTERY_BUG = "update_shield_battery_bug"
    UPDATE_IS_BANNED = "update_is_banned"
    UPDATE_READ_QUICK_START_GUIDE = "update_read_quick_start_guide"


@dataclass
class WriteJob:
    """Represents a queued database write operation."""
    job_type: WriteJobType
    data: Dict[str, Any]
    timestamp: float


class DataAccessService:
    """
    Singleton service providing unified data access with in-memory hot tables.
    
    This is the ONLY class the rest of the application should use for data access.
    """
    
    _instance: Optional['DataAccessService'] = None
    _initialized: bool = False
    
    def __new__(cls):
        """Singleton pattern - only one instance allowed."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the service (only runs once due to singleton pattern)."""
        # Guard: Don't re-initialize if __init__ was already called
        if hasattr(self, '_init_done') and self._init_done:
            return
        
        if DataAccessService._initialized:
            return
        
        print("[DataAccessService] Initializing...")
        
        # Database access for initial load and write-back
        self._db_reader = DatabaseReader()
        self._db_writer = DatabaseWriter()
        
        # In-memory DataFrames for hot tables
        self._players_df: Optional[pl.DataFrame] = None
        self._mmrs_1v1_df: Optional[pl.DataFrame] = None
        self._preferences_1v1_df: Optional[pl.DataFrame] = None
        self._matches_1v1_df: Optional[pl.DataFrame] = None
        self._replays_df: Optional[pl.DataFrame] = None
        
        # System state
        self._shutdown_event = asyncio.Event()
        self._writer_task: Optional[asyncio.Task] = None
        self._reconciliation_task: Optional[asyncio.Task] = None
        self._write_queue: asyncio.Queue = asyncio.Queue()
        self._write_event = asyncio.Event()  # Event-driven notification for write worker
        self._init_lock = asyncio.Lock()
        self._mmr_lock = asyncio.Lock()  # Lock for thread-safe MMR DataFrame updates
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None  # Store a reference to the main loop

        # Write-Ahead Log (WAL) for durable write queue
        # Path is configured via environment variable (PERSISTENT_VOLUME_PATH)
        self._wal_path = WAL_PATH
        self._wal_db: Optional[aiosqlite.Connection] = None

        # Performance stats
        self._write_queue_size_peak = 0
        self._total_writes_queued = 0
        self._total_writes_completed = 0
        
        self._init_done = True  # Mark that __init__ has completed
        print("[DataAccessService] Singleton initialized (DataFrames not loaded yet)")
    
    async def initialize_async(self) -> None:
        """
        Async initialization - loads all data and starts background worker.
        
        This MUST be called during bot startup after the event loop is running.
        """
        async with self._init_lock:
            if DataAccessService._initialized:
                print("[DataAccessService] Already initialized, skipping")
                return
            
            print("[DataAccessService] Starting async initialization...")
            self._main_loop = asyncio.get_running_loop() # Store the loop on which this was initialized
            start_time = time.time()
            
            # Initialize Write-Ahead Log (WAL)
            await self._initialize_wal()
            
            # Load all hot tables into memory
            await self._load_all_tables()
            
            # Run initial reconciliation on startup (only if in midnight-1AM UTC window and not already run)
            if await self._should_run_startup_reconciliation():
                await self.reconcile_mmr_stats_from_matches()
                await self._save_reconciliation_timestamp()
            else:
                print("[MMR Reconciliation] Skipping startup reconciliation (outside window or already run)")
            
            # Start background write worker
            self._writer_task = self._main_loop.create_task(self._db_writer_worker())
            
            # Start daily reconciliation background task
            self._reconciliation_task = self._main_loop.create_task(self._reconciliation_worker())
            
            elapsed = (time.time() - start_time) * 1000
            print(f"[DataAccessService] Async initialization complete in {elapsed:.2f}ms")
            
            self._initialized = True
    
    async def _load_all_tables(self) -> None:
        """Load all hot tables from the database into Polars DataFrames."""
        print("[DataAccessService] Loading all tables from database...")
        
        loop = asyncio.get_running_loop()
        
        # Load players table
        print("[DataAccessService]   Loading players...")
        players_data = await loop.run_in_executor(None, self._db_reader.get_all_players)
        if players_data:
            self._players_df = pl.DataFrame(players_data, infer_schema_length=None)
        else:
            # Create empty DataFrame with schema matching PostgreSQL players table
            self._players_df = pl.DataFrame({
                "id": pl.Series([], dtype=pl.Int64),
                "discord_uid": pl.Series([], dtype=pl.Int64),
                "discord_username": pl.Series([], dtype=pl.Utf8),
                "player_name": pl.Series([], dtype=pl.Utf8),
                "battletag": pl.Series([], dtype=pl.Utf8),
                "alt_player_name_1": pl.Series([], dtype=pl.Utf8),
                "alt_player_name_2": pl.Series([], dtype=pl.Utf8),
                "country": pl.Series([], dtype=pl.Utf8),
                "region": pl.Series([], dtype=pl.Utf8),
                "accepted_tos": pl.Series([], dtype=pl.Boolean),
                "accepted_tos_date": pl.Series([], dtype=pl.Utf8),
                "completed_setup": pl.Series([], dtype=pl.Boolean),
                "completed_setup_date": pl.Series([], dtype=pl.Utf8),
                "activation_code": pl.Series([], dtype=pl.Utf8),
                "created_at": pl.Series([], dtype=pl.Utf8),
                "updated_at": pl.Series([], dtype=pl.Utf8),
                "remaining_aborts": pl.Series([], dtype=pl.Int32),
                "player_state": pl.Series([], dtype=pl.Utf8),
                "shield_battery_bug": pl.Series([], dtype=pl.Boolean),
                "is_banned": pl.Series([], dtype=pl.Boolean),
                "read_quick_start_guide": pl.Series([], dtype=pl.Boolean),
            })
        print(f"[DataAccessService]   Players loaded: {len(self._players_df)} rows, size: {self._players_df.estimated_size('mb'):.2f} MB")
        
        # Load mmrs_1v1 table - FIRST load raw data to detect bad entries
        print("[DataAccessService]   Loading mmrs_1v1...")
        mmrs_raw_data = await loop.run_in_executor(
            None,
            self._db_reader.adapter.execute_query,
            "SELECT * FROM mmrs_1v1",
            {}
        )
        if mmrs_raw_data:
            self._mmrs_1v1_df = pl.DataFrame(mmrs_raw_data, infer_schema_length=None)
            print(f"[DataAccessService]   MMRs schema: {self._mmrs_1v1_df.schema}")
            print(f"[DataAccessService]   MMRs columns: {self._mmrs_1v1_df.columns}")
        else:
            # Create empty DataFrame with schema matching PostgreSQL mmrs_1v1 table
            self._mmrs_1v1_df = pl.DataFrame({
                "id": pl.Series([], dtype=pl.Int64),
                "discord_uid": pl.Series([], dtype=pl.Int64),
                "player_name": pl.Series([], dtype=pl.Utf8),
                "race": pl.Series([], dtype=pl.Utf8),
                "mmr": pl.Series([], dtype=pl.Int64),
                "games_played": pl.Series([], dtype=pl.Int64),
                "games_won": pl.Series([], dtype=pl.Int64),
                "games_lost": pl.Series([], dtype=pl.Int64),
                "games_drawn": pl.Series([], dtype=pl.Int64),
                "last_played": pl.Series([], dtype=pl.Datetime),
            })
        print(f"[DataAccessService]   MMRs loaded: {len(self._mmrs_1v1_df)} rows, size: {self._mmrs_1v1_df.estimated_size('mb'):.2f} MB")
        
        # Clean up bad player_name entries (player{discord_id} format)
        if not self._mmrs_1v1_df.is_empty() and self._players_df is not None:
            import re
            print("[DataAccessService]   Checking for bad player_name entries in MMRs...")
            
            # Find rows with suspicious player names matching "Player123456" or "player123456"
            bad_name_pattern = re.compile(r'^[Pp]layer\d+$')
            corrections_made = []
            
            # Iterate over rows using to_dicts() for proper access
            for row in self._mmrs_1v1_df.to_dicts():
                player_name = row['player_name']
                discord_uid = row['discord_uid']
                race = row['race']
                
                if player_name and bad_name_pattern.match(str(player_name)):
                    print(f"[DataAccessService]   Found bad entry: discord_uid={discord_uid}, race={race}, player_name='{player_name}'")
                    
                    # Found a bad entry - look up correct name from players table
                    player_info_rows = self._players_df.filter(pl.col('discord_uid') == discord_uid)
                    
                    if len(player_info_rows) > 0:
                        correct_name = player_info_rows[0, 'player_name']
                        if correct_name is None or bad_name_pattern.match(str(correct_name)):
                            # Fall back to discord_username if player_name is also bad/missing
                            correct_name = player_info_rows[0, 'discord_username']
                        
                        if correct_name and not bad_name_pattern.match(str(correct_name)):
                            # Update in-memory dataframe
                            mask = (pl.col('discord_uid') == discord_uid) & (pl.col('race') == race)
                            self._mmrs_1v1_df = self._mmrs_1v1_df.with_columns(
                                pl.when(mask)
                                .then(pl.lit(correct_name))
                                .otherwise(pl.col('player_name'))
                                .alias('player_name')
                            )
                            
                            corrections_made.append({
                                'discord_uid': discord_uid,
                                'race': race,
                                'old_name': player_name,
                                'new_name': correct_name
                            })
                            
                            print(f"[DataAccessService]   Fixed player_name: discord_uid={discord_uid}, race={race}, '{player_name}' -> '{correct_name}'")
            
            # Queue database writes to fix Supabase entries
            if corrections_made:
                print(f"[DataAccessService]   Queueing {len(corrections_made)} database corrections...")
                for correction in corrections_made:
                    job = WriteJob(
                        job_type=WriteJobType.UPDATE_MMR,
                        data={
                            'discord_uid': correction['discord_uid'],
                            'race': correction['race'],
                            'player_name': correction['new_name']
                        },
                        timestamp=time.time()
                    )
                    # Queue the write (will be processed by write worker)
                    self._write_queue.put_nowait(job)
                
                # Notify the write worker that there are jobs to process
                self._write_event.set()
                
                print(f"[DataAccessService]   Corrected {len(corrections_made)} bad player_name entries")
        
        # Load preferences_1v1 table
        print("[DataAccessService]   Loading preferences_1v1...")
        # Load all preferences (should be one row per player at most)
        prefs_data = await loop.run_in_executor(
            None,
            self._db_reader.adapter.execute_query,
            "SELECT * FROM preferences_1v1",
            {}
        )
        if prefs_data:
            self._preferences_1v1_df = pl.DataFrame(prefs_data, infer_schema_length=None)
        else:
            # Create empty DataFrame with schema matching PostgreSQL preferences_1v1 table
            self._preferences_1v1_df = pl.DataFrame({
                "id": pl.Series([], dtype=pl.Int64),
                "discord_uid": pl.Series([], dtype=pl.Int64),
                "last_chosen_races": pl.Series([], dtype=pl.Utf8),
                "last_chosen_vetoes": pl.Series([], dtype=pl.Utf8),
            })
        print(f"[DataAccessService]   Preferences loaded: {len(self._preferences_1v1_df)} rows, size: {self._preferences_1v1_df.estimated_size('mb'):.2f} MB")
        
        # Load matches_1v1 table
        print("[DataAccessService]   Loading matches_1v1...")
        # Load all matches
        matches_data = await loop.run_in_executor(
            None,
            self._db_reader.adapter.execute_query,
            "SELECT * FROM matches_1v1 ORDER BY played_at DESC",
            {}
        )
        if matches_data:
            self._matches_1v1_df = pl.DataFrame(matches_data, infer_schema_length=None)
        else:
            # Create empty DataFrame with complete schema matching matches_1v1 table
            self._matches_1v1_df = pl.DataFrame({
                "id": pl.Series([], dtype=pl.Int64),
                "player_1_discord_uid": pl.Series([], dtype=pl.Int64),
                "player_2_discord_uid": pl.Series([], dtype=pl.Int64),
                "player_1_race": pl.Series([], dtype=pl.Utf8),
                "player_2_race": pl.Series([], dtype=pl.Utf8),
                "map_played": pl.Series([], dtype=pl.Utf8),
                "server_choice": pl.Series([], dtype=pl.Utf8),
                "player_1_mmr": pl.Series([], dtype=pl.Int64),
                "player_2_mmr": pl.Series([], dtype=pl.Int64),
                "mmr_change": pl.Series([], dtype=pl.Float64),
                "played_at": pl.Series([], dtype=pl.Utf8),
                "updated_at": pl.Series([], dtype=pl.Utf8),
                "player_1_report": pl.Series([], dtype=pl.Int64),
                "player_2_report": pl.Series([], dtype=pl.Int64),
                "match_result": pl.Series([], dtype=pl.Int64),
                "player_1_replay_path": pl.Series([], dtype=pl.Utf8),
                "player_2_replay_path": pl.Series([], dtype=pl.Utf8),
                "player_1_replay_time": pl.Series([], dtype=pl.Utf8),
                "player_2_replay_time": pl.Series([], dtype=pl.Utf8)
            })
        print(f"[DataAccessService]   Matches loaded: {len(self._matches_1v1_df)} rows, size: {self._matches_1v1_df.estimated_size('mb'):.2f} MB")
        
        # Load replays table
        print("[DataAccessService]   Loading replays...")
        # Load all replays
        replays_data = await loop.run_in_executor(
            None,
            self._db_reader.adapter.execute_query,
            "SELECT * FROM replays ORDER BY id DESC",
            {}
        )
        if replays_data:
            self._replays_df = pl.DataFrame(replays_data, infer_schema_length=None)
        else:
            self._replays_df = pl.DataFrame({
                "id": pl.Series([], dtype=pl.Int64),
                "replay_path": pl.Series([], dtype=pl.Utf8),
                "replay_hash": pl.Series([], dtype=pl.Utf8),
                "replay_date": pl.Series([], dtype=pl.Utf8),
                "player_1_name": pl.Series([], dtype=pl.Utf8),
                "player_2_name": pl.Series([], dtype=pl.Utf8),
                "player_1_race": pl.Series([], dtype=pl.Utf8),
                "player_2_race": pl.Series([], dtype=pl.Utf8),
                "result": pl.Series([], dtype=pl.Int64),
                "player_1_handle": pl.Series([], dtype=pl.Utf8),
                "player_2_handle": pl.Series([], dtype=pl.Utf8),
                "observers": pl.Series([], dtype=pl.Utf8),
                "map_name": pl.Series([], dtype=pl.Utf8),
                "duration": pl.Series([], dtype=pl.Int64),
                "game_privacy": pl.Series([], dtype=pl.Utf8),
                "game_speed": pl.Series([], dtype=pl.Utf8),
                "game_duration_setting": pl.Series([], dtype=pl.Utf8),
                "locked_alliances": pl.Series([], dtype=pl.Utf8),
                "cache_handles": pl.Series([], dtype=pl.Utf8),
                "uploaded_at": pl.Series([], dtype=pl.Utf8),
            })
        print(f"[DataAccessService]   Replays loaded: {len(self._replays_df)} rows, size: {self._replays_df.estimated_size('mb'):.2f} MB")
    
    async def reconcile_mmr_stats_from_matches(self) -> None:
        """
        Reconcile mmrs_1v1 game statistics from matches_1v1 source of truth.
        
        Aggregates all finalized matches (match_result in 0,1,2) and overwrites:
        - games_played, games_won, games_lost, games_drawn
        - last_played timestamp
        
        Logs summary of changes to console.
        """
        start_time = time.time()
        now_utc = datetime.now(timezone.utc)
        print(f"[MMR Reconciliation] Starting reconciliation at {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
        if self._matches_1v1_df is None or self._mmrs_1v1_df is None:
            print("[MMR Reconciliation] DataFrames not loaded, skipping reconciliation")
            return
        
        if self._matches_1v1_df.is_empty():
            print("[MMR Reconciliation] No matches to process")
            return
        
        # Filter to finalized matches only (0=draw, 1=player1 win, 2=player2 win)
        finalized_matches = self._matches_1v1_df.filter(
            pl.col("match_result").is_in([0, 1, 2])
        )
        
        print(f"[MMR Reconciliation] Processing {len(finalized_matches)} finalized matches")
        
        if finalized_matches.is_empty():
            print("[MMR Reconciliation] No finalized matches to process")
            return
        
        # Build aggregation for player 1
        p1_data = finalized_matches.select([
            pl.col("player_1_discord_uid").alias("discord_uid"),
            pl.col("player_1_race").alias("race"),
            pl.col("played_at"),
            pl.col("match_result")
        ])
        
        # Build aggregation for player 2
        p2_data = finalized_matches.select([
            pl.col("player_2_discord_uid").alias("discord_uid"),
            pl.col("player_2_race").alias("race"),
            pl.col("played_at"),
            pl.col("match_result")
        ])
        
        # Combine both players' data
        all_player_data = pl.concat([p1_data, p2_data])
        
        # For player 1: win=1, loss=2, draw=0
        # For player 2: win=2, loss=1, draw=0
        # We need to track which perspective each row is from
        p1_data = p1_data.with_columns([
            (pl.col("match_result") == 1).cast(pl.Int64).alias("won"),
            (pl.col("match_result") == 2).cast(pl.Int64).alias("lost"),
            (pl.col("match_result") == 0).cast(pl.Int64).alias("drawn")
        ])
        
        p2_data = p2_data.with_columns([
            (pl.col("match_result") == 2).cast(pl.Int64).alias("won"),
            (pl.col("match_result") == 1).cast(pl.Int64).alias("lost"),
            (pl.col("match_result") == 0).cast(pl.Int64).alias("drawn")
        ])
        
        # Combine and aggregate
        combined = pl.concat([p1_data, p2_data])
        
        aggregated = combined.group_by(["discord_uid", "race"]).agg([
            pl.count().alias("games_played"),
            pl.sum("won").alias("games_won"),
            pl.sum("lost").alias("games_lost"),
            pl.sum("drawn").alias("games_drawn"),
            pl.max("played_at").alias("last_played")
        ])
        
        print(f"[MMR Reconciliation] Aggregated stats for {len(aggregated)} (discord_uid, race) combinations")
        
        # Now update mmrs_1v1_df with these values
        updates_made = 0
        players_affected = set()
        
        async with self._mmr_lock:
            for row in aggregated.iter_rows(named=True):
                discord_uid = row["discord_uid"]
                race = row["race"]
                games_played = row["games_played"]
                games_won = row["games_won"]
                games_lost = row["games_lost"]
                games_drawn = row["games_drawn"]
                last_played = row["last_played"]
                
                # Find the corresponding row in mmrs_1v1_df
                mask = (pl.col("discord_uid") == discord_uid) & (pl.col("race") == race)
                matching_rows = self._mmrs_1v1_df.filter(mask)
                
                if len(matching_rows) > 0:
                    # Update the existing row
                    self._mmrs_1v1_df = self._mmrs_1v1_df.with_columns([
                        pl.when(mask).then(pl.lit(games_played)).otherwise(pl.col("games_played")).alias("games_played"),
                        pl.when(mask).then(pl.lit(games_won)).otherwise(pl.col("games_won")).alias("games_won"),
                        pl.when(mask).then(pl.lit(games_lost)).otherwise(pl.col("games_lost")).alias("games_lost"),
                        pl.when(mask).then(pl.lit(games_drawn)).otherwise(pl.col("games_drawn")).alias("games_drawn"),
                        pl.when(mask).then(pl.lit(last_played)).otherwise(pl.col("last_played")).alias("last_played")
                    ])
                    
                    # Queue database update
                    player_name = matching_rows[0, "player_name"]
                    mmr = matching_rows[0, "mmr"]
                    
                    job = WriteJob(
                        job_type=WriteJobType.UPDATE_MMR,
                        data={
                            "discord_uid": discord_uid,
                            "player_name": player_name,
                            "race": race,
                            "mmr": mmr,
                            "games_played": games_played,
                            "games_won": games_won,
                            "games_lost": games_lost,
                            "games_drawn": games_drawn
                        },
                        timestamp=time.time()
                    )
                    self._write_queue.put_nowait(job)
                    
                    updates_made += 1
                    players_affected.add(discord_uid)
        
        # Notify write worker
        if updates_made > 0:
            self._write_event.set()
        
        elapsed_ms = (time.time() - start_time) * 1000
        print(f"[MMR Reconciliation] Updated {updates_made} mmrs_1v1 records ({len(players_affected)} players affected)")
        print(f"[MMR Reconciliation] Completed in {elapsed_ms:.2f}ms")
    
    async def _should_run_startup_reconciliation(self) -> bool:
        """
        Determine if startup reconciliation should run.
        
        Only runs if current time is between midnight and 1 AM UTC.
        Will run on EVERY startup during this window (useful for testing/restarts).
        
        Returns:
            bool: True if reconciliation should run
        """
        now_utc = datetime.now(timezone.utc)
        current_hour = now_utc.hour
        
        # Check if we're in the midnight-1AM UTC window
        if current_hour != 0:
            print(f"[MMR Reconciliation] Current hour is {current_hour} UTC, outside midnight-1AM window")
            return False
        
        print(f"[MMR Reconciliation] In midnight-1AM UTC window, will run reconciliation")
        return False
    
    async def _get_last_reconciliation_timestamp(self) -> Optional[datetime]:
        """
        Get the timestamp of the last reconciliation run.
        
        Returns:
            datetime: Last reconciliation time, or None if never run
        """
        timestamp_file = Path("data/last_reconciliation.timestamp")
        
        if not timestamp_file.exists():
            return None
        
        try:
            timestamp_str = timestamp_file.read_text().strip()
            return datetime.fromisoformat(timestamp_str)
        except Exception as e:
            print(f"[MMR Reconciliation] Error reading timestamp file: {e}")
            return None
    
    async def _save_reconciliation_timestamp(self) -> None:
        """Save the current timestamp as the last reconciliation time."""
        timestamp_file = Path("data/last_reconciliation.timestamp")
        timestamp_file.parent.mkdir(parents=True, exist_ok=True)
        
        now_utc = datetime.now(timezone.utc)
        timestamp_file.write_text(now_utc.isoformat())
        
        # Calculate next run time (tomorrow at midnight UTC)
        next_run = (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        print(f"[MMR Reconciliation] Last run: {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"[MMR Reconciliation] Next scheduled: {next_run.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    async def _reconciliation_worker(self) -> None:
        """
        Background task that runs reconciliation daily at midnight UTC.
        """
        print("[MMR Reconciliation] Background worker started")
        
        while not self._shutdown_event.is_set():
            try:
                # Calculate seconds until next midnight UTC
                now_utc = datetime.now(timezone.utc)
                next_midnight = (now_utc + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                seconds_until_midnight = (next_midnight - now_utc).total_seconds()
                
                print(f"[MMR Reconciliation] Next run scheduled for {next_midnight.strftime('%Y-%m-%d %H:%M:%S')} UTC "
                      f"(in {seconds_until_midnight/3600:.1f} hours)")
                
                # Wait until midnight or shutdown
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=seconds_until_midnight
                    )
                    # Shutdown event was set
                    break
                except asyncio.TimeoutError:
                    # Timeout reached - time to run reconciliation
                    pass
                
                # Run reconciliation
                await self.reconcile_mmr_stats_from_matches()
                await self._save_reconciliation_timestamp()
                
            except Exception as e:
                print(f"[MMR Reconciliation] Error in worker: {e}")
                import traceback
                traceback.print_exc()
                # Wait 1 hour before retrying on error
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=3600)
                    break
                except asyncio.TimeoutError:
                    pass
        
        print("[MMR Reconciliation] Background worker stopped")
    
    # ========== Write-Ahead Log (WAL) Methods ==========
    
    async def _initialize_wal(self) -> None:
        """
        Initialize the Write-Ahead Log (WAL) and replay any pending writes.
        
        This opens a single, persistent connection to the WAL SQLite database.
        It then replays any jobs left over from a previous crash and clears the WAL table.
        """
        # Ensure WAL directory exists
        self._wal_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Open a persistent connection to the WAL database for the bot's lifecycle
        self._wal_db = await aiosqlite.connect(str(self._wal_path))
        
        # Ensure the write_jobs table exists
        await self._wal_db.execute("""
            CREATE TABLE IF NOT EXISTS write_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                job_data TEXT NOT NULL,
                timestamp REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._wal_db.commit()
        
        # Replay any jobs from a previous session and clear the WAL
        await self._replay_wal()
        
        print(f"[DataAccessService] WAL initialized: {self._wal_path}")
    
    async def _replay_wal(self) -> None:
        """
        Replay pending writes from the WAL and clear it.
        
        This uses the existing DB connection to read pending jobs, re-queue them,
        and then clears the WAL table. This avoids file-locking issues on startup.
        """
        if self._wal_db is None:
            return

        print(f"[DataAccessService] Checking for pending writes from previous session...")
        try:
            cursor = await self._wal_db.execute(
                "SELECT id, job_type, job_data, timestamp FROM write_jobs ORDER BY id ASC"
            )
            rows = await cursor.fetchall()
            
            if rows:
                print(f"[DataAccessService] Found {len(rows)} pending writes from previous session")
                
                # Re-queue all pending writes
                for wal_id, job_type_str, job_data_json, timestamp in rows:
                    job_type = WriteJobType(job_type_str)
                    job_data = json.loads(job_data_json)
                    
                    job = WriteJob(
                        job_type=job_type,
                        data=job_data,
                        timestamp=timestamp
                    )
                    
                    await self._write_queue.put(job)
                
                # Notify the worker that jobs are available
                self._write_event.set()
                print(f"[DataAccessService] Successfully re-queued {len(rows)} writes")

                # Now that they are safely re-queued, clear the WAL table.
                await self._wal_db.execute("DELETE FROM write_jobs")
                await self._wal_db.commit()
                print("[DataAccessService] Cleared WAL table after re-queuing.")

            else:
                print(f"[DataAccessService] No pending writes found in WAL")
            
        except Exception as e:
            print(f"[DataAccessService] ERROR replaying WAL: {e}")
            import traceback
            traceback.print_exc()

    async def _wal_write_job(self, job: WriteJob) -> None:
        """
        Write a job to the WAL for durability.
        
        This ensures that if the bot crashes, the write job can be recovered
        and processed during the next startup.
        
        Args:
            job: The write job to persist to WAL
        """
        if self._wal_db is None:
            print("[DataAccessService] WARNING: WAL not initialized, skipping write")
            return
        
        try:
            # Serialize job data to JSON
            job_data_json = json.dumps(job.data)
            
            # Insert into WAL
            await self._wal_db.execute(
                "INSERT INTO write_jobs (job_type, job_data, timestamp) VALUES (?, ?, ?)",
                (job.job_type.value, job_data_json, job.timestamp)
            )
            await self._wal_db.commit()
            
        except Exception as e:
            print(f"[DataAccessService] ERROR writing to WAL: {e}")
            import traceback
            traceback.print_exc()
    
    async def _wal_remove_job(self, job_id: int) -> None:
        """
        Remove a completed job from the WAL.
        
        Args:
            job_id: The ID of the job to remove
        """
        if self._wal_db is None:
            return
        
        try:
            await self._wal_db.execute("DELETE FROM write_jobs WHERE id = ?", (job_id,))
            await self._wal_db.commit()
        except Exception as e:
            print(f"[DataAccessService] ERROR removing job from WAL: {e}")
    
    async def _wal_clear_all(self) -> None:
        """
        Clear all jobs from the WAL.
        
        This is called during graceful shutdown after all writes have been flushed.
        """
        if self._wal_db is None:
            return
        
        try:
            await self._wal_db.execute("DELETE FROM write_jobs")
            await self._wal_db.commit()
            print("[DataAccessService] Cleared all WAL entries")
        except Exception as e:
            print(f"[DataAccessService] ERROR clearing WAL: {e}")
    
    # ========== Write Queue Helper ==========
    
    async def _queue_write(self, job: WriteJob) -> None:
        """
        Queue a write job and notify the worker.
        
        This is a helper method to ensure consistent queuing behavior
        with event notification.
        
        Args:
            job: The write job to queue
        """
        await self._write_queue.put(job)
        self._total_writes_queued += 1
        # Notify the write worker that a job is available
        self._write_event.set()
    
    # ========== Write Queue Worker ==========
    
    async def _db_writer_worker(self) -> None:
        """
        Background worker that processes the write queue and persists to database.
        
        Uses event-driven notification instead of polling for better efficiency.
        All writes are first persisted to WAL for crash resistance, then processed
        and removed from WAL upon successful completion.
        
        This runs continuously until shutdown, ensuring all in-memory changes
        are eventually written to the persistent database.
        """
        print("[DataAccessService] Database write worker started (async, event-driven)")
        
        while not self._shutdown_event.is_set():
            try:
                # Wait for notification that a write is available OR shutdown
                wait_task = asyncio.create_task(self._write_event.wait())
                shutdown_task = asyncio.create_task(self._shutdown_event.wait())
                
                done, pending = await asyncio.wait(
                    [wait_task, shutdown_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                
                # If shutdown was signaled, break
                if self._shutdown_event.is_set():
                    break
                
                # Clear the event for next notification
                self._write_event.clear()
                
                # Process all available jobs in the queue
                while not self._write_queue.empty():
                    try:
                        job = self._write_queue.get_nowait()
                        
                        # Track queue size
                        current_size = self._write_queue.qsize()
                        if current_size > self._write_queue_size_peak:
                            self._write_queue_size_peak = current_size
                        
                        # Log if queue is backing up
                        if current_size > 5:
                            print(f"[DataAccessService] WARNING: Write queue backed up: {current_size} jobs pending")
                        
                        # Write to WAL first (durability)
                        await self._wal_write_job(job)
                        
                        # Process the job
                        await self._process_write_job(job)
                        
                        self._total_writes_completed += 1
                        
                        # Remove from WAL after successful processing
                        # Note: We don't have the WAL ID here, so we'll clear periodically
                        # For now, we'll clear WAL on graceful shutdown
                        
                    except asyncio.QueueEmpty:
                        break
                    except Exception as e:
                        print(f"[DataAccessService] ERROR processing write job: {e}")
                        import traceback
                        traceback.print_exc()
                
            except Exception as e:
                print(f"[DataAccessService] ERROR in write worker: {e}")
                import traceback
                traceback.print_exc()
        
        print("[DataAccessService] Database write worker stopped")
    
    async def _process_write_job(self, job: WriteJob) -> None:
        """
        Process a single write job and persist to database.
        
        Args:
            job: The write job to process
        """
        loop = asyncio.get_running_loop()
        
        try:
            # Execute the database write in a thread pool to avoid blocking
            if job.job_type == WriteJobType.UPDATE_PLAYER:
                # Extract fields for update
                discord_uid = job.data['discord_uid']
                
                # Use partial to bind keyword arguments for run_in_executor
                from functools import partial
                update_func = partial(
                    self._db_writer.update_player,
                    discord_uid,
                    discord_username=job.data.get('discord_username'),
                    player_name=job.data.get('player_name'),
                    battletag=job.data.get('battletag'),
                    alt_player_name_1=job.data.get('alt_player_name_1'),
                    alt_player_name_2=job.data.get('alt_player_name_2'),
                    country=job.data.get('country'),
                    region=job.data.get('region'),
                    accepted_tos=job.data.get('accepted_tos'),
                    completed_setup=job.data.get('completed_setup')
                )
                
                # Special handling for remaining_aborts
                if 'remaining_aborts' in job.data and 'player_name' not in job.data:
                    update_func = partial(
                        self._db_writer.update_player_remaining_aborts,
                        discord_uid,
                        job.data['remaining_aborts']
                    )
                
                await loop.run_in_executor(None, update_func)
            
            elif job.job_type == WriteJobType.CREATE_PLAYER:
                await loop.run_in_executor(
                    None,
                    self._db_writer.create_player,
                    job.data['discord_uid'],
                    job.data['discord_username'],
                    job.data.get('player_name'),
                    job.data.get('battletag'),
                    job.data.get('country'),
                    job.data.get('region'),
                    None  # activation_code
                )
            
            elif job.job_type == WriteJobType.UPDATE_MMR:
                # Check if this is a player_name-only update (from cleanup)
                if 'player_name' in job.data and 'new_mmr' not in job.data:
                    # Player name correction - update only the player_name field
                    from src.backend.db.db_reader_writer import get_timestamp
                    await loop.run_in_executor(
                        None,
                        self._db_writer.adapter.execute_write,
                        """
                        UPDATE mmrs_1v1
                        SET player_name = :player_name, last_played = :last_played
                        WHERE discord_uid = :discord_uid AND race = :race
                        """,
                        {
                            'discord_uid': job.data['discord_uid'],
                            'race': job.data['race'],
                            'player_name': job.data['player_name'],
                            'last_played': get_timestamp()
                        }
                    )
                # Check if this is a full stats update or MMR-only update
                elif 'games_played' in job.data:
                    # Full stats update (from match completion) - use create_or_update_mmr_1v1
                    player_info = self.get_player_info(job.data['discord_uid'])
                    if not player_info or not player_info.get('player_name'):
                        # Fallback to database if in-memory lookup fails
                        db_result = await loop.run_in_executor(
                            None,
                            self._db_reader.adapter.execute_query,
                            "SELECT player_name FROM players WHERE discord_uid = :discord_uid",
                            {'discord_uid': job.data['discord_uid']}
                        )
                        if db_result and len(db_result) > 0:
                            player_name = db_result[0]['player_name']
                        else:
                            raise ValueError(f"Player {job.data['discord_uid']} not found in database or in-memory cache")
                    else:
                        player_name = player_info.get('player_name')
                    
                    await loop.run_in_executor(
                        None,
                        self._db_writer.create_or_update_mmr_1v1,
                        job.data['discord_uid'],
                        player_name,
                        job.data['race'],
                        int(job.data['new_mmr']),
                        job.data['games_played'],
                        job.data['games_won'],
                        job.data['games_lost'],
                        job.data['games_drawn']
                    )
                else:
                    # MMR-only update (from admin) - only update MMR, not game stats
                    from src.backend.db.db_reader_writer import get_timestamp
                    await loop.run_in_executor(
                        None,
                        self._db_writer.adapter.execute_write,
                        """
                        UPDATE mmrs_1v1
                        SET mmr = :mmr, last_played = :last_played
                        WHERE discord_uid = :discord_uid AND race = :race
                        """,
                        {
                            'discord_uid': job.data['discord_uid'],
                            'race': job.data['race'],
                            'mmr': int(job.data['new_mmr']),
                            'last_played': get_timestamp()
                        }
                    )
            
            elif job.job_type == WriteJobType.CREATE_MMR:
                # Use create_or_update_mmr_1v1 for upserts
                await loop.run_in_executor(
                    None,
                    self._db_writer.create_or_update_mmr_1v1,
                    job.data['discord_uid'],
                    job.data['player_name'],
                    job.data['race'],
                    int(job.data['mmr']),
                    job.data.get('games_played', 0),
                    job.data.get('games_won', 0),
                    job.data.get('games_lost', 0),
                    job.data.get('games_drawn', 0)
                )
            
            elif job.job_type == WriteJobType.LOG_PLAYER_ACTION:
                await loop.run_in_executor(
                    None,
                    self._db_writer.log_player_action,
                    job.data['discord_uid'],
                    job.data['player_name'],
                    job.data['setting_name'],
                    job.data.get('old_value'),
                    job.data.get('new_value'),
                    job.data['changed_by']
                )
            
            elif job.job_type == WriteJobType.UPDATE_PREFERENCES:
                await loop.run_in_executor(
                    None,
                    self._db_writer.update_preferences_1v1,
                    job.data['discord_uid'],
                    job.data.get('last_chosen_races'),
                    job.data.get('last_chosen_vetoes')
                )
            
            elif job.job_type == WriteJobType.UPDATE_MATCH:
                # Handle general match updates (match_result, player reports, replay updates, etc.)
                match_id = job.data['match_id']
                update_fields = {k: v for k, v in job.data.items() if k != 'match_id'}
                
                # Handle specific field updates
                for field, value in update_fields.items():
                    if field == 'match_result':
                        await loop.run_in_executor(
                            None,
                            self._db_writer.update_match_result,
                            match_id,
                            value
                        )
                    elif field == 'player_1_report':
                        # Get player_1_discord_uid from the match data
                        from src.backend.db.db_reader_writer import DatabaseReader
                        db_reader = DatabaseReader()
                        match_data = db_reader.get_match_by_id(match_id)
                        if match_data:
                            player_1_uid = match_data.get('player_1_discord_uid')
                            if player_1_uid:
                                await loop.run_in_executor(
                                    None,
                                    self._db_writer.update_player_report_1v1,
                                    match_id,
                                    player_1_uid,
                                    value
                                )
                    elif field == 'player_2_report':
                        # Get player_2_discord_uid from the match data
                        from src.backend.db.db_reader_writer import DatabaseReader
                        db_reader = DatabaseReader()
                        match_data = db_reader.get_match_by_id(match_id)
                        if match_data:
                            player_2_uid = match_data.get('player_2_discord_uid')
                            if player_2_uid:
                                await loop.run_in_executor(
                                    None,
                                    self._db_writer.update_player_report_1v1,
                                    match_id,
                                    player_2_uid,
                                    value
                                )
                    elif field in ['player_discord_uid', 'replay_path', 'replay_time']:
                        # Handle replay updates - these fields come together
                        if 'player_discord_uid' in update_fields and 'replay_path' in update_fields and 'replay_time' in update_fields:
                            await loop.run_in_executor(
                                None,
                                self._db_writer.update_match_replay_1v1,
                                match_id,
                                update_fields['player_discord_uid'],
                                update_fields['replay_path'],
                                update_fields['replay_time']
                            )
                            break  # Only process this once per job
            
            elif job.job_type == WriteJobType.UPDATE_MATCH_MMR_CHANGE:
                print(f"[DataAccessService] Processing UPDATE_MATCH_MMR_CHANGE: match_id={job.data['match_id']}, mmr_change={job.data['mmr_change']}")
                result = await loop.run_in_executor(
                    None,
                    self._db_writer.update_match_mmr_change,
                    job.data['match_id'],
                    job.data['mmr_change']
                )
                print(f"[DataAccessService] UPDATE_MATCH_MMR_CHANGE result: {result}")
            
            elif job.job_type == WriteJobType.INSERT_REPLAY:
                print(f"[DataAccessService] Processing INSERT_REPLAY: replay_hash={job.data.get('replay_hash', 'unknown')}")
                result = await loop.run_in_executor(
                    None,
                    self._db_writer.insert_replay,
                    job.data
                )
                print(f"[DataAccessService] INSERT_REPLAY result: {result}")
            
            elif job.job_type == WriteJobType.INSERT_COMMAND_CALL:
                await loop.run_in_executor(
                    None,
                    self._db_writer.insert_command_call,
                    job.data['discord_uid'],
                    job.data['player_name'],
                    job.data['command']
                )
            
            elif job.job_type == WriteJobType.LOG_ADMIN_ACTION:
                await loop.run_in_executor(
                    None,
                    self._db_writer.log_admin_action,
                    job.data['admin_discord_uid'],
                    job.data['admin_username'],
                    job.data['action_type'],
                    job.data['target_player_uid'],
                    job.data['target_match_id'],
                    job.data['action_details'],
                    job.data['reason']
                )
            
            elif job.job_type == WriteJobType.LOG_PLAYER_ACTION:
                await loop.run_in_executor(
                    None,
                    self._db_writer.log_player_action,
                    job.data['discord_uid'],
                    job.data['player_name'],
                    job.data['setting_name'],
                    job.data.get('old_value'),
                    job.data.get('new_value'),
                    job.data.get('changed_by', 'player')
                )
            
            elif job.job_type == WriteJobType.UPDATE_MATCH_REPORT:
                # Use the database writer for match report updates
                await loop.run_in_executor(
                    None,
                    self._db_writer.update_player_report_1v1,
                    job.data['match_id'],
                    job.data['player_discord_uid'],
                    job.data['report_value']
                )
            
            elif job.job_type == WriteJobType.ABORT_MATCH:
                # Use the existing abort_match_1v1 method
                await loop.run_in_executor(
                    None,
                    self._db_writer.abort_match_1v1,
                    job.data['match_id'],
                    job.data['player_discord_uid'],
                    300  # ABORT_TIMER_SECONDS
                )
            
            elif job.job_type == WriteJobType.SYSTEM_ABORT_UNCONFIRMED:
                # Use the new update_match_reports_and_result method
                await loop.run_in_executor(
                    None,
                    self._db_writer.update_match_reports_and_result,
                    job.data['match_id'],
                    job.data['player_1_report'],
                    job.data['player_2_report'],
                    -1  # match_result: -1 for aborted
                )
            
            elif job.job_type == WriteJobType.ADMIN_RESOLVE_MATCH:
                # Admin resolution - sets match_result, reports, and updated_at atomically
                print(f"[DataAccessService] Processing ADMIN_RESOLVE_MATCH: match_id={job.data['match_id']}, result={job.data['match_result']}")
                await loop.run_in_executor(
                    None,
                    self._db_writer.admin_resolve_match,
                    job.data['match_id'],
                    job.data['match_result'],
                    job.data['p1_report'],
                    job.data['p2_report']
                )
            
            elif job.job_type == WriteJobType.UPDATE_PLAYER_STATE:
                await loop.run_in_executor(
                    None,
                    self._db_writer.update_player_state,
                    job.data['discord_uid'],
                    job.data['state']
                )
            
            elif job.job_type == WriteJobType.UPDATE_SHIELD_BATTERY_BUG:
                await loop.run_in_executor(
                    None,
                    self._db_writer.update_shield_battery_bug,
                    job.data['discord_uid'],
                    job.data['value']
                )
            
            elif job.job_type == WriteJobType.UPDATE_IS_BANNED:
                await loop.run_in_executor(
                    None,
                    self._db_writer.update_is_banned,
                    job.data['discord_uid'],
                    job.data['value']
                )
            
            elif job.job_type == WriteJobType.UPDATE_READ_QUICK_START_GUIDE:
                await loop.run_in_executor(
                    None,
                    self._db_writer.set_read_quick_start_guide,
                    job.data['discord_uid'],
                    job.data['value']
                )
            
            # Add other job types as we implement them
            else:
                print(f"[DataAccessService] WARNING: Unknown job type: {job.job_type}")
        
        except Exception as e:
            print(f"[DataAccessService] ERROR: Failed to process write job {job.job_type}: {e}")
            
            # Implement retry mechanism for failed writes
            if not hasattr(job, 'retry_count'):
                job.retry_count = 0
            
            job.retry_count += 1
            max_retries = 3
            
            if job.retry_count <= max_retries:
                print(f"[DataAccessService] Retrying write job {job.job_type} (attempt {job.retry_count}/{max_retries})")
                # Re-queue the job for retry
                await self._write_queue.put(job)
            else:
                # Move to dead-letter queue after max retries
                await self._log_failed_write_job(job, str(e))
    
    async def _log_failed_write_job(self, job: WriteJob, error_message: str) -> None:
        """
        Log a failed write job to a dead-letter file for manual review.
        
        Args:
            job: The failed write job
            error_message: The error that caused the failure
        """
        import json
        import os
        from datetime import datetime
        
        # Create failed_writes directory if it doesn't exist
        failed_writes_dir = "logs/failed_writes"
        os.makedirs(failed_writes_dir, exist_ok=True)
        
        # Create log entry
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "job_type": job.job_type.value,
            "job_data": job.data,
            "error_message": error_message,
            "retry_count": getattr(job, 'retry_count', 0)
        }
        
        # Write to failed_writes.log
        log_file = os.path.join(failed_writes_dir, "failed_writes.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        print(f"[DataAccessService] CRITICAL: Write job {job.job_type} failed after {getattr(job, 'retry_count', 0)} retries. Logged to {log_file}")
    
    async def shutdown(self) -> None:
        """
        Graceful shutdown - flush write queue and stop worker.
        
        This should be called during bot shutdown. This method ensures all
        pending writes are processed and the background worker is cleanly
        stopped before any resources are closed.
        """
        print("[DataAccessService] Shutting down...")
        
        # Signal shutdown to the worker task
        self._shutdown_event.set()
        print("[DataAccessService] Shutdown signal sent to writer task")
        
        # Wait for write queue to drain (with timeout)
        queue_size = self._write_queue.qsize()
        if queue_size > 0:
            print(f"[DataAccessService] Waiting for {queue_size} pending writes to complete...")
            timeout = 30  # 30 second timeout
            start = time.time()
            while self._write_queue.qsize() > 0 and (time.time() - start) < timeout:
                await asyncio.sleep(0.1)
        
        # Wait for writer task to finish gracefully
        if self._writer_task and not self._writer_task.done():
            print("[DataAccessService] Waiting for writer task to finish...")
            try:
                # Give the task a reasonable time to exit cleanly after receiving shutdown signal
                await asyncio.wait_for(self._writer_task, timeout=10.0)
            except asyncio.TimeoutError:
                print("[DataAccessService] WARN: Writer task did not exit cleanly within timeout, cancelling...")
                self._writer_task.cancel()
                try:
                    await asyncio.wait_for(self._writer_task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    print("[DataAccessService] Writer task forcefully stopped")
            except asyncio.CancelledError:
                print("[DataAccessService] Writer task was cancelled")
            except Exception as e:
                print(f"[DataAccessService] ERROR waiting for writer task: {e}")
        
        print("[DataAccessService] Writer task confirmed stopped")
        
        # Wait for reconciliation task to finish gracefully
        if self._reconciliation_task and not self._reconciliation_task.done():
            print("[DataAccessService] Waiting for reconciliation task to finish...")
            try:
                await asyncio.wait_for(self._reconciliation_task, timeout=10.0)
            except asyncio.TimeoutError:
                print("[DataAccessService] WARN: Reconciliation task did not exit cleanly, cancelling...")
                self._reconciliation_task.cancel()
                try:
                    await asyncio.wait_for(self._reconciliation_task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    print("[DataAccessService] Reconciliation task forcefully stopped")
            except asyncio.CancelledError:
                print("[DataAccessService] Reconciliation task was cancelled")
            except Exception as e:
                print(f"[DataAccessService] ERROR waiting for reconciliation task: {e}")
        
        print("[DataAccessService] Reconciliation task confirmed stopped")
        
        # Now that the writer task is fully stopped, safely close resources
        if self._wal_db:
            await self._wal_clear_all()
            await self._wal_db.close()
            print("[DataAccessService] WAL database closed")
            print(f"[DataAccessService] WAL file persisted at: {self._wal_path} (will be replayed on next startup if needed)")
        
        # Print stats
        print(f"[DataAccessService] Shutdown complete")
        print(f"[DataAccessService]   Total writes queued: {self._total_writes_queued}")
        print(f"[DataAccessService]   Total writes completed: {self._total_writes_completed}")
        print(f"[DataAccessService]   Peak queue size: {self._write_queue_size_peak}")
    
    # ========== Read Methods (Players Table) ==========
    
    def get_player_info(self, discord_uid: int) -> Optional[Dict[str, Any]]:
        """
        Get player information by Discord UID.
        
        This reads from the in-memory DataFrame for sub-millisecond performance.
        
        Args:
            discord_uid: Discord user ID
            
        Returns:
            Player data dictionary or None if not found
        """
        if self._players_df is None:
            print("[DataAccessService] WARNING: Players DataFrame not initialized")
            return None
        
        result = self._players_df.filter(pl.col("discord_uid") == discord_uid)
        
        if len(result) == 0:
            return None
        
        return result.to_dicts()[0]
    
    def get_remaining_aborts(self, discord_uid: int) -> int:
        """
        Get the number of remaining aborts for a player.
        
        This reads from the in-memory DataFrame for sub-millisecond performance.
        
        Args:
            discord_uid: Discord user ID
            
        Returns:
            Number of remaining aborts (defaults to 3 if player not found)
        """
        player = self.get_player_info(discord_uid)
        if player:
            return player.get('remaining_aborts', 3)
        return 3
    
    def player_exists(self, discord_uid: int) -> bool:
        """
        Check if a player exists in memory.
        
        Args:
            discord_uid: Discord user ID
            
        Returns:
            True if player exists, False otherwise
        """
        if self._players_df is None:
            return False
        
        result = self._players_df.filter(pl.col("discord_uid") == discord_uid)
        return len(result) > 0
    
    def get_player_state(self, discord_uid: int) -> str:
        """
        Get player's current state.
        
        Args:
            discord_uid: Player's Discord ID
        
        Returns:
            Player state string: "idle", "queueing", or "in_match:{match_id}"
            Returns "idle" if player not found or state is None
        """
        if self._players_df is None:
            return "idle"
        
        result = self._players_df.filter(pl.col("discord_uid") == discord_uid)
        
        if len(result) == 0:
            return "idle"
        
        state = result['player_state'][0]
        return state if state is not None else "idle"
    
    async def set_player_state(self, discord_uid: int, state: str) -> bool:
        """
        Set player's state atomically.
        
        Args:
            discord_uid: Player's Discord ID
            state: New state ("idle", "queueing", "in_match:{match_id}")
        
        Returns:
            True if successful, False if player not found
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if self._players_df is None:
            return False
        
        mask = pl.col("discord_uid") == discord_uid
        if len(self._players_df.filter(mask)) == 0:
            return False
        
        # Log every state transition for debugging
        logger.info(f"[STATE] {discord_uid} -> {state}")
        
        self._players_df = self._players_df.with_columns(
            pl.when(mask).then(pl.lit(state)).otherwise(pl.col("player_state")).alias("player_state")
        )
        
        job = WriteJob(
            job_type=WriteJobType.UPDATE_PLAYER_STATE,
            data={'discord_uid': discord_uid, 'state': state},
            timestamp=time.time()
        )
        await self._queue_write(job)
        return True
    
    def get_shield_battery_bug(self, discord_uid: int) -> bool:
        """Get whether player has acknowledged the shield battery bug."""
        if self._players_df is None or len(self._players_df) == 0:
            return False
        
        # Handle missing column (defensive)
        if "shield_battery_bug" not in self._players_df.columns:
            return False
        
        player_row = self._players_df.filter(pl.col("discord_uid") == discord_uid)
        if len(player_row) == 0:
            return False
        
        return player_row["shield_battery_bug"][0]

    async def set_shield_battery_bug(
        self, 
        discord_uid: int, 
        value: bool,
        changed_by: str = "player"
    ) -> bool:
        """
        Set whether player has acknowledged the shield battery bug.
        
        Args:
            discord_uid: Player's Discord ID
            value: New acknowledgment status
            changed_by: Who made the change (e.g., "admin:123456", "system", "player")
        """
        if self._players_df is None:
            return False
        
        # Get old value for logging
        old_value = self.get_shield_battery_bug(discord_uid)
        
        # Update in-memory DataFrame
        mask = pl.col("discord_uid") == discord_uid
        self._players_df = self._players_df.with_columns(
            pl.when(mask).then(pl.lit(value)).otherwise(pl.col("shield_battery_bug")).alias("shield_battery_bug")
        )
        
        # Get player name for logging
        player_info = self.get_player_info(discord_uid)
        player_name = player_info.get("player_name", "Unknown") if player_info else "Unknown"
        
        # Queue async database write
        job = WriteJob(
            job_type=WriteJobType.UPDATE_SHIELD_BATTERY_BUG,
            data={
                "discord_uid": discord_uid,
                "value": value
            },
            timestamp=time.time()
        )
        await self._queue_write(job)
        
        # Log to player_action_logs
        action_log_job = WriteJob(
            job_type=WriteJobType.LOG_PLAYER_ACTION,
            data={
                "discord_uid": discord_uid,
                "player_name": player_name,
                "setting_name": "shield_battery_bug",
                "old_value": str(old_value),
                "new_value": str(value),
                "changed_by": changed_by
            },
            timestamp=time.time()
        )
        await self._queue_write(action_log_job)
        
        return True
    
    def get_is_banned(self, discord_uid: int) -> bool:
        """Get whether player is banned."""
        if self._players_df is None or len(self._players_df) == 0:
            return False
        
        # Handle missing column (defensive)
        if "is_banned" not in self._players_df.columns:
            return False
        
        player_row = self._players_df.filter(pl.col("discord_uid") == discord_uid)
        if len(player_row) == 0:
            return False
        
        return player_row["is_banned"][0]

    async def set_is_banned(
        self, 
        discord_uid: int, 
        value: bool,
        changed_by: str = "system",
        reason: str = ""
    ) -> bool:
        """
        Set whether player is banned.
        
        Args:
            discord_uid: Player's Discord ID
            value: New ban status
            changed_by: Who made the change (e.g., "admin:123456", "system", "player")
            reason: Reason for the change
        """
        if self._players_df is None:
            return False
        
        # Get old value for logging
        old_value = self.get_is_banned(discord_uid)
        
        # Update in-memory DataFrame
        mask = pl.col("discord_uid") == discord_uid
        self._players_df = self._players_df.with_columns(
            pl.when(mask).then(pl.lit(value)).otherwise(pl.col("is_banned")).alias("is_banned")
        )
        
        # Get player name for logging
        player_info = self.get_player_info(discord_uid)
        player_name = player_info.get("player_name", "Unknown") if player_info else "Unknown"
        
        # Queue async database write
        job = WriteJob(
            job_type=WriteJobType.UPDATE_IS_BANNED,
            data={
                "discord_uid": discord_uid,
                "value": value
            },
            timestamp=time.time()
        )
        await self._queue_write(job)
        
        # Log to player_action_logs
        action_log_job = WriteJob(
            job_type=WriteJobType.LOG_PLAYER_ACTION,
            data={
                "discord_uid": discord_uid,
                "player_name": player_name,
                "setting_name": "is_banned",
                "old_value": str(old_value),
                "new_value": str(value),
                "changed_by": changed_by,
                "reason": reason
            },
            timestamp=time.time()
        )
        await self._queue_write(action_log_job)
        
        return True
    
    def get_read_quick_start_guide(self, discord_uid: int) -> bool:
        """
        Get whether player has confirmed reading the quick start guide.
        
        Args:
            discord_uid: Player's Discord ID
            
        Returns:
            True if player confirmed, False otherwise
        """
        if self._players_df is None or len(self._players_df) == 0:
            return False
        
        if "read_quick_start_guide" not in self._players_df.columns:
            return False
        
        player_row = self._players_df.filter(pl.col("discord_uid") == discord_uid)
        if len(player_row) == 0:
            return False
        
        return bool(player_row["read_quick_start_guide"][0])
    
    async def set_read_quick_start_guide(
        self, 
        discord_uid: int, 
        value: bool
    ) -> bool:
        """
        Set whether player has confirmed reading the quick start guide.
        
        Args:
            discord_uid: Player's Discord ID
            value: True if confirmed, False otherwise
            
        Returns:
            True if successful, False otherwise
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if self._players_df is None:
            return False
        
        mask = pl.col("discord_uid") == discord_uid
        if len(self._players_df.filter(mask)) == 0:
            return False
        
        self._players_df = self._players_df.with_columns(
            pl.when(mask).then(pl.lit(value)).otherwise(pl.col("read_quick_start_guide")).alias("read_quick_start_guide")
        )
        
        if value:
            logger.info(f"Player {discord_uid} confirmed Quick Start Guide")
        
        job = WriteJob(
            job_type=WriteJobType.UPDATE_READ_QUICK_START_GUIDE,
            data={
                "discord_uid": discord_uid,
                "value": value
            },
            timestamp=time.time()
        )
        await self._queue_write(job)
        
        return True
    
    async def reset_all_player_states_to_idle(self) -> int:
        """
        Reset all non-idle player states to idle. Used on startup for crash recovery.
        
        This method finds all players with non-idle states and resets them to "idle",
        both in memory and in the database. This is necessary when the bot restarts
        after a crash, as players who were in "queueing" or "in_match:X" states
        should be reset to allow them to queue again.
        
        Returns:
            Number of players whose state was reset
        """
        if self._players_df is None or len(self._players_df) == 0:
            return 0
        
        # Find all players with non-idle states
        non_idle_players = self._players_df.filter(
            (pl.col("player_state") != "idle") & 
            (pl.col("player_state").is_not_null())
        )
        
        reset_count = len(non_idle_players)
        
        if reset_count == 0:
            return 0
        
        # Reset all non-idle states to idle in memory
        self._players_df = self._players_df.with_columns(
            pl.lit("idle").alias("player_state")
        )
        
        # Queue database writes for each affected player
        for discord_uid in non_idle_players['discord_uid'].to_list():
            job = WriteJob(
                job_type=WriteJobType.UPDATE_PLAYER_STATE,
                data={'discord_uid': discord_uid, 'state': 'idle'},
                timestamp=time.time()
            )
            await self._queue_write(job)
        
        return reset_count
    
    # ========== Read Methods (MMRs Table) ==========
    
    def get_player_mmr(self, discord_uid: int, race: str) -> Optional[float]:
        """
        Get a player's MMR for a specific race.
        
        Args:
            discord_uid: Discord user ID
            race: Race code (e.g., 'bw_terran', 'sc2_zerg')
            
        Returns:
            MMR value or None if not found
        """
        if self._mmrs_1v1_df is None:
            print("[DataAccessService] WARNING: MMRs DataFrame not initialized")
            return None
        
        result = self._mmrs_1v1_df.filter(
            (pl.col("discord_uid") == discord_uid) &
            (pl.col("race") == race)
        )
        
        if len(result) == 0:
            return None
        
        mmr = result["mmr"][0]
        return float(mmr) if mmr is not None else None
    
    def get_all_player_mmrs(self, discord_uid: int) -> Dict[str, Dict[str, Any]]:
        """
        Get all MMRs for a player across all races.
        
        Args:
            discord_uid: Discord user ID
            
        Returns:
            Dict mapping race code to complete record dict with MMR, games_played, games_won, games_lost, games_drawn, last_played
        """
        if self._mmrs_1v1_df is None:
            print("[DataAccessService] WARNING: MMRs DataFrame not initialized")
            return {}
        
        print(f"[DataAccessService] get_all_player_mmrs called for {discord_uid}")
        print(f"[DataAccessService]   Total rows in DataFrame: {len(self._mmrs_1v1_df)}")
        
        result = self._mmrs_1v1_df.filter(pl.col("discord_uid") == discord_uid)
        print(f"[DataAccessService]   Filter found {len(result)} rows for discord_uid={discord_uid}")
        
        if len(result) == 0:
            return {}
        
        # Build dict of race -> complete record dict
        mmrs = {}
        for row in result.iter_rows(named=True):
            race = row["race"]
            if race:
                mmrs[race] = {
                    "mmr": float(row["mmr"]) if row["mmr"] is not None else 0,
                    "games_played": int(row["games_played"]) if row["games_played"] is not None else 0,
                    "games_won": int(row["games_won"]) if row["games_won"] is not None else 0,
                    "games_lost": int(row["games_lost"]) if row["games_lost"] is not None else 0,
                    "games_drawn": int(row["games_drawn"]) if row["games_drawn"] is not None else 0,
                    "last_played": row.get("last_played"),
                }
                print(f"[DataAccessService]   Found {race}: mmr={mmrs[race]['mmr']}, games={mmrs[race]['games_played']}")
        
        return mmrs
    
    def get_player_time_stratified_stats(self, discord_uid: int) -> Dict[str, Dict[str, Dict]]:
        """
        Get time-stratified win/loss/draw stats for a player across all races.
        
        Args:
            discord_uid: Discord user ID
            
        Returns:
            Dict mapping race code to time period stats:
            {
                'sc2_terran': {
                    '14d': {'wins': 5, 'losses': 2, 'draws': 1, 'total': 8},
                    '30d': {'wins': 12, 'losses': 8, 'draws': 2, 'total': 22},
                    '90d': {'wins': 25, 'losses': 20, 'draws': 3, 'total': 48}
                },
                'sc2_zerg': { ... }
            }
        """
        from datetime import datetime, timedelta, timezone
        
        if self._matches_1v1_df is None or len(self._matches_1v1_df) == 0:
            return {}
        
        # Initialize result structure
        stats = {}
        
        # Get current time
        now = datetime.now(timezone.utc)
        
        # Define time periods (in days)
        periods = {
            '14d': 14,
            '30d': 30,
            '90d': 90
        }
        
        # Get ALL matches for this player (no time filtering - table is chronologically sorted)
        # This avoids datetime parsing issues
        player_matches = self._matches_1v1_df.filter(
            (pl.col("player_1_discord_uid") == discord_uid) | 
            (pl.col("player_2_discord_uid") == discord_uid)
        )
        
        if len(player_matches) == 0:
            return {}
        
        # Process each match and categorize by time period
        for row in player_matches.iter_rows(named=True):
            player_1_uid = row['player_1_discord_uid']
            player_2_uid = row['player_2_discord_uid']
            match_result = row.get('match_result')
            played_at = row.get('played_at')
            
            # Skip matches without valid result
            if match_result is None or match_result < 0:
                continue
            
            # Determine match age (in days)
            match_age_days = None
            if played_at:
                try:
                    if isinstance(played_at, datetime):
                        match_dt = played_at
                    elif isinstance(played_at, (int, float)):
                        match_dt = datetime.fromtimestamp(played_at, tz=timezone.utc)
                    else:
                        match_dt = datetime.fromisoformat(str(played_at).replace('Z', '+00:00').replace('+00', '+00:00'))
                    
                    if match_dt.tzinfo is None:
                        match_dt = match_dt.replace(tzinfo=timezone.utc)
                    
                    match_age_days = (now - match_dt).days
                except Exception:
                    pass
            
            # Determine which player we are and get the race/outcome
            if player_1_uid == discord_uid:
                race = row['player_1_race']
                # match_result: 1 = player 1 won, 2 = player 2 won, 0 = draw
                if match_result == 1:
                    outcome = 'win'
                elif match_result == 2:
                    outcome = 'loss'
                elif match_result == 0:
                    outcome = 'draw'
                else:
                    continue
            else:
                race = row['player_2_race']
                # match_result: 1 = player 1 won, 2 = player 2 won, 0 = draw
                if match_result == 2:
                    outcome = 'win'
                elif match_result == 1:
                    outcome = 'loss'
                elif match_result == 0:
                    outcome = 'draw'
                else:
                    continue
            
            # Initialize race structure if not exists
            if race not in stats:
                stats[race] = {}
            
            # Update stats for each applicable time period
            for period_key, period_days in periods.items():
                # If we couldn't determine age, include in all periods (fail-safe)
                if match_age_days is None or match_age_days <= period_days:
                    if period_key not in stats[race]:
                        stats[race][period_key] = {
                            'wins': 0,
                            'losses': 0,
                            'draws': 0,
                            'total': 0
                        }
                    
                    stats[race][period_key]['total'] += 1
                    if outcome == 'win':
                        stats[race][period_key]['wins'] += 1
                    elif outcome == 'loss':
                        stats[race][period_key]['losses'] += 1
                    elif outcome == 'draw':
                        stats[race][period_key]['draws'] += 1
        
        # Ensure all races have all periods (fill with zeros if missing)
        all_races = list(stats.keys())
        for race in all_races:
            for period_key in ['14d', '30d', '90d']:
                if period_key not in stats[race]:
                    stats[race][period_key] = {
                        'wins': 0,
                        'losses': 0,
                        'draws': 0,
                        'total': 0
                    }
        
        return stats
    
    def get_leaderboard_dataframe(self) -> Optional[pl.DataFrame]:
        """
        Get the leaderboard DataFrame with joined player and MMR data.
        
        This creates a proper leaderboard view by joining players and MMRs data.
        
        Returns:
            Polars DataFrame with complete leaderboard data, or None if not initialized
        """
        if self._mmrs_1v1_df is None or self._players_df is None:
            print("[DataAccessService] WARNING: DataFrames not initialized")
            return None
        
        # Join MMRs with Players data to get complete leaderboard information
        leaderboard_df = self._mmrs_1v1_df.join(
            self._players_df.select([
                "discord_uid", 
                "player_name",
                "country", 
                "alt_player_name_1", 
                "alt_player_name_2"
            ]),
            on="discord_uid",
            how="left"
        )
        
        return leaderboard_df
    
    # ========== Match Operations ==========
    
    def update_match_report(self, match_id: int, player_discord_uid: int, report_value: int) -> bool:
        """
        Update a player's report for a match in memory.
        
        Args:
            match_id: Match ID
            player_discord_uid: Discord UID of the player reporting
            report_value: Report value (0=loss, 1=win, -1=aborted, -3=aborted by this player)
            
        Returns:
            True if successful
        """
        try:
            if self._matches_1v1_df is None:
                print(f"[DataAccessService] Matches DataFrame not initialized")
                return False
            
            # Get match data to verify player is in this match
            match = self.get_match(match_id)
            if not match:
                print(f"[DataAccessService] Match {match_id} not found")
                return False
            
            p1_discord_uid = match.get('player_1_discord_uid')
            p2_discord_uid = match.get('player_2_discord_uid')
            
            # Determine which player is reporting
            if player_discord_uid == p1_discord_uid:
                report_column = "player_1_report"
            elif player_discord_uid == p2_discord_uid:
                report_column = "player_2_report"
            else:
                print(f"[DataAccessService] Player {player_discord_uid} not in match {match_id}")
                return False
            
            # Update the report in memory
            self._matches_1v1_df = self._matches_1v1_df.with_columns([
                pl.when(pl.col("id") == match_id)
                  .then(pl.lit(report_value))
                  .otherwise(pl.col(report_column))
                  .alias(report_column)
            ])
            
            print(f"[DataAccessService] Updated {report_column} to {report_value} for match {match_id}")
            
            # Queue database write
            job = WriteJob(
                job_type=WriteJobType.UPDATE_MATCH_REPORT,
                data={
                    "match_id": match_id,
                    "player_discord_uid": player_discord_uid,
                    "report_value": report_value
                },
                timestamp=time.time()
            )
            
            # Note: We can't await here since this is called from sync context
            # The write will be queued and processed by the background worker
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._queue_write(job))
            else:
                loop.run_until_complete(self._queue_write(job))
            
            return True
            
        except Exception as e:
            print(f"[DataAccessService] Error updating match report: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # ========== Write Methods (Players Table) ==========
    
    async def update_remaining_aborts(
        self, 
        discord_uid: int, 
        new_aborts: int,
        changed_by: str = "system"
    ) -> bool:
        """
        Update a player's remaining aborts count.
        
        Updates in-memory DataFrame instantly, then queues async DB write.
        
        Args:
            discord_uid: Discord user ID
            new_aborts: New abort count
            changed_by: Who made the change (e.g., "admin:123456", "system", "player")
            
        Returns:
            True if successful, False if player not found
        """
        if self._players_df is None:
            print("[DataAccessService] WARNING: Players DataFrame not initialized")
            return False
        
        # Check if player exists
        mask = pl.col("discord_uid") == discord_uid
        player_row = self._players_df.filter(mask)
        if len(player_row) == 0:
            print(f"[DataAccessService] WARNING: Player {discord_uid} not found for abort update")
            return False
        
        # Get old value and player info for logging
        old_aborts = int(player_row["remaining_aborts"][0])
        player_info = self.get_player_info(discord_uid)
        player_name = player_info.get("player_name", "Unknown") if player_info else "Unknown"
        
        # Update in-memory DataFrame
        self._players_df = self._players_df.with_columns(
            pl.when(mask)
            .then(pl.lit(new_aborts))
            .otherwise(pl.col("remaining_aborts"))
            .alias("remaining_aborts")
        )
        
        # Queue database write
        job = WriteJob(
            job_type=WriteJobType.UPDATE_PLAYER,
            data={
                'discord_uid': discord_uid,
                'remaining_aborts': new_aborts
            },
            timestamp=time.time()
        )
        
        await self._queue_write(job)
        
        # Log to player_action_logs
        action_log_job = WriteJob(
            job_type=WriteJobType.LOG_PLAYER_ACTION,
            data={
                "discord_uid": discord_uid,
                "player_name": player_name,
                "setting_name": "remaining_aborts",
                "old_value": str(old_aborts),
                "new_value": str(new_aborts),
                "changed_by": changed_by
            },
            timestamp=time.time()
        )
        await self._queue_write(action_log_job)
        
        return True
    
    async def update_player_info(
        self,
        discord_uid: int,
        discord_username: Optional[str] = None,
        player_name: Optional[str] = None,
        country: Optional[str] = None,
        battletag: Optional[str] = None,
        alt_player_name_1: Optional[str] = None,
        alt_player_name_2: Optional[str] = None,
        region: Optional[str] = None,
        accepted_tos: Optional[bool] = None,
        completed_setup: Optional[bool] = None,
        changed_by: str = "player"
    ) -> bool:
        """
        Update player information.
        
        Updates in-memory DataFrame instantly, then queues async DB write.
        
        Args:
            discord_uid: Discord user ID
            discord_username: Discord username
            player_name: In-game player name
            country: Country code
            battletag: Battle.net tag
            alt_player_name_1: First alternate name
            alt_player_name_2: Second alternate name
            region: Region code
            changed_by: Who made the change (e.g., "admin:123456", "system", "player")
            
        Returns:
            True if successful, False if player not found
        """
        if self._players_df is None:
            print("[DataAccessService] WARNING: Players DataFrame not initialized")
            return False
        
        # Check if player exists
        mask = pl.col("discord_uid") == discord_uid
        player_row = self._players_df.filter(mask)
        if len(player_row) == 0:
            print(f"[DataAccessService] WARNING: Player {discord_uid} not found for update")
            return False
        
        # Get old values for logging
        old_values = {}
        field_mapping = {
            'discord_username': discord_username,
            'player_name': player_name,
            'country': country,
            'battletag': battletag,
            'alt_player_name_1': alt_player_name_1,
            'alt_player_name_2': alt_player_name_2,
            'region': region,
            'accepted_tos': accepted_tos,
            'completed_setup': completed_setup
        }
        
        for field_name, new_value in field_mapping.items():
            if new_value is not None:
                old_values[field_name] = str(player_row[field_name][0]) if player_row[field_name][0] is not None else "None"
        
        # Get player name for logging
        current_player_name = str(player_row["player_name"][0]) if player_row["player_name"][0] is not None else "Unknown"
        
        # Build update expressions for each field
        updates = {}
        write_data = {'discord_uid': discord_uid}
        
        if discord_username is not None:
            updates["discord_username"] = pl.when(mask).then(pl.lit(discord_username)).otherwise(pl.col("discord_username"))
            write_data['discord_username'] = discord_username
        
        if player_name is not None:
            updates["player_name"] = pl.when(mask).then(pl.lit(player_name)).otherwise(pl.col("player_name"))
            write_data['player_name'] = player_name
        
        if country is not None:
            updates["country"] = pl.when(mask).then(pl.lit(country)).otherwise(pl.col("country"))
            write_data['country'] = country
        
        if battletag is not None:
            updates["battletag"] = pl.when(mask).then(pl.lit(battletag)).otherwise(pl.col("battletag"))
            write_data['battletag'] = battletag
        
        if alt_player_name_1 is not None:
            updates["alt_player_name_1"] = pl.when(mask).then(pl.lit(alt_player_name_1 if alt_player_name_1.strip() else None)).otherwise(pl.col("alt_player_name_1"))
            write_data['alt_player_name_1'] = alt_player_name_1
        
        if alt_player_name_2 is not None:
            updates["alt_player_name_2"] = pl.when(mask).then(pl.lit(alt_player_name_2 if alt_player_name_2.strip() else None)).otherwise(pl.col("alt_player_name_2"))
            write_data['alt_player_name_2'] = alt_player_name_2
        
        if region is not None:
            updates["region"] = pl.when(mask).then(pl.lit(region)).otherwise(pl.col("region"))
            write_data['region'] = region
        
        if accepted_tos is not None:
            updates["accepted_tos"] = pl.when(mask).then(pl.lit(accepted_tos)).otherwise(pl.col("accepted_tos"))
            write_data['accepted_tos'] = accepted_tos
            # Update timestamp whenever accepted_tos is changed
            timestamp_str = datetime.now(timezone.utc).isoformat()
            updates["accepted_tos_date"] = pl.when(mask).then(pl.lit(timestamp_str)).otherwise(pl.col("accepted_tos_date"))
            write_data['accepted_tos_date'] = timestamp_str
        
        if completed_setup is not None:
            updates["completed_setup"] = pl.when(mask).then(pl.lit(completed_setup)).otherwise(pl.col("completed_setup"))
            write_data['completed_setup'] = completed_setup
        
        # Apply updates to DataFrame if any
        if updates:
            self._players_df = self._players_df.with_columns(**updates)
            
            # Queue database write
            job = WriteJob(
                job_type=WriteJobType.UPDATE_PLAYER,
                data=write_data,
                timestamp=time.time()
            )
            
            await self._write_queue.put(job)
            self._total_writes_queued += 1
            
            # Log each field change to player_action_logs
            for field_name, new_value in field_mapping.items():
                if new_value is not None:
                    action_log_job = WriteJob(
                        job_type=WriteJobType.LOG_PLAYER_ACTION,
                        data={
                            "discord_uid": discord_uid,
                            "player_name": current_player_name,
                            "setting_name": field_name,
                            "old_value": old_values.get(field_name, "None"),
                            "new_value": str(new_value),
                            "changed_by": changed_by
                        },
                        timestamp=time.time()
                    )
                    await self._queue_write(action_log_job)
        
        return True
    
    async def create_player(
        self,
        discord_uid: int,
        discord_username: str = "Unknown",
        player_name: Optional[str] = None,
        country: Optional[str] = None,
        battletag: Optional[str] = None,
        region: Optional[str] = None
    ) -> bool:
        """
        Create a new player.
        
        Adds to in-memory DataFrame instantly, then queues async DB write.
        
        Args:
            discord_uid: Discord user ID
            discord_username: Discord username
            player_name: In-game player name
            country: Country code
            battletag: Battle.net tag
            region: Region code
            
        Returns:
            True if successful, False if player already exists
        """
        if self._players_df is None:
            print("[DataAccessService] WARNING: Players DataFrame not initialized")
            return False
        
        # Check if player already exists
        if self.player_exists(discord_uid):
            print(f"[DataAccessService] WARNING: Player {discord_uid} already exists")
            return False
        
        # Create new row - matches PostgreSQL schema order exactly
        new_row = pl.DataFrame({
            "discord_uid": [discord_uid],
            "discord_username": [discord_username],
            "player_name": [player_name],
            "battletag": [battletag],
            "alt_player_name_1": [None],
            "alt_player_name_2": [None],
            "country": [country],
            "region": [region],
            "accepted_tos": [False],
            "accepted_tos_date": [None],
            "completed_setup": [False],
            "completed_setup_date": [None],
            "activation_code": [None],
            "created_at": [None],
            "updated_at": [None],
            "remaining_aborts": [3],
            "player_state": ["idle"],
            "shield_battery_bug": [False],
            "is_banned": [False],
        })
        
        # Append to existing DataFrame
        self._players_df = pl.concat([self._players_df, new_row], how="diagonal")
        
        # Queue database write
        job = WriteJob(
            job_type=WriteJobType.CREATE_PLAYER,
            data={
                'discord_uid': discord_uid,
                'discord_username': discord_username,
                'player_name': player_name,
                'country': country,
                'battletag': battletag,
                'region': region
            },
            timestamp=time.time()
        )
        
        await self._queue_write(job)
        
        print(f"[DataAccessService] Created player {discord_uid} ({discord_username})")
        return True
    
    # ========== Write Methods (MMRs Table) ==========
    
    def _update_mmr_dataframe_row(
        self,
        discord_uid: int,
        race: str,
        update_data: Dict[str, Any]
    ) -> bool:
        """
        Helper method to update a specific row in the MMR DataFrame.
        
        Uses conditional expressions with verification to ensure updates are applied correctly.
        Maintains DataFrame row order and integrity.
        
        Args:
            discord_uid: Discord user ID
            race: Race code
            update_data: Dictionary of column names to new values
            
        Returns:
            True if the row was found and updated, False otherwise
        """
        if self._mmrs_1v1_df is None or self._mmrs_1v1_df.is_empty():
            print(f"[DataAccessService] WARNING: Cannot update - MMRs DataFrame is empty")
            return False
        
        # Check if the row exists BEFORE update
        mask = (pl.col("discord_uid") == discord_uid) & (pl.col("race") == race)
        before_filter = self._mmrs_1v1_df.filter(mask)
        
        if before_filter.is_empty():
            print(f"[DataAccessService] WARNING: No MMR record found for discord_uid={discord_uid}, race={race}")
            return False
        
        # Get the old value of a field we're updating (for verification)
        verification_column = list(update_data.keys())[0]
        old_value = before_filter[verification_column][0]
        
        # Build conditional update expressions for each column
        updates = {}
        for column, value in update_data.items():
            if column in self._mmrs_1v1_df.columns:
                # Cast to the correct dtype to match the column
                col_dtype = self._mmrs_1v1_df.schema[column]
                updates[column] = pl.when(mask).then(pl.lit(value).cast(col_dtype)).otherwise(pl.col(column))
        
        # Apply the updates
        print(f"[DataAccessService] Applying updates for {discord_uid}/{race}: {list(update_data.keys())}")
        self._mmrs_1v1_df = self._mmrs_1v1_df.with_columns(**updates)
        print(f"[DataAccessService] After with_columns, DataFrame has {len(self._mmrs_1v1_df)} rows")
        
        # VERIFY the update actually happened
        after_filter = self._mmrs_1v1_df.filter(mask)
        print(f"[DataAccessService] After update filter found {len(after_filter)} rows")
        
        if after_filter.is_empty():
            print(f"[DataAccessService] ERROR: Row disappeared after update for discord_uid={discord_uid}, race={race}")
            return False
        
        new_value = after_filter[verification_column][0]
        expected_value = update_data[verification_column]
        
        # Compare values (handle different types)
        if new_value != expected_value:
            print(f"[DataAccessService] ERROR: Update failed verification for discord_uid={discord_uid}, race={race}")
            print(f"  Expected {verification_column}={expected_value}, got {new_value}")
            return False
        
        return True
    
    async def update_player_mmr(
        self,
        discord_uid: int,
        race: str,
        new_mmr: int,
        games_played: Optional[int] = None,
        games_won: Optional[int] = None,
        games_lost: Optional[int] = None,
        games_drawn: Optional[int] = None
    ) -> bool:
        """
        Update a player's MMR for a specific race.
        
        Updates in-memory DataFrame instantly, then queues async DB write.
        
        Args:
            discord_uid: Discord user ID
            race: Race code
            new_mmr: New MMR value (integer)
            games_played: Total games played (optional)
            games_won: Games won (optional)
            games_lost: Games lost (optional)
            games_drawn: Games drawn (optional)
            
        Returns:
            True if successful, False if record not found
        """
        if self._mmrs_1v1_df is None:
            print("[DataAccessService] WARNING: MMRs DataFrame not initialized")
            return False
        
        async with self._mmr_lock:
            # Prepare update data
            update_data = {
                "mmr": int(new_mmr),
                "last_played": datetime.now(timezone.utc)
            }
            
            if games_played is not None:
                update_data["games_played"] = games_played
            if games_won is not None:
                update_data["games_won"] = games_won
            if games_lost is not None:
                update_data["games_lost"] = games_lost
            if games_drawn is not None:
                update_data["games_drawn"] = games_drawn
            
            # Update the in-memory DataFrame using the helper method
            success = self._update_mmr_dataframe_row(discord_uid, race, update_data)
            
            if not success:
                return False
            
            # Prepare database write data
            write_data = {
                'discord_uid': discord_uid,
                'race': race,
                'new_mmr': new_mmr
            }
            
            if games_played is not None:
                write_data['games_played'] = games_played
            if games_won is not None:
                write_data['games_won'] = games_won
            if games_lost is not None:
                write_data['games_lost'] = games_lost
            if games_drawn is not None:
                write_data['games_drawn'] = games_drawn
            
            # Queue database write
            job = WriteJob(
                job_type=WriteJobType.UPDATE_MMR,
                data=write_data,
                timestamp=time.time()
            )
            
            await self._queue_write(job)
        
        # Trigger ranking service refresh (outside lock to avoid deadlock)
        from src.backend.services.app_context import ranking_service
        if ranking_service:
            await ranking_service.trigger_refresh()
        
        return True
    
    async def create_or_update_mmr(
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
        Create or update (upsert) a player's MMR record.
        
        Updates in-memory DataFrame instantly, then queues async DB write.
        
        Args:
            discord_uid: Discord user ID
            player_name: Player's name
            race: Race code
            mmr: MMR value (integer)
            games_played: Total games played
            games_won: Games won
            games_lost: Games lost
            games_drawn: Games drawn
            
        Returns:
            True if successful
        """
        if self._mmrs_1v1_df is None:
            print("[DataAccessService] WARNING: MMRs DataFrame not initialized")
            return False
        
        # Validate player_name to prevent bad entries
        import re
        bad_name_pattern = re.compile(r'^[Pp]layer\d+$')
        if bad_name_pattern.match(str(player_name)):
            print(f"[DataAccessService] WARNING: Suspicious player_name detected: '{player_name}' for discord_uid={discord_uid}")
            
            # Attempt to auto-correct by looking up actual name from players table
            if self._players_df is not None:
                player_info_rows = self._players_df.filter(pl.col('discord_uid') == discord_uid)
                
                if len(player_info_rows) > 0:
                    correct_name = player_info_rows[0, 'player_name']
                    if correct_name is None or bad_name_pattern.match(str(correct_name)):
                        # Fall back to discord_username if player_name is also bad/missing
                        correct_name = player_info_rows[0, 'discord_username']
                    
                    if correct_name and not bad_name_pattern.match(str(correct_name)):
                        print(f"[DataAccessService] Auto-corrected player_name: '{player_name}' -> '{correct_name}'")
                        player_name = correct_name
                    else:
                        print(f"[DataAccessService] ERROR: Cannot find valid player_name for discord_uid={discord_uid}")
                        return False
                else:
                    print(f"[DataAccessService] ERROR: No player record found for discord_uid={discord_uid}")
                    return False
            else:
                print(f"[DataAccessService] ERROR: Players DataFrame not initialized, cannot validate player_name")
                return False
        
        # Ensure MMR is an integer
        mmr = int(mmr)
        
        async with self._mmr_lock:
            # Check if record exists
            mask = (pl.col("discord_uid") == discord_uid) & (pl.col("race") == race)
            existing = self._mmrs_1v1_df.filter(mask)
            
            if not existing.is_empty():
                # --- UPDATE PATH ---
                # Prepare update data
                update_data = {
                    "mmr": mmr,
                    "player_name": player_name,
                    "games_played": games_played,
                    "games_won": games_won,
                    "games_lost": games_lost,
                    "games_drawn": games_drawn,
                    "last_played": datetime.now(timezone.utc)
                }
                
                # Update the in-memory DataFrame using the helper method
                success = self._update_mmr_dataframe_row(discord_uid, race, update_data)
                
                if not success:
                    print(f"[DataAccessService] ERROR: Failed to update MMR for {discord_uid}/{race}")
                    return False
            else:
                # --- CREATE PATH ---
                # Create new record with schema matching the existing DataFrame
                new_row_data = {
                    "id": None,  # Will be assigned by database
                    "discord_uid": discord_uid,
                    "player_name": player_name,
                    "race": race,
                    "mmr": mmr,
                    "games_played": games_played,
                    "games_won": games_won,
                    "games_lost": games_lost,
                    "games_drawn": games_drawn,
                    "last_played": datetime.now(timezone.utc)
                }
                
                # Create DataFrame with explicit schema to ensure compatibility
                new_row_df = pl.DataFrame([new_row_data], schema=self._mmrs_1v1_df.schema)
                
                # Concatenate to add the new row
                self._mmrs_1v1_df = pl.concat([self._mmrs_1v1_df, new_row_df])
                
                print(f"[DataAccessService] Created new MMR record for {discord_uid}/{race}")
            
            # Queue database write
            job = WriteJob(
                job_type=WriteJobType.CREATE_MMR,
                data={
                    'discord_uid': discord_uid,
                    'player_name': player_name,
                    'race': race,
                    'mmr': mmr,
                    'games_played': games_played,
                    'games_won': games_won,
                    'games_lost': games_lost,
                    'games_drawn': games_drawn
                },
                timestamp=time.time()
            )
            
            await self._queue_write(job)
        
        # Trigger ranking service refresh (outside lock to avoid deadlock)
        from src.backend.services.app_context import ranking_service
        if ranking_service:
            await ranking_service.trigger_refresh()
        
        return True
    
    # ========== Read Methods (Preferences Table) ==========
    
    def get_player_preferences(self, discord_uid: int) -> Optional[Dict[str, Any]]:
        """
        Get a player's 1v1 preferences.
        
        Args:
            discord_uid: Discord user ID
            
        Returns:
            Dictionary with preference data or None if not found
        """
        if self._preferences_1v1_df is None:
            print("[DataAccessService] WARNING: Preferences DataFrame not initialized")
            return None
        
        result = self._preferences_1v1_df.filter(pl.col("discord_uid") == discord_uid)
        
        if len(result) == 0:
            return None
        
        # Convert to dictionary
        return result.to_dicts()[0]
    
    def get_player_last_races(self, discord_uid: int) -> Optional[str]:
        """
        Get a player's last chosen races (JSON string).
        
        Args:
            discord_uid: Discord user ID
            
        Returns:
            JSON string of last chosen races or None
        """
        prefs = self.get_player_preferences(discord_uid)
        return prefs.get("last_chosen_races") if prefs else None
    
    def get_player_last_vetoes(self, discord_uid: int) -> Optional[str]:
        """
        Get a player's last chosen map vetoes (JSON string).
        
        Args:
            discord_uid: Discord user ID
            
        Returns:
            JSON string of last chosen vetoes or None
        """
        prefs = self.get_player_preferences(discord_uid)
        return prefs.get("last_chosen_vetoes") if prefs else None
    
    # ========== Write Methods (Preferences Table) ==========
    
    async def update_player_preferences(
        self,
        discord_uid: int,
        last_chosen_races: Optional[str] = None,
        last_chosen_vetoes: Optional[str] = None
    ) -> bool:
        """
        Update (or create) a player's 1v1 preferences.
        
        Updates in-memory DataFrame instantly, then queues async DB write.
        
        Args:
            discord_uid: Discord user ID
            last_chosen_races: JSON string of last chosen races (optional)
            last_chosen_vetoes: JSON string of last chosen map vetoes (optional)
            
        Returns:
            True if successful
        """
        if self._preferences_1v1_df is None:
            print("[DataAccessService] WARNING: Preferences DataFrame not initialized")
            return False
        
        if last_chosen_races is None and last_chosen_vetoes is None:
            return False
        
        # Check if record exists
        mask = pl.col("discord_uid") == discord_uid
        existing = self._preferences_1v1_df.filter(mask)
        
        if len(existing) > 0:
            # Update existing record
            updates = {}
            if last_chosen_races is not None:
                updates["last_chosen_races"] = pl.when(mask).then(pl.lit(last_chosen_races)).otherwise(pl.col("last_chosen_races"))
            if last_chosen_vetoes is not None:
                updates["last_chosen_vetoes"] = pl.when(mask).then(pl.lit(last_chosen_vetoes)).otherwise(pl.col("last_chosen_vetoes"))
            
            self._preferences_1v1_df = self._preferences_1v1_df.with_columns(**updates)
        else:
            # Create new record
            new_row = pl.DataFrame({
                "discord_uid": [discord_uid],
                "last_chosen_races": [last_chosen_races],
                "last_chosen_vetoes": [last_chosen_vetoes],
            })
            self._preferences_1v1_df = pl.concat([self._preferences_1v1_df, new_row], how="diagonal")
        
        # Queue database write
        job = WriteJob(
            job_type=WriteJobType.UPDATE_PREFERENCES,
            data={
                'discord_uid': discord_uid,
                'last_chosen_races': last_chosen_races,
                'last_chosen_vetoes': last_chosen_vetoes
            },
            timestamp=time.time()
        )
        
        await self._queue_write(job)
        
        return True
    
    # ========== Read Methods (Matches Table) ==========
    
    def get_match(self, match_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific match by ID from in-memory DataFrame.
        
        Args:
            match_id: Match ID
            
        Returns:
            Match data dictionary or None if not found
        """
        if self._matches_1v1_df is None:
            return None
        
        result = self._matches_1v1_df.filter(pl.col("id") == match_id)
        return result.to_dicts()[0] if len(result) > 0 else None
    
    def get_match_mmrs(self, match_id: int) -> tuple[int, int]:
        """
        Get player MMRs for a match (optimized for match embed).
        
        Args:
            match_id: Match ID
            
        Returns:
            Tuple of (player_1_mmr, player_2_mmr)
            
        Raises:
            ValueError: If match not found in memory (DataAccessService is source of truth)
        """
        if self._matches_1v1_df is None:
            raise ValueError(f"[DataAccessService] Matches DataFrame not initialized. Cannot get MMRs for match {match_id}")
        
        match = self.get_match(match_id)
        if not match:
            raise ValueError(f"[DataAccessService] Match {match_id} not found in memory. DataAccessService is the source of truth - match should have been written to memory first.")
        
        p1_mmr = int(match.get('player_1_mmr', 0))
        p2_mmr = int(match.get('player_2_mmr', 0))
        return (p1_mmr, p2_mmr)
    
    def get_player_recent_matches(self, discord_uid: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent matches for a player."""
        if self._matches_1v1_df is None:
            return []
        
        result = self._matches_1v1_df.filter(
            (pl.col("player_1_discord_uid") == discord_uid) | 
            (pl.col("player_2_discord_uid") == discord_uid)
        ).head(limit)
        
        return result.to_dicts()
    
    # ========== Read Methods (Replays Table) ==========
    
    def get_replay(self, replay_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific replay by ID."""
        if self._replays_df is None:
            return None
        
        result = self._replays_df.filter(pl.col("id") == replay_id)
        return result.to_dicts()[0] if len(result) > 0 else None
    
    def get_replay_by_path(self, replay_path: str) -> Optional[Dict[str, Any]]:
        """Get a specific replay by file path."""
        if self._replays_df is None:
            return None
        
        result = self._replays_df.filter(pl.col("replay_path") == replay_path)
        return result.to_dicts()[0] if len(result) > 0 else None
    
    # ========== Write Methods (Matches Table) ==========
    
    async def create_match(self, match_data: Dict[str, Any]) -> Optional[int]:
        """
        Create a new match record.
        
        For now, delegates to database and reloads match data.
        Full in-memory implementation can be added later if needed.
        """
        # For matches, we'll implement a simple pass-through for now
        # since the match creation logic is complex
        loop = asyncio.get_running_loop()
        match_id = await loop.run_in_executor(
            None,
            self._db_writer.create_match_1v1,
            match_data.get('player_1_discord_uid'),
            match_data.get('player_2_discord_uid'),
            match_data.get('player_1_race'),
            match_data.get('player_2_race'),
            match_data.get('map_played'),
            match_data.get('server_choice'),  # Fixed: was 'server_used', should be 'server_choice'
            match_data.get('player_1_mmr'),
            match_data.get('player_2_mmr'),
            match_data.get('mmr_change')
        )
        
        # Reload the match into memory
        if match_id:
            match = await loop.run_in_executor(None, self._db_reader.get_match_1v1, match_id)
            if match:
                # Create new row with explicit schema alignment
                new_row = pl.DataFrame([match], infer_schema_length=None)
                # Use diagonal concat to handle any missing columns gracefully
                try:
                    self._matches_1v1_df = pl.concat([new_row, self._matches_1v1_df], how="diagonal_relaxed")
                except Exception as e:
                    print(f"[DataAccessService] Error concatenating match: {e}")
                    # Fallback: recreate the match dataframe with the new row
                    self._matches_1v1_df = pl.concat([new_row, self._matches_1v1_df], how="diagonal")
                # Keep only recent 1000 matches
                if len(self._matches_1v1_df) > 1000:
                    self._matches_1v1_df = self._matches_1v1_df.head(1000)
                
                print(f"[DataAccessService] Created match {match_id}")
        
        return match_id
    
    async def update_match_replay(
        self,
        match_id: int,
        player_discord_uid: int,
        replay_path: str,
        replay_time: str
    ) -> bool:
        """Update replay information for a match with immediate in-memory update."""
        if self._matches_1v1_df is None:
            print("[DataAccessService] WARNING: Matches DataFrame not initialized")
            return False
        
        # Update in-memory immediately
        try:
            # Find the match and which player uploaded
            match_row = self._matches_1v1_df.filter(pl.col("id") == match_id)
            if len(match_row) == 0:
                print(f"[DataAccessService] WARNING: Match {match_id} not found in memory")
                # Still queue the write for the database
            else:
                match_data = match_row.to_dicts()[0]
                
                # Determine which player column to update
                if match_data['player_1_discord_uid'] == player_discord_uid:
                    replay_col = 'player_1_replay_path'
                    time_col = 'player_1_replay_time'
                elif match_data['player_2_discord_uid'] == player_discord_uid:
                    replay_col = 'player_2_replay_path'
                    time_col = 'player_2_replay_time'
                else:
                    print(f"[DataAccessService] WARNING: Player {player_discord_uid} not in match {match_id}")
                    replay_col = None
                
                if replay_col:
                    # Update the DataFrame
                    self._matches_1v1_df = self._matches_1v1_df.with_columns([
                        pl.when(pl.col("id") == match_id)
                          .then(pl.lit(replay_path))
                          .otherwise(pl.col(replay_col))
                          .alias(replay_col),
                        pl.when(pl.col("id") == match_id)
                          .then(pl.lit(replay_time))
                          .otherwise(pl.col(time_col))
                          .alias(time_col)
                    ])
                    print(f"[DataAccessService] Updated match {match_id} replay in memory ({replay_col})")
        
        except Exception as e:
            print(f"[DataAccessService] Error updating match replay in memory: {e}")
            import traceback
            traceback.print_exc()
        
        # Queue async write to database
        job = WriteJob(
            job_type=WriteJobType.UPDATE_MATCH,
            data={
                'match_id': match_id,
                'player_discord_uid': player_discord_uid,
                'replay_path': replay_path,
                'replay_time': replay_time
            },
            timestamp=time.time()
        )
        
        await self._queue_write(job)
        
        return True
    
    # ========== Write Methods (Replays Table) ==========
    
    async def insert_replay(self, replay_data: Dict[str, Any]) -> bool:
        """
        Insert a new replay record with immediate in-memory update.
        
        Args:
            replay_data: Replay data dictionary
            
        Returns:
            True if the write was queued successfully
        """
        # Update in-memory immediately
        if self._replays_df is not None:
            try:
                # Create new row DataFrame
                new_row = pl.DataFrame([replay_data], infer_schema_length=None)
                
                # Concatenate to add the new row (prepend for recent-first ordering)
                self._replays_df = pl.concat([new_row, self._replays_df], how="diagonal_relaxed")
                
                print(f"[DataAccessService] Added replay to memory: {replay_data.get('replay_hash', 'unknown')}")
            except Exception as e:
                print(f"[DataAccessService] Error adding replay to memory: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("[DataAccessService] WARNING: Replays DataFrame not initialized")
        
        # Queue async write to database
        job = WriteJob(
            job_type=WriteJobType.INSERT_REPLAY,
            data=replay_data,
            timestamp=time.time()
        )
        
        await self._queue_write(job)
        
        return True
    
    # ========== Write Methods (Write-Only Tables) ==========
    
    async def log_player_action(
        self,
        discord_uid: int,
        player_name: str,
        setting_name: str,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        changed_by: str = "player"
    ) -> None:
        """
        Log a player action to the player_action_logs table.
        
        This is write-only (not stored in memory) and processes asynchronously.
        
        Args:
            discord_uid: Discord user ID
            player_name: Player's display name
            setting_name: Name of the setting changed
            old_value: Old value
            new_value: New value
            changed_by: Who made the change
        """
        job = WriteJob(
            job_type=WriteJobType.LOG_PLAYER_ACTION,
            data={
                'discord_uid': discord_uid,
                'player_name': player_name,
                'setting_name': setting_name,
                'old_value': old_value,
                'new_value': new_value,
                'changed_by': changed_by
            },
            timestamp=time.time()
        )
        
        await self._queue_write(job)
    
    async def insert_command_call(
        self,
        discord_uid: int,
        player_name: str,
        command_name: str
    ) -> None:
        """Logs a command call with the current timestamp."""
        job_data = {
            "discord_uid": discord_uid,
            "player_name": player_name,
            "command": command_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        job = WriteJob(
            job_type=WriteJobType.INSERT_COMMAND_CALL,
            data=job_data,
            timestamp=time.time()
        )
        
        await self._queue_write(job)
    
    async def log_admin_action(
        self,
        admin_discord_uid: int,
        admin_username: str,
        action_type: str,
        target_player_uid: Optional[int] = None,
        target_match_id: Optional[int] = None,
        action_details: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None
    ) -> None:
        """
        Log an admin action to the admin_actions table.
        
        This is write-only (not stored in memory) and processes asynchronously.
        All admin operations should log through this method for audit trail.
        
        Args:
            admin_discord_uid: Discord user ID of admin performing action
            admin_username: Display name of admin
            action_type: Type of action (e.g., 'resolve_conflict', 'adjust_mmr')
            target_player_uid: Discord UID of target player (if applicable)
            target_match_id: Match ID being modified (if applicable)
            action_details: JSON-serializable dict with action details
            reason: Human-readable reason for the action
        """
        job = WriteJob(
            job_type=WriteJobType.LOG_ADMIN_ACTION,
            data={
                'admin_discord_uid': admin_discord_uid,
                'admin_username': admin_username,
                'action_type': action_type,
                'target_player_uid': target_player_uid,
                'target_match_id': target_match_id,
                'action_details': json.dumps(action_details or {}),
                'reason': reason
            },
            timestamp=time.time()
        )
        
        await self._queue_write(job)
    
    async def record_system_abort(
        self,
        match_id: int,
        p1_report: Optional[int],
        p2_report: Optional[int]
    ) -> None:
        """
        Record a system-initiated abort for unconfirmed matches.
        
        This method is used when players fail to confirm a match in time.
        It updates match reports and sets the match result to -1 (aborted)
        WITHOUT decrementing player abort counters.
        
        Args:
            match_id: The ID of the match to abort
            p1_report: Player 1's report value (-4 if they didn't confirm, None if they did)
            p2_report: Player 2's report value (-4 if they didn't confirm, None if they did)
        """
        # Update in-memory DataFrame immediately to reflect the abort
        if self._matches_1v1_df is not None:
            self._matches_1v1_df = self._matches_1v1_df.with_columns([
                pl.when(pl.col("id") == match_id)
                  .then(pl.lit(p1_report))
                  .otherwise(pl.col("player_1_report"))
                  .alias("player_1_report"),
                pl.when(pl.col("id") == match_id)
                  .then(pl.lit(p2_report))
                  .otherwise(pl.col("player_2_report"))
                  .alias("player_2_report"),
                pl.when(pl.col("id") == match_id)
                  .then(pl.lit(-1))  # match_result: -1 for aborted
                  .otherwise(pl.col("match_result"))
                  .alias("match_result")
            ])
            print(f"[DataAccessService] Updated match {match_id} reports and result to ABORTED in memory (unconfirmed)")

        job = WriteJob(
            job_type=WriteJobType.SYSTEM_ABORT_UNCONFIRMED,
            data={
                'match_id': match_id,
                'player_1_report': p1_report,
                'player_2_report': p2_report
            },
            timestamp=time.time()
        )
        
        await self._queue_write(job)
    
    # ========== Match Operations ==========
    
    async def abort_match(self, match_id: int, player_discord_uid: int) -> bool:
        """
        Abort a match using DataAccessService for fast operations.
        
        Updates in-memory match state immediately, then queues database write.
        
        Args:
            match_id: Match ID to abort
            player_discord_uid: Discord UID of player aborting
            
        Returns:
            True if abort was successful
        """
        try:
            # Get match data from memory first - DataAccessService is source of truth
            match = self.get_match(match_id)
            if not match:
                print(f"[DataAccessService] Match {match_id} not found in memory")
                return False
            
            p1_discord_uid = match.get('player_1_discord_uid')
            p2_discord_uid = match.get('player_2_discord_uid')
            
            # Verify player is in this match
            if player_discord_uid not in [p1_discord_uid, p2_discord_uid]:
                print(f"[DataAccessService] Player {player_discord_uid} not in match {match_id}")
                return False
            
            # Check if match is already aborted
            match_result = match.get('match_result')
            if match_result == -1:
                print(f"[DataAccessService] Match {match_id} already aborted, treating as success for player {player_discord_uid}")
                # Don't decrement aborts again, but return success so the UI updates correctly
                return True
            
            # Decrement aborts in memory (instant)
            current_aborts = self.get_remaining_aborts(player_discord_uid)
            if current_aborts > 0:
                await self.update_remaining_aborts(player_discord_uid, current_aborts - 1)
                print(f"[DataAccessService] Decremented aborts for player {player_discord_uid}: {current_aborts} -> {current_aborts - 1}")
            
            # Update match state in memory immediately
            # - Set aborting player's report to -3 (to identify them)
            # - Set other player's report to -1 (aborted, no fault)
            # - Set match_result to -1 (aborted)
            if self._matches_1v1_df is not None:
                # Determine which player aborted
                is_player1_aborting = player_discord_uid == p1_discord_uid
                
                self._matches_1v1_df = self._matches_1v1_df.with_columns([
                    pl.when(pl.col("id") == match_id)
                      .then(pl.lit(-3 if is_player1_aborting else -1))
                      .otherwise(pl.col("player_1_report"))
                      .alias("player_1_report"),
                    pl.when(pl.col("id") == match_id)
                      .then(pl.lit(-3 if not is_player1_aborting else -1))
                      .otherwise(pl.col("player_2_report"))
                      .alias("player_2_report"),
                    pl.when(pl.col("id") == match_id)
                      .then(pl.lit(-1))
                      .otherwise(pl.col("match_result"))
                      .alias("match_result")
                ])
                print(f"[DataAccessService] Updated match {match_id} state to aborted in memory (aborting player: {player_discord_uid})")
            
            # Queue the actual abort operation to database (async)
            job = WriteJob(
                job_type=WriteJobType.ABORT_MATCH,
                data={
                    "match_id": match_id,
                    "player_discord_uid": player_discord_uid,
                    "p1_discord_uid": p1_discord_uid,
                    "p2_discord_uid": p2_discord_uid
                },
                timestamp=time.time()
            )
            
            await self._write_queue.put(job)
            self._total_writes_queued += 1
            
            return True
            
        except Exception as e:
            print(f"[DataAccessService] Error aborting match {match_id}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def update_match(self, match_id: int, **kwargs) -> bool:
        """
        Update match data with immediate in-memory update.
        
        Args:
            match_id: Match ID
            **kwargs: Match fields to update (e.g., match_result, player_1_report, etc.)
            
        Returns:
            True if updated successfully
        """
        if self._matches_1v1_df is None:
            print("[DataAccessService] WARNING: Matches DataFrame not initialized")
            return False
        
        try:
            # Update in-memory immediately
            if len(self._matches_1v1_df.filter(pl.col("id") == match_id)) > 0:
                # Update the match in memory
                for key, value in kwargs.items():
                    if key in self._matches_1v1_df.columns:
                        self._matches_1v1_df = self._matches_1v1_df.with_columns(
                            pl.when(pl.col("id") == match_id)
                            .then(pl.lit(value))
                            .otherwise(pl.col(key))
                            .alias(key)
                        )
                        print(f"[DataAccessService] Updated match {match_id} {key} to {value} in memory")
            
            # Queue database write
            job = WriteJob(
                job_type=WriteJobType.UPDATE_MATCH,
                data={
                    "match_id": match_id,
                    **kwargs
                },
                timestamp=time.time()
            )
            
            await self._write_queue.put(job)
            self._total_writes_queued += 1
            return True
            
        except Exception as e:
            print(f"[DataAccessService] Error updating match {match_id}: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def update_match_mmr_change(self, match_id: int, mmr_change: int) -> bool:
        """
        Update the MMR change for a match.
        
        Updates in-memory DataFrame immediately and queues async database write.
        
        Args:
            match_id: Match ID
            mmr_change: MMR change amount (positive = player 1 gained)
            
        Returns:
            True if successfully updated in memory and queued
        """
        try:
            # Update in-memory DataFrame immediately
            import polars as pl
            if self._matches_1v1_df is not None:
                self._matches_1v1_df = self._matches_1v1_df.with_columns(
                    pl.when(pl.col("id") == match_id)
                      .then(pl.lit(mmr_change))
                      .otherwise(pl.col("mmr_change"))
                      .alias("mmr_change")
                )
                print(f"[DataAccessService] Updated mmr_change={mmr_change} in memory for match {match_id}")
            
            # Queue database write
            job = WriteJob(
                job_type=WriteJobType.UPDATE_MATCH_MMR_CHANGE,
                data={
                    "match_id": match_id,
                    "mmr_change": mmr_change
                },
                timestamp=time.time()
            )
            
            await self._write_queue.put(job)
            self._total_writes_queued += 1
            
            return True
            
        except Exception as e:
            print(f"[DataAccessService] Error queuing match MMR change update: {e}")
            import traceback
            traceback.print_exc()
            return False


# Global singleton instance
data_access_service = DataAccessService()

