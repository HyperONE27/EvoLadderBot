#!/usr/bin/env python3
"""
Test the event-driven process pool health checking system.

This test verifies that the process pool health checker only runs when needed,
not on a timer like the old system.
"""

import asyncio
import time
from concurrent.futures import ProcessPoolExecutor

from src.backend.services.process_pool_health import ensure_process_pool_healthy, set_bot_instance


class MockBot:
    """Mock bot class for testing."""
    
    def __init__(self):
        self.process_pool = ProcessPoolExecutor(max_workers=1)
        self.health_check_count = 0
    
    async def _ensure_process_pool_healthy(self) -> bool:
        """Mock health check that counts calls."""
        self.health_check_count += 1
        print(f"[Mock Bot] Health check called #{self.health_check_count}")
        
        # Simulate a healthy pool
        return True


async def test_event_driven_health_check():
    """
    Test that health checks only happen when explicitly requested.
    """
    print("\n" + "="*60)
    print("TEST: Event-Driven Process Pool Health Check")
    print("="*60 + "\n")
    
    # Create mock bot
    bot = MockBot()
    set_bot_instance(bot)
    
    print("[Test] Bot instance registered")
    print(f"[Test] Initial health check count: {bot.health_check_count}")
    
    # Wait for 5 seconds - no health checks should happen
    print("[Test] Waiting 5 seconds (no health checks should occur)...")
    await asyncio.sleep(5)
    print(f"[Test] Health check count after 5 seconds: {bot.health_check_count}")
    
    # Now explicitly request a health check
    print("[Test] Explicitly requesting health check...")
    is_healthy = await ensure_process_pool_healthy()
    print(f"[Test] Health check result: {is_healthy}")
    print(f"[Test] Health check count after explicit request: {bot.health_check_count}")
    
    # Request another health check
    print("[Test] Requesting another health check...")
    is_healthy = await ensure_process_pool_healthy()
    print(f"[Test] Health check result: {is_healthy}")
    print(f"[Test] Final health check count: {bot.health_check_count}")
    
    # Cleanup
    bot.process_pool.shutdown(wait=True)
    print("[Test] Process pool shutdown complete")
    
    # Verify we only got health checks when explicitly requested
    expected_calls = 2  # Two explicit calls
    if bot.health_check_count == expected_calls:
        print(f"[PASS] Test PASSED: Health checks only occurred when requested ({bot.health_check_count}/{expected_calls})")
    else:
        print(f"[FAIL] Test FAILED: Expected {expected_calls} health checks, got {bot.health_check_count}")
    
    print("="*60 + "\n")


async def test_no_bot_instance():
    """
    Test behavior when no bot instance is registered.
    """
    print("\n" + "="*60)
    print("TEST: No Bot Instance")
    print("="*60 + "\n")
    
    # Clear bot instance
    set_bot_instance(None)
    
    print("[Test] No bot instance registered")
    
    # Try to get health check
    is_healthy = await ensure_process_pool_healthy()
    print(f"[Test] Health check result with no bot: {is_healthy}")
    
    if not is_healthy:
        print("[PASS] Test PASSED: Health check correctly failed with no bot instance")
    else:
        print("[FAIL] Test FAILED: Health check should have failed with no bot instance")
    
    print("="*60 + "\n")


async def main():
    """Run all tests."""
    print("Event-Driven Process Pool Health Check Tests")
    print("="*60)
    
    await test_event_driven_health_check()
    await test_no_bot_instance()
    
    print("All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
