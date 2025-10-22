"""
Replay service.
"""

import hashlib
import io
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

import sc2reader
import xxhash

from src.backend.db.db_reader_writer import DatabaseWriter, get_timestamp
from src.bot.utils.discord_utils import get_current_unix_timestamp


class ReplayParseError(Exception):
    """Custom exception for replay parsing errors."""
    pass


def parse_replay_data_blocking(replay_bytes: bytes) -> dict:
    """
    Parses replay file data using sc2reader in a blocking, CPU-bound manner.
    This function is designed to be run in a separate process to avoid blocking
    the main application's event loop.

    Args:
        replay_bytes: The raw byte content of the .SC2Replay file.

    Returns:
        A dictionary containing key information about the replay, or an error dict.
        The dictionary contains either:
        - On success: All parsed replay data fields with 'error': None
        - On failure: 'error': <error_message> with other fields None or partial
    """
    import logging
    import os
    import sys
    import time
    
    # Track memory usage in worker
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss / 1024 / 1024  # MB
        print(f"[Worker Process] Memory before parse: {mem_before:.2f} MB")
    except:
        mem_before = None
    
    start_time = time.time()
    
    print(f"[Worker Process] Starting replay parse (size: {len(replay_bytes)} bytes)...")
    
    # Suppress sc2reader logging errors to reduce noise
    sc2reader_logger = logging.getLogger('sc2reader')
    sc2reader_logger.setLevel(logging.CRITICAL)  # Only show critical errors
    
    # Also suppress stderr for sc2reader to prevent error spam
    original_stderr = sys.stderr
    try:
        # Redirect stderr to devnull to suppress sc2reader errors
        sys.stderr = open(os.devnull, 'w')
        
        # Load the replay using sc2reader at level 4 for full parsing
        replay = sc2reader.load_replay(io.BytesIO(replay_bytes), load_level=4)
        
        # Validate player count
        if len(replay.players) != 2:
            error_msg = f"Expected 2 players, but replay has {len(replay.players)} players"
            print(f"[Worker Process] Parse failed: {error_msg}")
            return {"error": error_msg}
        
        # Calculate replay hash
        hasher = hashlib.blake2b(digest_size=10)  # 80 bits = 10 bytes
        hasher.update(replay_bytes)
        replay_hash = hasher.hexdigest()
        
        # Extract player information
        player1 = replay.players[0]
        player2 = replay.players[1]
        
        # Fix race names to match database format
        def fix_race(race):
            race_map = {
                "Terran": "sc2_terran",
                "Zerg": "sc2_zerg",
                "Protoss": "sc2_protoss",
                "BW Terran": "bw_terran",
                "BW Zerg": "bw_zerg",
                "BW Protoss": "bw_protoss"
            }
            return race_map.get(race, race)
        
        player_1_race = fix_race(player1.play_race)
        player_2_race = fix_race(player2.play_race)
        
        # Determine winner
        winner = replay.winner
        if winner is None:
            # Try to infer winner from defeat messages
            remaining = set(p.name for p in replay.players)
            for msg in replay.messages:
                if msg.text.endswith("was defeated!"):
                    left_name = msg.text.replace(" was defeated!", "")
                    remaining.discard(left_name)
            if len(remaining) == 1:
                winner_name = next(iter(remaining))
                for p in replay.players:
                    if p.name == winner_name:
                        winner = p
        
        # Convert winner to result int
        if winner is None:
            result = 0  # Draw
        else:
            winner_str = str(winner)
            if "Player 1" in winner_str:
                result = 1
            elif "Player 2" in winner_str:
                result = 2
            else:
                result = 0
        
        # Extract toon handles
        def find_toon_handles(data):
            """Recursively search for toon_handle keys in a dictionary or list."""
            handles = []
            
            def traverse(obj):
                if isinstance(obj, dict):
                    if "toon_handle" in obj and obj["toon_handle"] != '':
                        handles.append(obj["toon_handle"])
                    for value in obj.values():
                        if isinstance(value, (dict, list)):
                            traverse(value)
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, (dict, list)):
                            traverse(item)
            
            traverse(data)
            return handles
        
        toon_handles = find_toon_handles(replay.raw_data)
        player_1_handle = toon_handles[0] if len(toon_handles) >= 1 else ''
        player_2_handle = toon_handles[1] if len(toon_handles) >= 2 else ''
        
        # Get duration
        duration = None
        if hasattr(replay, 'game_events'):
            for event in replay.game_events:
                if event.name == 'PlayerLeaveEvent':
                    # Ensure player is not an observer
                    if event.player and not event.player.is_observer:
                        duration = int(round(event.second / 1.4))  # Faster is 1.4 times Normal
                        break
        
        if duration is None and hasattr(replay, 'game_length'):
            duration = int(round(replay.game_length.seconds))
        
        # Get observers
        observers = [o.name for o in replay.observers]
        
        # Get replay date
        replay_date = replay.date.isoformat() if hasattr(replay, 'date') and replay.date else ''
        
        elapsed_time = time.time() - start_time
        
        # Log memory usage after parse
        if mem_before is not None:
            try:
                mem_after = process.memory_info().rss / 1024 / 1024
                mem_delta = mem_after - mem_before
                print(f"[Worker Process] Memory after parse: {mem_after:.2f} MB (Δ {mem_delta:+.2f} MB)")
            except:
                pass
        
        print(f"[Worker Process] Parse complete for hash {replay_hash} in {elapsed_time:.3f}s")
        
        return {
            "error": None,
            "replay_hash": replay_hash,
            "replay_date": replay_date,
            "player_1_name": player1.name,
            "player_2_name": player2.name,
            "player_1_race": player_1_race,
            "player_2_race": player_2_race,
            "result": result,
            "player_1_handle": player_1_handle,
            "player_2_handle": player_2_handle,
            "observers": observers,  # Keep as list, will be JSON-encoded later
            "map_name": replay.map_name,
            "duration": duration if duration is not None else 0
        }
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        error_msg = f"sc2reader failed to parse replay: {type(e).__name__}: {str(e)}"
        print(f"[Worker Process] Parse failed after {elapsed_time:.3f}s: {error_msg}")
        return {"error": error_msg}
    finally:
        # Restore stderr
        sys.stderr.close()
        sys.stderr = original_stderr


