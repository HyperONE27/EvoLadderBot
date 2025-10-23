"""
Test to verify DataAccessService singleton initialization is race-condition-free.

This test spawns multiple concurrent coroutines that all attempt to get the singleton
instance simultaneously and verifies that initialization happens exactly once.
"""

import asyncio
import pytest
from src.backend.services.data_access_service import DataAccessService


@pytest.mark.asyncio
async def test_singleton_concurrent_initialization():
    """
    Test that DataAccessService.get_instance() correctly handles concurrent access.
    
    This test verifies that:
    1. Multiple concurrent calls to get_instance() all return the same instance
    2. Initialization happens exactly once (not multiple times)
    3. No race conditions occur during initialization
    """
    # Reset singleton state for clean test
    DataAccessService._instance = None
    DataAccessService._initialized = False
    DataAccessService._lock = None
    
    # Track initialization attempts
    init_count = 0
    original_initialize = DataAccessService._initialize
    
    async def tracked_initialize(self):
        """Wrapper to track initialization calls - mocked to avoid DB dependency."""
        nonlocal init_count
        init_count += 1
        print(f"[Test] Initialization attempt #{init_count}")
        
        # Mock initialization without DB
        if DataAccessService._initialized:
            return
        
        # Simulate some async work
        await asyncio.sleep(0.01)
        
        # Set minimal required attributes
        self._db_reader = None
        self._db_writer = None
        self._players_df = None
        self._mmrs_df = None
        self._preferences_df = None
        self._matches_df = None
        self._replays_df = None
        self._shutdown_event = asyncio.Event()
        self._writer_task = None
        self._write_queue = asyncio.Queue()
        self._init_lock = asyncio.Lock()
        self._main_loop = asyncio.get_running_loop()
        self._write_queue_size_peak = 0
        self._total_writes_queued = 0
        self._total_writes_completed = 0
        
        DataAccessService._initialized = True
        print(f"[Test] Initialization #{init_count} completed")
    
    # Monkey-patch to track initialization
    DataAccessService._initialize = tracked_initialize
    
    try:
        # Spawn 10 concurrent coroutines that all try to get the instance
        print("[Test] Spawning 10 concurrent get_instance() calls...")
        tasks = [DataAccessService.get_instance() for _ in range(10)]
        instances = await asyncio.gather(*tasks)
        
        # Verify all instances are the same object
        first_instance = instances[0]
        for i, instance in enumerate(instances[1:], start=1):
            assert instance is first_instance, \
                f"Instance {i} is not the same as instance 0"
        
        # Verify initialization happened exactly once
        assert init_count == 1, \
            f"Initialization happened {init_count} times, expected 1"
        
        # Verify the instance is properly initialized
        assert DataAccessService._initialized is True
        
        print(f"[Test] SUCCESS: Singleton initialized exactly once across 10 concurrent calls")
        print(f"[Test] All 10 instances are the same object: {all(inst is first_instance for inst in instances)}")
        
    finally:
        # Restore original method
        DataAccessService._initialize = original_initialize
        
        # Reset state
        DataAccessService._instance = None
        DataAccessService._initialized = False
        DataAccessService._lock = None


@pytest.mark.asyncio
async def test_singleton_returns_same_instance():
    """Test that multiple calls to get_instance() return the same instance."""
    # Reset state
    DataAccessService._instance = None
    DataAccessService._initialized = False
    DataAccessService._lock = None
    
    # Mock _initialize to avoid DB dependency
    original_initialize = DataAccessService._initialize
    
    async def mock_initialize(self):
        if DataAccessService._initialized:
            return
        self._db_reader = None
        self._db_writer = None
        self._players_df = None
        self._mmrs_df = None
        self._preferences_df = None
        self._matches_df = None
        self._replays_df = None
        self._shutdown_event = asyncio.Event()
        self._writer_task = None
        self._write_queue = asyncio.Queue()
        self._init_lock = asyncio.Lock()
        self._main_loop = asyncio.get_running_loop()
        self._write_queue_size_peak = 0
        self._total_writes_queued = 0
        self._total_writes_completed = 0
        DataAccessService._initialized = True
    
    DataAccessService._initialize = mock_initialize
    
    try:
        # Get instance twice
        instance1 = await DataAccessService.get_instance()
        instance2 = await DataAccessService.get_instance()
        
        # Verify they're the same object
        assert instance1 is instance2
        print("[Test] SUCCESS: Multiple calls return same instance")
        
    finally:
        # Restore original
        DataAccessService._initialize = original_initialize
        
        # Reset state
        DataAccessService._instance = None
        DataAccessService._initialized = False
        DataAccessService._lock = None


if __name__ == "__main__":
    print("Running singleton race condition tests...")
    print("\nTest 1: Concurrent initialization")
    asyncio.run(test_singleton_concurrent_initialization())
    
    print("\nTest 2: Same instance returned")
    asyncio.run(test_singleton_returns_same_instance())
    
    print("\nAll tests passed!")

