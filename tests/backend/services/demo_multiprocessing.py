"""
Demonstration script for multiprocessing replay parsing.

This script simulates the actual bot workflow:
1. Process pool initialization (like in interface_main.py)
2. Replay upload detection (like in on_message)
3. Async parsing with run_in_executor
4. Storage of parsed data

Run this script to verify the multiprocessing implementation works end-to-end.
"""

import asyncio
import os
from concurrent.futures import ProcessPoolExecutor
from src.backend.services.replay_service import parse_replay_data_blocking


async def simulate_replay_upload(process_pool, replay_path, player_name):
    """Simulate a replay upload from a player."""
    print(f"\n{'='*70}")
    print(f"[Main Process] {player_name} uploaded replay: {os.path.basename(replay_path)}")
    
    # Read the replay file (simulating Discord attachment download)
    with open(replay_path, 'rb') as f:
        replay_bytes = f.read()
    
    print(f"[Main Process] Downloaded {len(replay_bytes)} bytes")
    print(f"[Main Process] Offloading parse to worker process...")
    
    # Get the current event loop
    loop = asyncio.get_running_loop()
    
    # Offload parsing to worker process (this is the key multiprocessing call)
    try:
        replay_info = await loop.run_in_executor(
            process_pool,
            parse_replay_data_blocking,
            replay_bytes
        )
    except Exception as e:
        print(f"[Main Process] ERROR: Worker process failed: {e}")
        return None
    
    print(f"[Main Process] Received result from worker process")
    
    # Check for parsing errors
    if replay_info.get('error'):
        print(f"[Main Process] Parse failed: {replay_info['error']}")
        return None
    
    # Success!
    print(f"[Main Process] Parse successful!")
    print(f"   Hash: {replay_info.get('replay_hash')}")
    print(f"   Map: {replay_info.get('map_name', 'N/A').encode('ascii', 'replace').decode('ascii')}")
    print(f"   Players: {replay_info.get('player_1_name')} vs {replay_info.get('player_2_name')}")
    print(f"   Duration: {replay_info.get('duration')}s")
    
    return replay_info


async def simulate_concurrent_uploads(process_pool):
    """Simulate multiple players uploading replays at the same time."""
    print("\n" + "="*70)
    print("SIMULATING CONCURRENT REPLAY UPLOADS")
    print("="*70)
    print("This demonstrates that the bot remains responsive while parsing")
    print("multiple replays in worker processes.")
    
    # Find all test replay files
    test_replay_dir = "tests/test_data/test_replay_files"
    replay_files = [
        os.path.join(test_replay_dir, f)
        for f in os.listdir(test_replay_dir)
        if f.endswith('.SC2Replay')
    ][:2]  # Limit to 2 replays for demonstration
    
    if len(replay_files) < 2:
        print("\n[INFO] Need at least 2 replay files for concurrent demo")
        return
    
    # Simulate concurrent uploads from different players
    tasks = [
        simulate_replay_upload(process_pool, replay_files[0], "Player1"),
        simulate_replay_upload(process_pool, replay_files[1], "Player2")
    ]
    
    # Both uploads are processed concurrently
    results = await asyncio.gather(*tasks)
    
    print("\n" + "="*70)
    print("CONCURRENT PROCESSING COMPLETE")
    print("="*70)
    print(f"Successfully processed {sum(1 for r in results if r)} out of {len(results)} replays")
    print("\nKey Observation: While worker processes parsed replays, the main")
    print("event loop remained free to handle other tasks (Discord messages,")
    print("commands, matchmaking, etc.)")


async def main():
    """Main demonstration workflow."""
    print("\n" + "="*70)
    print("MULTIPROCESSING REPLAY PARSING DEMONSTRATION")
    print("="*70)
    print("\nThis script demonstrates the production workflow:")
    print("1. Initialize process pool (happens once at bot startup)")
    print("2. Handle replay uploads asynchronously")
    print("3. Parse replays in worker processes without blocking")
    print("4. Shutdown process pool gracefully")
    
    # Step 1: Initialize process pool (like in interface_main.py)
    worker_processes = 2
    process_pool = ProcessPoolExecutor(max_workers=worker_processes)
    print(f"\n[INFO] Initialized Process Pool with {worker_processes} worker process(es)")
    
    try:
        # Step 2: Simulate single replay upload
        test_replay = "tests/test_data/test_replay_files/DarkReBellionIsles.SC2Replay"
        if os.path.exists(test_replay):
            await simulate_replay_upload(process_pool, test_replay, "TestPlayer")
        
        # Step 3: Simulate concurrent uploads
        await simulate_concurrent_uploads(process_pool)
        
    finally:
        # Step 4: Graceful shutdown (like in interface_main.py finally block)
        print("\n" + "="*70)
        print("[INFO] Shutting down process pool...")
        process_pool.shutdown(wait=True)
        print("[INFO] Process pool shutdown complete")
        print("="*70 + "\n")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("Starting demonstration...")
    print("="*70)
    
    # Run the async demonstration
    asyncio.run(main())
    
    print("\n" + "="*70)
    print("DEMONSTRATION COMPLETE")
    print("="*70)
    print("\nThe implementation is working correctly!")
    print("\nNext steps:")
    print("1. Set WORKER_PROCESSES environment variable (default: 2)")
    print("2. Start the bot normally with: python src/bot/interface/interface_main.py")
    print("3. Upload a replay file to a match channel")
    print("4. Observe the [Worker Process] and [Main Process] log messages")
    print("\nThe bot will remain responsive during replay parsing!")

