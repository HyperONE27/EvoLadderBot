"""
Stress test simulating 500 concurrent users accessing DataAccessService.

This test simulates real-world load patterns:
- Multiple users querying player data
- MMR lookups across different races
- Leaderboard queries with various filters
- Match history lookups
- Preferences queries
- Concurrent initialization attempts

NO DATABASE WRITES - Read-only stress test using mocked data.
"""

import asyncio
import random
import time
from typing import List, Dict, Any
from unittest.mock import MagicMock, AsyncMock
import polars as pl

from src.backend.services.data_access_service import DataAccessService


class StressTestHarness:
    """Harness for simulating concurrent user load on DataAccessService."""
    
    def __init__(self, num_users: int = 500):
        self.num_users = num_users
        self.results = {
            "total_operations": 0,
            "successful_operations": 0,
            "failed_operations": 0,
            "operation_times": [],
            "concurrent_instances": set(),
            "initialization_count": 0,
            "error_types": {}
        }
    
    def setup_mock_data(self) -> None:
        """Create realistic mock data for stress testing."""
        print("[Stress Test] Setting up mock data...")
        
        # Generate mock player data (500 players)
        player_ids = list(range(100000, 100000 + self.num_users))
        
        self.mock_players_df = pl.DataFrame({
            "discord_uid": player_ids,
            "discord_username": [f"Player{i}" for i in range(self.num_users)],
            "player_name": [f"IGN_{i}" for i in range(self.num_users)],
            "country": [random.choice(["US", "KR", "EU", "CN", "BR"]) for _ in range(self.num_users)],
            "remaining_aborts": [random.randint(0, 3) for _ in range(self.num_users)],
            "battletag": [None for _ in range(self.num_users)],
            "region": [None for _ in range(self.num_users)],
            "alt_player_name_1": [None for _ in range(self.num_users)],
            "alt_player_name_2": [None for _ in range(self.num_users)],
        })
        
        # Generate MMR data (each player has 1-3 races)
        mmr_entries = []
        races = ["bw_terran", "bw_zerg", "bw_protoss", "sc2_terran", "sc2_zerg", "sc2_protoss"]
        for player_id in player_ids:
            num_races = random.randint(1, 3)
            for race in random.sample(races, num_races):
                mmr_entries.append({
                    "discord_uid": player_id,
                    "race": race,
                    "mmr": random.randint(800, 2400),
                    "player_name": f"IGN_{player_id - 100000}",
                    "games_played": random.randint(0, 100),
                    "games_won": random.randint(0, 60),
                    "games_lost": random.randint(0, 60),
                    "games_drawn": random.randint(0, 5),
                })
        
        self.mock_mmrs_df = pl.DataFrame(mmr_entries)
        
        # Generate preferences data
        self.mock_preferences_df = pl.DataFrame({
            "discord_uid": player_ids[:250],  # Half the players have preferences
            "last_chosen_races": ['["bw_terran"]' for _ in range(250)],
            "last_chosen_vetoes": ['["lost_temple"]' for _ in range(250)],
        })
        
        # Generate match data
        match_entries = []
        for match_id in range(1000):
            p1, p2 = random.sample(player_ids, 2)
            match_entries.append({
                "id": match_id,
                "player_1_discord_uid": p1,
                "player_2_discord_uid": p2,
                "player_1_race": random.choice(races),
                "player_2_race": random.choice(races),
                "map_played": f"Map_{random.randint(1, 10)}",
                "server_choice": random.choice(["US", "EU", "KR"]),
                "player_1_mmr": random.randint(1000, 2000),
                "player_2_mmr": random.randint(1000, 2000),
                "mmr_change": random.uniform(-50, 50),
                "played_at": "2024-01-01 00:00:00",
                "player_1_report": random.choice([0, 1, None]),
                "player_2_report": random.choice([0, 1, None]),
                "match_result": random.choice([0, 1, -1, None]),
                "player_1_replay_path": None,
                "player_2_replay_path": None,
                "player_1_replay_time": None,
                "player_2_replay_time": None,
            })
        
        self.mock_matches_df = pl.DataFrame(match_entries)
        
        # Generate replay data
        self.mock_replays_df = pl.DataFrame({
            "id": list(range(500)),
            "replay_path": [f"/replays/replay_{i}.rep" for i in range(500)],
        })
        
        print(f"[Stress Test] Mock data created:")
        print(f"  - Players: {len(self.mock_players_df)}")
        print(f"  - MMR entries: {len(self.mock_mmrs_df)}")
        print(f"  - Preferences: {len(self.mock_preferences_df)}")
        print(f"  - Matches: {len(self.mock_matches_df)}")
        print(f"  - Replays: {len(self.mock_replays_df)}")
    
    async def mock_initialize(self, instance: DataAccessService) -> None:
        """Mock initialization that loads test data without DB calls."""
        if DataAccessService._initialized:
            return
        
        self.results["initialization_count"] += 1
        print(f"[Stress Test] Mock initialization #{self.results['initialization_count']}")
        
        # Simulate async initialization work
        await asyncio.sleep(0.01)
        
        # Set up mock attributes - must be set BEFORE checking _initialized again
        instance._db_reader = MagicMock()
        instance._db_writer = MagicMock()
        
        # Load our mock dataframes - create copies to avoid sharing mutable state
        instance._players_df = self.mock_players_df.clone()
        instance._mmrs_df = self.mock_mmrs_df.clone()
        instance._preferences_df = self.mock_preferences_df.clone()
        instance._matches_df = self.mock_matches_df.clone()
        instance._replays_df = self.mock_replays_df.clone()
        
        # Set up other required attributes
        instance._shutdown_event = asyncio.Event()
        instance._writer_task = None  # Don't start writer for stress test
        instance._write_queue = asyncio.Queue()
        instance._init_lock = asyncio.Lock()
        instance._main_loop = asyncio.get_running_loop()
        instance._write_queue_size_peak = 0
        instance._total_writes_queued = 0
        instance._total_writes_completed = 0
        
        DataAccessService._initialized = True
        print(f"[Stress Test] Mock initialization complete - DataFrames loaded")
    
    def record_error(self, error: Exception) -> None:
        """Record an error for statistics."""
        error_type = type(error).__name__
        self.results["error_types"][error_type] = self.results["error_types"].get(error_type, 0) + 1
        
        # Log first few errors for debugging
        if self.results["error_types"][error_type] <= 2:
            print(f"[Error Sample] {error_type}: {str(error)[:100]}")
    
    async def simulate_user_profile_lookup(self, user_id: int) -> Dict[str, Any]:
        """Simulate a user viewing their profile."""
        start = time.perf_counter()
        try:
            data_service = await DataAccessService.get_instance()
            self.results["concurrent_instances"].add(id(data_service))
            
            # Get player info
            player = data_service.get_player_info(user_id)
            
            # Get all MMRs
            mmrs = data_service.get_all_player_mmrs(user_id)
            
            # Get preferences
            prefs = data_service.get_player_preferences(user_id)
            
            self.results["successful_operations"] += 1
            elapsed = time.perf_counter() - start
            self.results["operation_times"].append(elapsed)
            return {"success": True, "time": elapsed}
        except Exception as e:
            self.results["failed_operations"] += 1
            self.record_error(e)
            return {"success": False, "error": str(e)}
        finally:
            self.results["total_operations"] += 1
    
    async def simulate_leaderboard_query(self, user_id: int) -> Dict[str, Any]:
        """Simulate a user viewing the leaderboard."""
        start = time.perf_counter()
        try:
            data_service = await DataAccessService.get_instance()
            self.results["concurrent_instances"].add(id(data_service))
            
            # Get leaderboard dataframe
            df = data_service.get_leaderboard_dataframe()
            
            # Simulate filtering (like real usage)
            if df is not None:
                # Filter by race
                race_filter = random.choice(["bw_terran", "bw_zerg", "sc2_terran", None])
                if race_filter:
                    df = df.filter(pl.col("race") == race_filter)
                
                # Sort and limit
                df = df.sort("mmr", descending=True).head(50)
            
            self.results["successful_operations"] += 1
            elapsed = time.perf_counter() - start
            self.results["operation_times"].append(elapsed)
            return {"success": True, "time": elapsed}
        except Exception as e:
            self.results["failed_operations"] += 1
            self.record_error(e)
            return {"success": False, "error": str(e)}
        finally:
            self.results["total_operations"] += 1
    
    async def simulate_mmr_lookup(self, user_id: int) -> Dict[str, Any]:
        """Simulate checking player MMR for matchmaking."""
        start = time.perf_counter()
        try:
            data_service = await DataAccessService.get_instance()
            self.results["concurrent_instances"].add(id(data_service))
            
            # Get MMR for specific race
            race = random.choice(["bw_terran", "bw_zerg", "bw_protoss"])
            mmr = data_service.get_player_mmr(user_id, race)
            
            # Get abort count
            aborts = data_service.get_remaining_aborts(user_id)
            
            self.results["successful_operations"] += 1
            elapsed = time.perf_counter() - start
            self.results["operation_times"].append(elapsed)
            return {"success": True, "time": elapsed}
        except Exception as e:
            self.results["failed_operations"] += 1
            self.record_error(e)
            return {"success": False, "error": str(e)}
        finally:
            self.results["total_operations"] += 1
    
    async def simulate_match_history_lookup(self, user_id: int) -> Dict[str, Any]:
        """Simulate viewing match history."""
        start = time.perf_counter()
        try:
            data_service = await DataAccessService.get_instance()
            self.results["concurrent_instances"].add(id(data_service))
            
            # Get recent matches
            matches = data_service.get_player_recent_matches(user_id, limit=20)
            
            self.results["successful_operations"] += 1
            elapsed = time.perf_counter() - start
            self.results["operation_times"].append(elapsed)
            return {"success": True, "time": elapsed}
        except Exception as e:
            self.results["failed_operations"] += 1
            self.record_error(e)
            return {"success": False, "error": str(e)}
        finally:
            self.results["total_operations"] += 1
    
    async def simulate_player_existence_check(self, user_id: int) -> Dict[str, Any]:
        """Simulate checking if player exists (guard checks)."""
        start = time.perf_counter()
        try:
            data_service = await DataAccessService.get_instance()
            self.results["concurrent_instances"].add(id(data_service))
            
            # Check existence
            exists = data_service.player_exists(user_id)
            
            self.results["successful_operations"] += 1
            elapsed = time.perf_counter() - start
            self.results["operation_times"].append(elapsed)
            return {"success": True, "time": elapsed}
        except Exception as e:
            self.results["failed_operations"] += 1
            self.record_error(e)
            return {"success": False, "error": str(e)}
        finally:
            self.results["total_operations"] += 1
    
    async def simulate_random_user_action(self, user_id: int) -> Dict[str, Any]:
        """Simulate a random user action (weighted by frequency)."""
        action = random.choices(
            [
                self.simulate_player_existence_check,
                self.simulate_mmr_lookup,
                self.simulate_user_profile_lookup,
                self.simulate_leaderboard_query,
                self.simulate_match_history_lookup,
            ],
            weights=[30, 25, 20, 15, 10],  # Weighted by real-world frequency
            k=1
        )[0]
        
        return await action(user_id)
    
    async def run_user_session(self, user_id: int) -> None:
        """Simulate a complete user session with multiple actions."""
        # Each user performs 3-7 actions
        num_actions = random.randint(3, 7)
        
        for _ in range(num_actions):
            await self.simulate_random_user_action(user_id)
            # Small random delay between actions (0-50ms)
            await asyncio.sleep(random.uniform(0, 0.05))
    
    async def run_stress_test(self) -> None:
        """Execute the full stress test."""
        print(f"\n{'='*80}")
        print(f"STRESS TEST: {self.num_users} Concurrent Users")
        print(f"{'='*80}\n")
        
        # Reset singleton for clean test
        DataAccessService._instance = None
        DataAccessService._initialized = False
        DataAccessService._lock = None
        
        # Set up mock data
        self.setup_mock_data()
        
        # Patch the _initialize method
        original_initialize = DataAccessService._initialize
        harness = self
        
        async def patched_initialize(instance):
            """Patched initialize that uses our mock."""
            await harness.mock_initialize(instance)
        
        DataAccessService._initialize = patched_initialize
        
        try:
            test_start = time.perf_counter()
            
            # Create user IDs
            user_ids = list(range(100000, 100000 + self.num_users))
            
            print(f"\n[Stress Test] Launching {self.num_users} concurrent user sessions...")
            print("[Stress Test] Each user will perform 3-7 random actions")
            print("[Stress Test] Simulating real-world usage patterns:\n")
            print("  - 30% - Existence checks (command guards)")
            print("  - 25% - MMR lookups (matchmaking)")
            print("  - 20% - Profile views")
            print("  - 15% - Leaderboard queries")
            print("  - 10% - Match history lookups\n")
            
            # Launch all user sessions concurrently
            tasks = [self.run_user_session(user_id) for user_id in user_ids]
            await asyncio.gather(*tasks)
            
            test_duration = time.perf_counter() - test_start
            
            # Calculate statistics
            self.print_results(test_duration)
            
        finally:
            # Restore original method
            DataAccessService._initialize = original_initialize
            
            # Reset state
            DataAccessService._instance = None
            DataAccessService._initialized = False
            DataAccessService._lock = None
    
    def print_results(self, duration: float) -> None:
        """Print comprehensive test results."""
        print(f"\n{'='*80}")
        print("STRESS TEST RESULTS")
        print(f"{'='*80}\n")
        
        print(f"Test Duration:          {duration:.3f} seconds")
        print(f"Concurrent Users:       {self.num_users}")
        print(f"Unique Instances:       {len(self.results['concurrent_instances'])} (expected: 1)")
        print(f"Initialization Count:   {self.results['initialization_count']} (expected: 1)")
        
        print(f"\nOperations:")
        print(f"  Total:                {self.results['total_operations']}")
        print(f"  Successful:           {self.results['successful_operations']}")
        print(f"  Failed:               {self.results['failed_operations']}")
        print(f"  Success Rate:         {(self.results['successful_operations']/self.results['total_operations']*100):.2f}%")
        
        if self.results['operation_times']:
            times = self.results['operation_times']
            times.sort()
            
            print(f"\nPerformance Metrics:")
            print(f"  Operations/sec:       {self.results['total_operations']/duration:.2f}")
            print(f"  Avg Response Time:    {sum(times)/len(times)*1000:.3f}ms")
            print(f"  Min Response Time:    {min(times)*1000:.3f}ms")
            print(f"  Max Response Time:    {max(times)*1000:.3f}ms")
            print(f"  Median (p50):         {times[len(times)//2]*1000:.3f}ms")
            print(f"  p95:                  {times[int(len(times)*0.95)]*1000:.3f}ms")
            print(f"  p99:                  {times[int(len(times)*0.99)]*1000:.3f}ms")
        
        print(f"\nConcurrency Validation:")
        if len(self.results['concurrent_instances']) == 1:
            print(f"  [PASS] All operations used the same singleton instance")
        else:
            print(f"  [FAIL] Multiple instances detected: {len(self.results['concurrent_instances'])}")
        
        if self.results['initialization_count'] == 1:
            print(f"  [PASS] Singleton initialized exactly once")
        else:
            print(f"  [FAIL] Initialization happened {self.results['initialization_count']} times")
        
        if self.results['failed_operations'] == 0:
            print(f"  [PASS] No failed operations")
        else:
            print(f"  [WARN] {self.results['failed_operations']} operations failed")
        
        if self.results['error_types']:
            print(f"\nError Breakdown:")
            for error_type, count in sorted(self.results['error_types'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {error_type}: {count} occurrences")
        
        print(f"\n{'='*80}")
        
        # Overall assessment
        if (len(self.results['concurrent_instances']) == 1 and 
            self.results['initialization_count'] == 1 and
            self.results['failed_operations'] == 0):
            print("OVERALL: [PASS] Stress test completed successfully!")
        else:
            print("OVERALL: [FAIL] Issues detected during stress test")
        
        print(f"{'='*80}\n")


async def run_stress_test(num_users: int = 500):
    """Run the stress test with specified number of users."""
    harness = StressTestHarness(num_users=num_users)
    await harness.run_stress_test()


if __name__ == "__main__":
    print("\nStarting DataAccessService Stress Test...")
    print("This will simulate 500 concurrent users hitting the service.")
    print("No actual database writes will be performed.\n")
    
    asyncio.run(run_stress_test(num_users=500))
    
    print("\nStress test complete!")

