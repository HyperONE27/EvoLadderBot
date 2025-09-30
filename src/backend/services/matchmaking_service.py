"""
Matchmaking service.

This module defines the MatchmakerService class, which contains methods for:
- Creating the matchmaking queue
- Adding and removing players to and from the queue
- Determining valid matches
- Defining the parameters for matchmaking
"""

import asyncio
import random
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass

@dataclass
class QueuePreferences:
    """Player's queue preferences"""
    selected_races: List[str]
    vetoed_maps: List[str]
    discord_user_id: int
    user_id: str  # The player's "gamer name"

@dataclass
class MatchResult:
    """Result of a successful match"""
    player1_discord_id: int
    player2_discord_id: int
    player1_user_id: str
    player2_user_id: str
    map_choice: str
    server_choice: str
    in_game_channel: str

class Player:
    def __init__(self, discord_user_id: int, user_id: str, preferences: QueuePreferences):
        self.discord_user_id = discord_user_id
        self.user_id = user_id
        self.preferences = preferences

    def __repr__(self):
        return f"Player({self.user_id}, discord_id={self.discord_user_id})"


class Matchmaker:
    def __init__(self, players: Optional[List[Player]] = None):
        self.players: List[Player] = players or []
        self.running = False
        self.match_callback: Optional[Callable[[MatchResult], None]] = None

    def add_player(self, player: Player):
        """Add a player to the matchmaking pool."""
        print(f"👤 {player.user_id} (Discord ID: {player.discord_user_id}) joined the queue")
        print(f"   Selected races: {player.preferences.selected_races}")
        print(f"   Vetoed maps: {player.preferences.vetoed_maps}")
        self.players.append(player)
        print(f"   Total players in queue: {len(self.players)}")

    def remove_player(self, discord_user_id: int):
        """Remove a player from the matchmaking pool by Discord ID."""
        before_count = len(self.players)
        self.players = [p for p in self.players if p.discord_user_id != discord_user_id]
        after_count = len(self.players)
        print(f"🚪 Player with Discord ID {discord_user_id} left the queue")
        print(f"   Players before removal: {before_count}, after: {after_count}")

    def set_match_callback(self, callback: Callable[[MatchResult], None]):
        """Set the callback function to be called when a match is found."""
        self.match_callback = callback

    async def is_valid_match(self, p1: Player, p2: Player) -> bool:
        """Check if two players are a valid match (currently always True)."""
        print(f"   🔍 Checking if {p1.user_id} vs {p2.user_id} is valid...")
        await asyncio.sleep(0.1)  # simulate some processing
        return True

    def get_available_maps(self, p1: Player, p2: Player) -> List[str]:
        """Get maps that haven't been vetoed by either player."""
        all_maps = ["Arkanoid", "Death Valley", "Keres Passage", "Khione", "Pylon", 
                   "Radeon", "Subsequence", "Sylphid", "Vermeer"]
        
        # Get vetoed maps from both players
        vetoed_maps = set(p1.preferences.vetoed_maps + p2.preferences.vetoed_maps)
        
        # Return maps that aren't vetoed
        return [map_name for map_name in all_maps if map_name not in vetoed_maps]

    def generate_in_game_channel(self) -> str:
        """Generate a random 3-digit in-game channel name."""
        return "scevo" + str(random.randint(100, 999))

    def get_random_server(self) -> str:
        """Get a random server choice (placeholder for now)."""
        servers = ["US East", "US West", "Europe", "Asia"]
        return random.choice(servers)

    async def attempt_match(self):
        """Try to find and process all valid matches."""
        if len(self.players) < 2:
            return  # Silent when not enough players

        matched = []
        used = set()

        print("🎯 Attempting to match players...")

        for i, p1 in enumerate(self.players):
            if p1.discord_user_id in used:
                continue
            for p2 in self.players[i + 1:]:
                if p2.discord_user_id in used:
                    continue
                if await self.is_valid_match(p1, p2):
                    print(f"✅ Match found: {p1.user_id} vs {p2.user_id}")
                    
                    # Get available maps and pick one randomly
                    available_maps = self.get_available_maps(p1, p2)
                    if not available_maps:
                        print(f"❌ No available maps for {p1.user_id} vs {p2.user_id}")
                        continue
                    
                    map_choice = random.choice(available_maps)
                    server_choice = self.get_random_server()
                    in_game_channel = self.generate_in_game_channel()
                    
                    # Create match result
                    match_result = MatchResult(
                        player1_discord_id=p1.discord_user_id,
                        player2_discord_id=p2.discord_user_id,
                        player1_user_id=p1.user_id,
                        player2_user_id=p2.user_id,
                        map_choice=map_choice,
                        server_choice=server_choice,
                        in_game_channel=in_game_channel
                    )
                    
                    # Call the match callback if set
                    if self.match_callback:
                        print(f"📞 Calling match callback for {p1.user_id} vs {p2.user_id}")
                        self.match_callback(match_result)
                    else:
                        print("⚠️  No match callback set!")
                    
                    matched.append((p1, p2))
                    used.add(p1.discord_user_id)
                    used.add(p2.discord_user_id)
                    break  # move on to next unmatched player

        for p1, p2 in matched:
            self.remove_player(p1.discord_user_id)
            self.remove_player(p2.discord_user_id)

        if not matched:
            print("❌ No valid matches this round.")

    async def run(self):
        """Continuously try to match players every 5 seconds."""
        self.running = True
        print("🚀 Matchmaker started - checking for matches every 5 seconds")
        while self.running:
            await asyncio.sleep(5)
            if len(self.players) > 0:
                print(f"⏰ Checking for matches with {len(self.players)} players in queue...")
            await self.attempt_match()

    def stop(self):
        """Stop matchmaking loop."""
        self.running = False


# Global matchmaker instance
matchmaker = Matchmaker()


async def main():
    mm = Matchmaker()

    # Start matchmaking loop
    task_matchmaker = asyncio.create_task(mm.run())

    # Start player join simulation
    task_joins = asyncio.create_task(simulate_player_joins(mm))

    # Let simulation run for 30 seconds
    await asyncio.sleep(3000)

    # Stop everything
    mm.stop()
    await task_matchmaker
    task_joins.cancel()


if __name__ == "__main__":
    asyncio.run(main())