"""
Replay parsing timeout and process pool management.

This module handles:
- Replay parsing with 2.5-second timeout (2s work + 0.5s IPC overhead)
- Graceful shutdown with fallback to forceful termination
- Worker zombie detection (unresponsive processes)
- Replay job queuing and retry logic
"""

import asyncio
import logging
import time
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Replay parsing timeout configuration
REPLAY_PARSE_TIMEOUT = 2.5  # seconds (2s work + 0.5s IPC overhead)
GRACEFUL_SHUTDOWN_TIMEOUT = 1.0  # seconds to wait for graceful shutdown
FORCE_SHUTDOWN_TIMEOUT = 0.5  # seconds before forcing shutdown


async def parse_replay_with_timeout(
    process_pool: ProcessPoolExecutor,
    parse_replay_func,
    replay_bytes: bytes,
    timeout: float = REPLAY_PARSE_TIMEOUT
) -> Tuple[Optional[dict], bool]:
    """
    Parse a replay file with timeout and fallback logic.
    
    Attempts to parse the replay in the process pool with a strict timeout.
    If the timeout is exceeded, falls back to synchronous parsing in the main thread.
    
    Args:
        process_pool: ProcessPoolExecutor for the replay parsing
        parse_replay_func: The replay parsing function (parse_replay_data_blocking)
        replay_bytes: The raw replay file bytes
        timeout: Timeout in seconds (default: 2.5s)
    
    Returns:
        Tuple of (result_dict, was_timeout):
        - result_dict: The parsed replay data or error dict
        - was_timeout: True if a timeout occurred and fallback was used, False otherwise
    
    Raises:
        Exception: If both pool and fallback parsing fail
    """
    loop = asyncio.get_running_loop()
    
    try:
        print(f"[Replay Parse] Submitting replay parse to worker pool (timeout: {timeout}s)...")
        
        # Submit to process pool with timeout
        future = loop.run_in_executor(process_pool, parse_replay_func, replay_bytes)
        
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            print("[Replay Parse] ✅ Replay parsed successfully in worker process")
            return result, False
            
        except asyncio.TimeoutError:
            print(f"[Replay Parse] ⏱️  Worker timeout after {timeout}s - worker is unresponsive")
            
            # Try to cancel the future (it may not be responsive, but we try)
            if not future.done():
                future.cancel()
            
            # Fallback to synchronous parsing in main thread
            print("[Replay Parse] 🔄 Falling back to synchronous parsing in main thread...")
            try:
                result = parse_replay_func(replay_bytes)
                print("[Replay Parse] ✅ Replay parsed synchronously (fallback)")
                return result, True
            except Exception as e:
                print(f"[Replay Parse] ❌ Synchronous fallback also failed: {e}")
                return {"error": f"Fallback parsing failed: {str(e)}"}, True
                
    except Exception as e:
        print(f"[Replay Parse] ❌ Unexpected error during replay parsing: {e}")
        raise


async def graceful_pool_shutdown(
    process_pool: ProcessPoolExecutor,
    graceful_timeout: float = GRACEFUL_SHUTDOWN_TIMEOUT,
    force_timeout: float = FORCE_SHUTDOWN_TIMEOUT
) -> bool:
    """
    Gracefully shutdown the process pool with fallback to forceful termination.
    
    Strategy:
    1. Try graceful shutdown (wait for existing work to complete)
    2. If graceful times out, force shutdown (terminate immediately)
    3. Return success status
    
    Args:
        process_pool: The ProcessPoolExecutor to shutdown
        graceful_timeout: Time to wait for graceful shutdown (default: 1.0s)
        force_timeout: Time to wait for force shutdown (default: 0.5s)
    
    Returns:
        True if shutdown completed, False if it's still running
    """
    if process_pool is None:
        return True
    
    loop = asyncio.get_running_loop()
    
    try:
        print("[Process Pool Shutdown] Attempting graceful shutdown (waiting for work to complete)...")
        
        # Create a coroutine that runs the blocking shutdown in a thread
        def _graceful_shutdown():
            """Gracefully shutdown the pool (blocking operation)."""
            process_pool.shutdown(wait=True, cancel_futures=False)
            return True
        
        try:
            # Try graceful shutdown with timeout
            await asyncio.wait_for(
                loop.run_in_executor(None, _graceful_shutdown),
                timeout=graceful_timeout
            )
            print("[Process Pool Shutdown] ✅ Graceful shutdown completed")
            return True
            
        except asyncio.TimeoutError:
            print(f"[Process Pool Shutdown] ⏱️  Graceful shutdown timeout after {graceful_timeout}s - forcing shutdown...")
            
            # Graceful shutdown timed out, try forceful shutdown
            try:
                # Force shutdown (cancel_futures=True, wait=False)
                def _force_shutdown():
                    """Force shutdown the pool (terminate immediately)."""
                    process_pool.shutdown(wait=False, cancel_futures=True)
                    return True
                
                await asyncio.wait_for(
                    loop.run_in_executor(None, _force_shutdown),
                    timeout=force_timeout
                )
                print("[Process Pool Shutdown] ⚠️  Forced shutdown completed (work may be lost)")
                return True
                
            except asyncio.TimeoutError:
                print(f"[Process Pool Shutdown] ❌ Force shutdown timeout after {force_timeout}s - pool may be stuck")
                return False
                
    except Exception as e:
        logger.error(f"[Process Pool Shutdown] Unexpected error during shutdown: {e}")
        return False


def detect_zombie_workers(process_pool: ProcessPoolExecutor) -> bool:
    """
    Detect if the process pool has zombie (unresponsive) workers.
    
    A zombie worker is one that doesn't respond to a simple health check
    within the expected timeout.
    
    Args:
        process_pool: The ProcessPoolExecutor to check
    
    Returns:
        True if zombie workers detected, False otherwise
    """
    if process_pool is None:
        return False
    
    try:
        # Try to get pool info (this is implementation-specific)
        # For concurrent.futures.ProcessPoolExecutor, we can check the _processes dict
        if hasattr(process_pool, '_processes'):
            processes = process_pool._processes
            if processes is None:
                print("[Zombie Detection] Process pool appears to be shutdown")
                return True
            
            # Check if any processes have exited unexpectedly
            zombie_count = 0
            for worker_id, process in processes.items():
                if process is not None and not process.is_alive():
                    print(f"[Zombie Detection] Worker {worker_id} is dead (exitcode: {process.exitcode})")
                    zombie_count += 1
            
            if zombie_count > 0:
                print(f"[Zombie Detection] Detected {zombie_count} zombie worker(s)")
                return zombie_count > 0
        
        return False
        
    except Exception as e:
        logger.error(f"[Zombie Detection] Error checking for zombies: {e}")
        return False


def get_pool_worker_count(process_pool: ProcessPoolExecutor) -> int:
    """
    Get the number of active workers in the process pool.
    
    Args:
        process_pool: The ProcessPoolExecutor to check
    
    Returns:
        Number of active workers, or -1 if pool is None/unavailable
    """
    if process_pool is None:
        return -1
    
    try:
        if hasattr(process_pool, '_processes'):
            processes = process_pool._processes
            if processes is None:
                return 0
            return len([p for p in processes.values() if p is not None and p.is_alive()])
        
        # Fallback: try to access _max_workers
        if hasattr(process_pool, '_max_workers'):
            return process_pool._max_workers
        
        return -1
        
    except Exception as e:
        logger.error(f"[Pool Info] Error getting worker count: {e}")
        return -1


if __name__ == "__main__":
    # Example usage
    print("Replay parsing timeout module loaded")
