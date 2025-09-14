import asyncio
from typing import List, Optional

class Player:
    def __init__(self, player_id: int, name: str):
        self.player_id = player_id
        self.name = name

    def __repr__(self):
        return f"Player({self.player_id}, {self.name})"


class Matchmaker:
    def __init__(self, players: Optional[List[Player]] = None):
        self.players: List[Player] = players or []
        self.running = False

    def add_player(self, player: Player):
        """Add a player to the matchmaking pool."""
        print(f"👤 {player.name} joined the pool.")
        self.players.append(player)

    def remove_player(self, player: Player):
        """Remove a player from the matchmaking pool."""
        self.players = [p for p in self.players if p.player_id != player.player_id]

    async def is_valid_match(self, p1: Player, p2: Player) -> bool:
        """Check if two players are a valid match (mock: always True)."""
        print(f"   🔍 Checking if {p1.name} vs {p2.name} is valid...")
        await asyncio.sleep(0.2)  # simulate some processing
        return True

    async def attempt_match(self):
        """Try to find and process all valid matches."""
        if len(self.players) < 2:
            print("⚠️  Not enough players to match.")
            return

        matched = []
        used = set()

        print("🎯 Attempting to match players...")

        for i, p1 in enumerate(self.players):
            if p1.player_id in used:
                continue
            for p2 in self.players[i + 1:]:
                if p2.player_id in used:
                    continue
                if await self.is_valid_match(p1, p2):
                    print(f"✅ Match found: {p1.name} vs {p2.name}")
                    matched.append((p1, p2))
                    used.add(p1.player_id)
                    used.add(p2.player_id)
                    break  # move on to next unmatched player

        for p1, p2 in matched:
            self.remove_player(p1)
            self.remove_player(p2)

        if not matched:
            print("❌ No valid matches this round.")

    async def run(self):
        """Continuously try to match players every 5 seconds."""
        self.running = True
        while self.running:
            print("\n⏳ Waiting 5 seconds before next matchmaking attempt...")
            await asyncio.sleep(5)
            print("⏰ 5 seconds passed, looking for matches...")
            await self.attempt_match()

    def stop(self):
        """Stop matchmaking loop."""
        self.running = False


# -----------------------------
# Simulation
# -----------------------------
async def simulate_player_joins(mm: Matchmaker):
    """Simulate players joining over time."""
    player_id = 1
    while mm.running:
        await asyncio.sleep(1)  # new player joins every 3 seconds
        new_player = Player(player_id, f"Player{player_id}")
        mm.add_player(new_player)
        player_id += 1


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