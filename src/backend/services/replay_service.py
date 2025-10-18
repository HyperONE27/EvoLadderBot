"""
Replay service.
"""

from dataclasses import dataclass, asdict
import json
import sc2reader
import xxhash
from typing import Optional
import hashlib
import os
from datetime import datetime, timezone
from src.backend.db.db_reader_writer import DatabaseWriter, get_timestamp
from src.bot.utils.discord_utils import get_current_unix_timestamp
import io


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
    """Replay service."""

    def __init__(self, replay_dir="data/replays"):
        self.replay_dir = replay_dir
        os.makedirs(self.replay_dir, exist_ok=True)

    def is_sc2_replay(self, filename: str) -> bool:
        """Check if a file is an SC2Replay file."""
        return filename.lower().endswith(".sc2replay")

    def parse_replay(self, replay_data, is_bytes=False) -> Optional[ReplayParsed]:
        """Parse a replay file."""
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
            return None

    def store_upload(self, match_id: int, uploader_id: int, replay_bytes: bytes) -> dict:
        """Saves a replay file and updates the database."""
        try:
            replay_path = self.save_replay(replay_bytes)
            
            # Parse the replay to get the data for the replays table
            parsed_replay = self.parse_replay(replay_bytes, is_bytes=True)
            if not parsed_replay:
                raise Exception("Failed to parse replay.")

            db_writer = DatabaseWriter()

            # Insert the parsed replay data into the new replays table
            replay_data = asdict(parsed_replay)
            replay_data['replay_path'] = replay_path  # Add the path to the data
            replay_data['observers'] = json.dumps(replay_data['observers'])  # Convert list to JSON string
            db_writer.insert_replay(replay_data)

            sql_timestamp = get_timestamp()
            success = db_writer.update_match_replay_1v1(
                match_id,
                uploader_id,
                replay_path,
                sql_timestamp
            )

            return {
                "success": success,
                "unix_epoch": get_current_unix_timestamp() if success else None
            }
        except Exception as e:
            print(f"Error storing replay upload: {e}")
            return {"success": False, "unix_epoch": None}

    def _calculate_replay_hash(self, replay_bytes: bytes) -> str:
        """Calculates an 80-bit blake2b hash of the replay."""
        hasher = hashlib.blake2b(digest_size=10)  # 80 bits = 10 bytes
        hasher.update(replay_bytes)
        return hasher.hexdigest()

    def _generate_filename(self, replay_hash: str) -> str:
        """Generates a new filename for the replay."""
        timestamp = int(datetime.now(timezone.utc).timestamp())
        return f"{replay_hash}_{timestamp}.SC2Replay"

    def save_replay(self, replay_bytes: bytes) -> str:
        """Saves a replay file and returns its new path."""
        replay_hash = self._calculate_replay_hash(replay_bytes)
        filename = self._generate_filename(replay_hash)
        filepath = os.path.join(self.replay_dir, filename)

        print(f"Renaming replay to: {filename}")
        print(f"Saving replay to: {filepath}")

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
                        return (event.second / 1.4)     # Faster is 1.4 times Normal
        else:
            return int(replay.game_length.seconds)

if __name__ == "__main__":
    replay_service = ReplayService()
    parsed_replay = replay_service.parse_replay("tests/test_data/test_replay_files/GoldenWall.SC2Replay")
    print(parsed_replay)