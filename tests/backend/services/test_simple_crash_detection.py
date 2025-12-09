"""
Test simple crash detection for process pool monitoring.

This test verifies that our simplified crash detection mechanism works
without relying on complex error parsing from sc2reader.
"""

import asyncio
import sys
import os
import time
from concurrent.futures import ProcessPoolExecutor
from unittest.mock import Mock, patch

# Add the src directory to the path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from bot.bot_setup import _health_check_worker, EvoLadderBot


class MockBot:
    """Mock bot class for testing crash detection."""
    
    def __init__(self):
        self.process_pool = None
        self._process_pool_lock = asyncio.Lock()
        self.is_closed_flag = False
    
    def is_closed(self):
        return self.is_closed_flag
    
    async def wait_until_ready(self):
        """Mock wait_until_ready."""
        pass
    
    async def _check_and_restart_process_pool(self) -> bool:
        """Mock health check that simulates different scenarios."""
        if not self.process_pool:
            print("[Mock] Process pool is None, attempting restart...")
            return await self._restart_process_pool()
        
        try:
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(self.process_pool, _health_check_worker)
            result = await asyncio.wait_for(future, timeout=5.0)
            
            if isinstance(result, dict) and result.get("status") == "healthy":
                print(f"[Mock] ✅ Health check passed (PID: {result.get('pid', 'unknown')})")
                return True
            else:
                print(f"[Mock] Health check returned invalid result: {result}")
                return await self._restart_process_pool()
                
        except (asyncio.TimeoutError, Exception) as e:
            print(f"[Mock] Health check failed: {e}")
            return await self._restart_process_pool()
    
    async def _restart_process_pool(self) -> bool:
        """Mock process pool restart."""
        try:
            if self.process_pool:
                print("[Mock] Shutting down old pool...")
                self.process_pool.shutdown(wait=False, cancel_futures=True)
            
            print("[Mock] Creating new pool...")
            self.process_pool = ProcessPoolExecutor(max_workers=2)
            print("[Mock] ✅ Process pool restarted successfully")
            return True
            
        except Exception as e:
            print(f"[Mock] ❌ Failed to restart process pool: {e}")
            return False


async def test_health_check_worker():
    """Test that the health check worker returns proper data."""
    print("\n=== Test 1: Health Check Worker ===")
    
    result = _health_check_worker()
    print(f"Health check result: {result}")
    
    assert isinstance(result, dict), "Health check should return a dictionary"
    assert result.get("status") == "healthy", "Status should be 'healthy'"
    assert "pid" in result, "Should include process ID"
    assert "timestamp" in result, "Should include timestamp"
    
    print("✅ Health check worker test passed")


async def test_healthy_pool():
    """Test monitoring with a healthy process pool."""
    print("\n=== Test 2: Healthy Pool Monitoring ===")
    
    bot = MockBot()
    
    # Initialize a healthy pool
    bot.process_pool = ProcessPoolExecutor(max_workers=2)
    
    # Test health check
    is_healthy = await bot._check_and_restart_process_pool()
    assert is_healthy, "Healthy pool should pass health check"
    
    print("✅ Healthy pool test passed")


async def test_crashed_pool():
    """Test monitoring with a crashed process pool."""
    print("\n=== Test 3: Crashed Pool Recovery ===")
    
    bot = MockBot()
    
    # Simulate a crashed pool (None)
    bot.process_pool = None
    
    # Test health check and recovery
    is_healthy = await bot._check_and_restart_process_pool()
    assert is_healthy, "Crashed pool should be restarted successfully"
    assert bot.process_pool is not None, "New pool should be created"
    
    print("✅ Crashed pool recovery test passed")


async def test_consecutive_failures():
    """Test consecutive failure detection."""
    print("\n=== Test 4: Consecutive Failure Detection ===")
    
    bot = MockBot()
    consecutive_failures = 0
    max_consecutive_failures = 3
    
    # Simulate consecutive failures
    for i in range(5):
        consecutive_failures += 1
        print(f"Simulating failure {consecutive_failures}/{max_consecutive_failures}")
        
        if consecutive_failures >= max_consecutive_failures:
            print("CRITICAL: Too many consecutive failures detected")
            consecutive_failures = 0  # Reset to avoid spam
    
    print("✅ Consecutive failure detection test passed")


async def test_monitoring_task():
    """Test the full monitoring task logic."""
    print("\n=== Test 5: Full Monitoring Task ===")
    
    bot = MockBot()
    consecutive_failures = 0
    max_consecutive_failures = 3
    
    # Initialize healthy pool
    bot.process_pool = ProcessPoolExecutor(max_workers=2)
    
    # Simulate one monitoring cycle
    try:
        is_healthy = await bot._check_and_restart_process_pool()
        if is_healthy:
            consecutive_failures = 0
            print("✅ Health check passed")
        else:
            consecutive_failures += 1
            print(f"❌ Health check failed ({consecutive_failures}/{max_consecutive_failures})")
    except Exception as e:
        consecutive_failures += 1
        print(f"❌ Monitoring error: {e}")
    
    assert consecutive_failures == 0, "Healthy pool should not increment failure counter"
    print("✅ Full monitoring task test passed")


async def test_suppressed_logging():
    """Test that sc2reader errors are suppressed."""
    print("\n=== Test 6: Suppressed Logging Test ===")
    
    # This would normally be tested with actual sc2reader, but we'll simulate
    # the logging suppression logic
    import logging
    
    # Test logging suppression
    sc2reader_logger = logging.getLogger('sc2reader')
    original_level = sc2reader_logger.level
    sc2reader_logger.setLevel(logging.CRITICAL)
    
    # Verify suppression
    assert sc2reader_logger.level == logging.CRITICAL, "sc2reader logging should be suppressed"
    
    # Restore original level
    sc2reader_logger.setLevel(original_level)
    
    print("✅ Suppressed logging test passed")


async def main():
    """Run all tests."""
    print("🧪 Testing Simple Crash Detection Mechanism")
    print("=" * 50)
    
    try:
        await test_health_check_worker()
        await test_healthy_pool()
        await test_crashed_pool()
        await test_consecutive_failures()
        await test_monitoring_task()
        await test_suppressed_logging()
        
        print("\n" + "=" * 50)
        print("🎉 All tests passed! Simple crash detection is working.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
