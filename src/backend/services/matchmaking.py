import asyncio
import uuid as uuid_lib
from typing import List, Optional, Set
from datetime import datetime


class Player:
    def __init__(self, uuid: str, elo: int):
        self.uuid = uuid
        self.ELO = elo
    
    def __repr__(self):
        return f"Player(uuid='{self.uuid}', ELO={self.ELO})"
    
    def __eq__(self, other):
        if isinstance(other, Player):
            return self.uuid == other.uuid
        return False
    
    def __hash__(self):
        return hash(self.uuid)


class Matchmaker:
    def __init__(self):
        self.queue: List[Player] = []
        self.queue_lock = asyncio.Lock()
        self.running = False
        self.matchmaking_task: Optional[asyncio.Task] = None
    
    async def add_player(self, player: Player):
        """Add a player to the matchmaking queue."""
        async with self.queue_lock:
            if player not in self.queue:
                self.queue.append(player)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Added {player} to queue. Queue size: {len(self.queue)}")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {player} already in queue")
    
    async def remove_player(self, player: Player):
        """Remove a player from the matchmaking queue."""
        async with self.queue_lock:
            if player in self.queue:
                self.queue.remove(player)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Removed {player} from queue. Queue size: {len(self.queue)}")
                return True
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {player} not found in queue")
                return False
    
    async def _create_matches(self):
        """Create matches from players in the queue."""
        async with self.queue_lock:
            if len(self.queue) < 2:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Not enough players in queue for matchmaking (need 2, have {len(self.queue)})")
                return []
            
            matches = []
            # Simple pairing: take players in pairs from the queue
            while len(self.queue) >= 2:
                player1 = self.queue.pop(0)
                player2 = self.queue.pop(0)
                matches.append((player1, player2))
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Created match: {player1} vs {player2}")
            
            if self.queue:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {len(self.queue)} player(s) remaining in queue")
            
            return matches
    
    async def _matchmaking_loop(self):
        """Periodic matchmaking loop that runs every 15 seconds."""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Matchmaking loop started")
        
        while self.running:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Running matchmaking cycle...")
            matches = await self._create_matches()
            
            if matches:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Created {len(matches)} match(es) this cycle")
            
            # Wait 15 seconds before next cycle
            await asyncio.sleep(15)
    
    async def start(self):
        """Start the matchmaking service."""
        if not self.running:
            self.running = True
            self.matchmaking_task = asyncio.create_task(self._matchmaking_loop())
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Matchmaker started")
    
    async def stop(self):
        """Stop the matchmaking service."""
        if self.running:
            self.running = False
            if self.matchmaking_task:
                self.matchmaking_task.cancel()
                try:
                    await self.matchmaking_task
                except asyncio.CancelledError:
                    pass
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Matchmaker stopped")
    
    async def get_queue_status(self):
        """Get current queue status."""
        async with self.queue_lock:
            return list(self.queue)


async def demo():
    """Demonstration of the matchmaking system."""
    print("=== Matchmaking System Demo ===\n")
    
    # Create matchmaker instance
    matchmaker = Matchmaker()
    
    # Start the matchmaking service
    await matchmaker.start()
    
    # Simulate players joining over time
    async def simulate_players():
        # Add initial players
        players = [
            Player(str(uuid_lib.uuid4())[:8], 1500),
            Player(str(uuid_lib.uuid4())[:8], 1600),
        ]
        
        for player in players:
            await matchmaker.add_player(player)
            await asyncio.sleep(1)
        
        # Wait a bit
        await asyncio.sleep(5)
        
        # Add more players
        more_players = [
            Player(str(uuid_lib.uuid4())[:8], 1400),
            Player(str(uuid_lib.uuid4())[:8], 1700),
            Player(str(uuid_lib.uuid4())[:8], 1550),
        ]
        
        for player in more_players:
            await matchmaker.add_player(player)
            await asyncio.sleep(2)
        
        # Wait for first matchmaking cycle
        await asyncio.sleep(10)
        
        # Add one more player after matchmaking
        late_player = Player(str(uuid_lib.uuid4())[:8], 1800)
        await matchmaker.add_player(late_player)
        
        # Let one more cycle run
        await asyncio.sleep(17)
        
        # Add a couple more players
        final_players = [
            Player(str(uuid_lib.uuid4())[:8], 1650),
            Player(str(uuid_lib.uuid4())[:8], 1450),
        ]
        
        for player in final_players:
            await matchmaker.add_player(player)
            await asyncio.sleep(1)
    
    # Run the simulation
    await simulate_players()
    
    # Wait for final matchmaking
    await asyncio.sleep(20)
    
    # Stop the matchmaker
    await matchmaker.stop()
    
    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(demo())