@dataclass
class ReplayRaw:
    """Raw replay data."""
    replay_bytes: bytes
    replay_path: str


@dataclass
class ReplayParsed:
    """Just the bits of the replay we need."""
    replay_hash: str
    replay_date: str
    player_1_name: str
    player_2_name: str
    player_1_race: str
    player_2_race: str
    result: int
    player_1_handle: str
    player_2_handle: str
    observers: list[str]
    map_name: str
    duration: int

class ReplayService:
    """
    Replay service for handling replay file storage and database operations.
    
    Note: CPU-intensive replay parsing is handled by the standalone
    parse_replay_data_blocking() function which runs in worker processes.
    This service handles the fast I/O operations (file storage, database writes).
    """

    def __init__(self, replay_dir="data/replays"):
        self.replay_dir = replay_dir
        os.makedirs(self.replay_dir, exist_ok=True)

    def is_sc2_replay(self, filename: str) -> bool:
        """Check if a file is an SC2Replay file."""
        return filename.lower().endswith(".sc2replay")

    def parse_replay(self, replay_data, is_bytes=False) -> Optional[ReplayParsed]:
        """
        LEGACY METHOD - Use parse_replay_data_blocking() instead for production.
        
        This method performs BLOCKING, CPU-intensive parsing and should only be
        used for testing/debugging purposes. For production use with the Discord bot,
        use parse_replay_data_blocking() via run_in_executor() to avoid blocking
        the event loop.
        """
        try:
            if is_bytes:
                replay_bytes = replay_data
            else:
                with open(replay_data, 'rb') as f:
                    replay_bytes = f.read()

            replay = self._load_replay(replay_bytes)

            replay_hash = self._calculate_replay_hash(replay_bytes)
            player_1_name, player_2_name, player_1_race, player_2_race = self._get_player_info(replay)
            player_1_race, player_2_race = self._fix_race(player_1_race), self._fix_race(player_2_race)
            result = self._get_winner(replay)
            player_1_handle, player_2_handle = self._get_toon_handles(replay)
            map_name = replay.map_name
            duration = self._get_duration(replay)
            replay_date = replay.date.isoformat() if hasattr(replay, 'date') and replay.date else ''
            observers = self._get_observers(replay)
            return ReplayParsed(
                replay_date=replay_date,
                replay_hash=replay_hash,
                player_1_name=player_1_name,
                player_2_name=player_2_name,
                player_1_race=player_1_race,
                player_2_race=player_2_race,
                result=result,
                player_1_handle=player_1_handle,
                player_2_handle=player_2_handle,
                observers=observers,
                map_name=map_name,
                duration=duration
            )
        except Exception as e:
            print(f"Error processing replay: {e}")
            raise ReplayParseError(e)

    def store_upload(self, match_id: int, uploader_id: int, replay_bytes: bytes) -> dict:
        """
        LEGACY METHOD - Use store_upload_from_parsed_dict() instead for production.
        
        This method performs BLOCKING parsing internally and should only be used
        for testing/debugging. For production use, parse the replay in a worker
        process using parse_replay_data_blocking(), then call
        store_upload_from_parsed_dict() with the result.
        """
        # This method now delegates to the new async workflow
        # Parse the replay first (blocking)
        parsed_dict = self.parse_replay_data_blocking(replay_bytes)
        
        # Delegate to the refactored sync method which uses DataAccessService
        return self.store_upload_from_parsed_dict(match_id, uploader_id, replay_bytes, parsed_dict)
    
    async def store_upload_from_parsed_dict_async(self, match_id: int, uploader_id: int, 
                                                    replay_bytes: bytes, parsed_dict: dict) -> dict:
        """
        ASYNC PRIMARY METHOD for production use with multiprocessing.
        
        Saves a replay file and updates the database using pre-parsed replay data.
        This method uses DataAccessService for non-blocking async writes, eliminating
        the dropdown slowness issue after replay uploads.
        
        Args:
            match_id: The match ID to associate with this replay
            uploader_id: The Discord user ID of the uploader
            replay_bytes: The raw replay bytes (for saving to disk)
            parsed_dict: The dictionary returned from parse_replay_data_blocking()
        
        Returns:
            A dictionary with success status and replay data
        """
        try:
            # Check if parsing failed
            if parsed_dict.get("error"):
                return {"success": False, "error": parsed_dict["error"]}
            
            # Save the replay file (uploads to Supabase Storage, falls back to local)
            # Pass match_id and uploader_id for Supabase storage path
            # Run this in executor since it may do I/O
            import asyncio
            loop = asyncio.get_running_loop()
            replay_url = await loop.run_in_executor(
                None,
                self.save_replay,
                replay_bytes,
                match_id,
                uploader_id
            )
            
            from src.backend.services.data_access_service import DataAccessService
            data_service = DataAccessService()

            # Prepare replay data for database insertion
            replay_data = {
                "replay_hash": parsed_dict["replay_hash"],
                "replay_date": parsed_dict["replay_date"],
                "player_1_name": parsed_dict["player_1_name"],
                "player_2_name": parsed_dict["player_2_name"],
                "player_1_race": parsed_dict["player_1_race"],
                "player_2_race": parsed_dict["player_2_race"],
                "result": parsed_dict["result"],
                "player_1_handle": parsed_dict["player_1_handle"],
                "player_2_handle": parsed_dict["player_2_handle"],
                "observers": json.dumps(parsed_dict["observers"]),  # Convert list to JSON
                "map_name": parsed_dict["map_name"],
                "duration": parsed_dict["duration"],
                "replay_path": replay_url,  # Store URL (Supabase) or path (local fallback)
                "uploaded_at": get_timestamp()  # Add uploaded_at timestamp (new column)
            }
            
            # Insert into replays table (async, non-blocking)
            await data_service.insert_replay(replay_data)

            # Update match record with replay URL/path (async, non-blocking)
            sql_timestamp = get_timestamp()
            await data_service.update_match_replay(
                match_id,
                uploader_id,
                replay_url,  # Store URL (Supabase) or path (local fallback)
                sql_timestamp
            )

            return {
                "success": True,
                "unix_epoch": get_current_unix_timestamp(),
                "replay_data": parsed_dict
            }
            
        except Exception as e:
            print(f"Error storing replay upload from parsed dict: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}
    
    def store_upload_from_parsed_dict(self, match_id: int, uploader_id: int, 
                                       replay_bytes: bytes, parsed_dict: dict) -> dict:
        """
        DEPRECATED: Synchronous version kept for backwards compatibility.
        Use store_upload_from_parsed_dict_async() instead for better performance.
        
        Now delegates to the async version using DataAccessService.
        """
        import asyncio
        
        # Get or create event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, create a temporary one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.store_upload_from_parsed_dict_async(match_id, uploader_id, replay_bytes, parsed_dict)
                )
                return result
            finally:
                loop.close()
        else:
            # Already in an async context, create a task
            task = loop.create_task(
                self.store_upload_from_parsed_dict_async(match_id, uploader_id, replay_bytes, parsed_dict)
            )
            # Return a placeholder - caller should use async version
            return {"success": True, "task": task}

    def _calculate_replay_hash(self, replay_bytes: bytes) -> str:
        """Calculates an 80-bit blake2b hash of the replay."""
        hasher = hashlib.blake2b(digest_size=10)  # 80 bits = 10 bytes
        hasher.update(replay_bytes)
        return hasher.hexdigest()

    def _generate_filename(self, replay_hash: str) -> str:
        """Generates a new filename for the replay."""
        timestamp = int(datetime.now(timezone.utc).timestamp())
        return f"{replay_hash}_{timestamp}.SC2Replay"

    def save_replay(self, replay_bytes: bytes, match_id: int = None, player_discord_uid: int = None) -> str:
        """
        Saves a replay file to Supabase Storage and returns its URL.
        Falls back to local storage if Supabase upload fails.
        
        Args:
            replay_bytes: The replay file bytes
            match_id: Optional match ID for Supabase storage path
            player_discord_uid: Optional player Discord UID for Supabase storage path
            
        Returns:
            URL to replay file (Supabase URL if successful, local path as fallback)
        """
        replay_hash = self._calculate_replay_hash(replay_bytes)
        filename = self._generate_filename(replay_hash)
        
        # Try Supabase Storage first if match_id and player_discord_uid are provided
        if match_id is not None and player_discord_uid is not None:
            try:
                from src.backend.services.storage_service import storage_service
                
                print(f"[Replay] Uploading to Supabase Storage (match: {match_id}, player: {player_discord_uid})...")
                public_url = storage_service.upload_replay(
                    match_id=match_id,
                    player_discord_uid=player_discord_uid,
                    file_data=replay_bytes,
                    filename=filename
                )
                
                if public_url:
                    print(f"[Replay] Upload successful: {public_url}")
                    return public_url
                else:
                    print(f"[Replay] Supabase upload failed, falling back to local storage")
                    
            except Exception as e:
                print(f"[Replay] ERROR during Supabase upload: {e}")
                print(f"[Replay] Falling back to local storage")
        
        # Fallback: Save to local disk
        filepath = os.path.join(self.replay_dir, filename)
        print(f"[Replay] Saving to local disk: {filepath}")
        
        with open(filepath, "wb") as f:
            f.write(replay_bytes)
        
        return filepath

    def _load_replay(self, replay_bytes: bytes):
        """Loads a replay from bytes."""
        return sc2reader.load_replay(io.BytesIO(replay_bytes), load_level=4)

    def _get_player_info(self, replay):
        player1 = replay.players[0]
        player2 = replay.players[1]
        return player1.name, player2.name, player1.play_race, player2.play_race

    def _fix_race(self, race):
        return {
            "Terran": "sc2_terran",
            "Zerg": "sc2_zerg",
            "Protoss": "sc2_protoss",
            "BW Terran": "bw_terran",
            "BW Zerg": "bw_zerg",
            "BW Protoss": "bw_protoss"
        }.get(race, race)

    def _get_winner(self, replay):
        if replay.winner is None:
            replay.winner = self._infer_winner_from_defeat(replay)

        if replay.winner is None:
            return 0  # Draw

        winner_str = str(replay.winner)
        if "Player 1" in winner_str:
            return 1
        elif "Player 2" in winner_str:
            return 2
        return 0

    def _get_toon_handles(self, replay):
        toon_handles = self._find_toon_handles(replay.raw_data)
        if len(toon_handles) >= 2:
            return toon_handles[0], toon_handles[1]
        return '', ''

    def _get_observers(self, replay):
        return [o.name for o in replay.observers]

    def _infer_winner_from_defeat(self, replay):
        remaining = set(p.name for p in replay.players)
        for msg in replay.messages:
            if msg.text.endswith("was defeated!"):
                left_name = msg.text.replace(" was defeated!", "")
                remaining.discard(left_name)
        if len(remaining) == 1:
            winner_name = next(iter(remaining))
            for p in replay.players:
                if p.name == winner_name:
                    return p
        return None

    def _find_toon_handles(self, data):
        """Recursively search for toon_handle keys in a dictionary or list."""
        handles = []
        
        def traverse(obj):
            if isinstance(obj, dict):
                if "toon_handle" in obj and obj["toon_handle"] != '':
                    handles.append(obj["toon_handle"])
                for value in obj.values():
                    if isinstance(value, (dict, list)):
                        traverse(value)
            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, (dict, list)):
                        traverse(item)
        
        traverse(data)
        return handles

    def _get_duration(self, replay):
        if hasattr(replay, 'game_events'):
            for event in replay.game_events:
                if event.name == 'PlayerLeaveEvent':
                    # Ensure player is not an observer
                    if event.player and not event.player.is_observer:
                        return int(round(event.second / 1.4))     # Faster is 1.4 times Normal
        else:
            return int(round(replay.game_length.seconds))

if __name__ == "__main__":
    replay_service = ReplayService()
    parsed_replay = replay_service.parse_replay("tests/test_data/test_replay_files/GoldenWall.SC2Replay")
    print(parsed_replay)