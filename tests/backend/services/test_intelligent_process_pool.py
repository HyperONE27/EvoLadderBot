#!/usr/bin/env python3
"""
Test the intelligent process pool health checking system.

This test verifies that the health checker uses appropriate timeouts
based on worker status and doesn't restart pools when workers are
legitimately busy.
"""

import asyncio
import time
from concurrent.futures import ProcessPoolExecutor

from src.backend.services.process_pool_health import ensure_process_pool_healthy, set_bot_instance


def slow_worker_task(duration: float) -> dict:
    """Simulate a slow worker task."""
    print(f"[Worker] Starting slow task (duration: {duration}s)")
    time.sleep(duration)
    print(f"[Worker] Slow task completed")
    return {"status": "completed", "duration": duration}


class MockBot:
    """Mock bot class for testing intelligent health checking."""
    
    def __init__(self):
        self.process_pool = ProcessPoolExecutor(max_workers=1)
        self.health_check_count = 0
        self._active_work_count = 0
        self._last_work_time = 0
    
    def _track_work_start(self):
        """Track that work is starting on the process pool."""
        self._active_work_count += 1
        self._last_work_time = time.time()
        print(f"[Mock Bot] Work started (active: {self._active_work_count})")
    
    def _track_work_end(self):
        """Track that work has completed on the process pool."""
        if self._active_work_count > 0:
            self._active_work_count -= 1
        print(f"[Mock Bot] Work completed (active: {self._active_work_count})")
    
    def _is_worker_busy(self) -> bool:
        """Check if workers are currently busy with legitimate work."""
        return self._active_work_count > 0
    
    def _get_work_age(self) -> float:
        """Get the age of the oldest active work in seconds."""
        if self._last_work_time == 0:
            return 0
        return time.time() - self._last_work_time
    
    async def _ensure_process_pool_healthy(self) -> bool:
        """Mock health check that simulates intelligent behavior."""
        self.health_check_count += 1
        
        # Simulate intelligent timeout logic
        if self._is_worker_busy():
            work_age = self._get_work_age()
            timeout = min(5.0 + (work_age * 0.1), 30.0)
            print(f"[Mock Bot] Health check #{self.health_check_count} - Workers busy (age: {work_age:.1f}s), timeout: {timeout:.1f}s")
            
            # If work is very old, simulate a crash
            if work_age > 60:
                print(f"[Mock Bot] Work too old ({work_age:.1f}s) - simulating crash")
                return False
        else:
            print(f"[Mock Bot] Health check #{self.health_check_count} - Workers idle")
        
        # Simulate healthy pool
        return True


async def test_idle_workers():
    """
    Test health check behavior with idle workers.
    """
    print("\n" + "="*60)
    print("TEST: Idle Workers")
    print("="*60 + "\n")
    
    bot = MockBot()
    set_bot_instance(bot)
    
    print("[Test] Testing health check with idle workers...")
    is_healthy = await ensure_process_pool_healthy()
    print(f"[Test] Health check result: {is_healthy}")
    print(f"[Test] Health check count: {bot.health_check_count}")
    
    if is_healthy and bot.health_check_count == 1:
        print("[PASS] Test PASSED: Health check worked correctly with idle workers")
    else:
        print("[FAIL] Test FAILED: Health check should have succeeded with idle workers")
    
    print("="*60 + "\n")


async def test_busy_workers():
    """
    Test health check behavior with busy workers.
    """
    print("\n" + "="*60)
    print("TEST: Busy Workers")
    print("="*60 + "\n")
    
    bot = MockBot()
    set_bot_instance(bot)
    
    # Start some work
    print("[Test] Starting work on process pool...")
    bot._track_work_start()
    
    # Wait a bit to simulate work in progress
    await asyncio.sleep(2)
    
    print("[Test] Testing health check with busy workers...")
    is_healthy = await ensure_process_pool_healthy()
    print(f"[Test] Health check result: {is_healthy}")
    print(f"[Test] Work age: {bot._get_work_age():.1f}s")
    
    # Complete the work
    bot._track_work_end()
    
    if is_healthy:
        print("[PASS] Test PASSED: Health check correctly handled busy workers")
    else:
        print("[FAIL] Test FAILED: Health check should have succeeded with busy workers")
    
    print("="*60 + "\n")


async def test_old_work():
    """
    Test health check behavior with very old work (simulating crashed workers).
    """
    print("\n" + "="*60)
    print("TEST: Old Work (Crashed Workers)")
    print("="*60 + "\n")
    
    bot = MockBot()
    set_bot_instance(bot)
    
    # Start work and simulate it being very old
    print("[Test] Starting work and simulating old age...")
    bot._track_work_start()
    
    # Manually set old work time to simulate crashed worker
    bot._last_work_time = time.time() - 120  # 2 minutes ago
    
    print("[Test] Testing health check with old work...")
    is_healthy = await ensure_process_pool_healthy()
    print(f"[Test] Health check result: {is_healthy}")
    print(f"[Test] Work age: {bot._get_work_age():.1f}s")
    
    if not is_healthy:
        print("[PASS] Test PASSED: Health check correctly detected crashed workers")
    else:
        print("[FAIL] Test FAILED: Health check should have detected crashed workers")
    
    print("="*60 + "\n")


async def test_concurrent_work():
    """
    Test health check behavior with multiple concurrent work items.
    """
    print("\n" + "="*60)
    print("TEST: Concurrent Work")
    print("="*60 + "\n")
    
    bot = MockBot()
    set_bot_instance(bot)
    
    # Start multiple work items
    print("[Test] Starting multiple work items...")
    bot._track_work_start()
    bot._track_work_start()
    bot._track_work_start()
    
    print(f"[Test] Active work count: {bot._active_work_count}")
    
    # Test health check
    print("[Test] Testing health check with multiple work items...")
    is_healthy = await ensure_process_pool_healthy()
    print(f"[Test] Health check result: {is_healthy}")
    
    # Complete all work
    bot._track_work_end()
    bot._track_work_end()
    bot._track_work_end()
    
    if is_healthy:
        print("[PASS] Test PASSED: Health check correctly handled multiple work items")
    else:
        print("[FAIL] Test FAILED: Health check should have succeeded with multiple work items")
    
    print("="*60 + "\n")


async def main():
    """Run all tests."""
    print("Intelligent Process Pool Health Check Tests")
    print("="*60)
    
    await test_idle_workers()
    await test_busy_workers()
    await test_old_work()
    await test_concurrent_work()
    
    print("All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
