#!/usr/bin/env python3
"""
Test the memory monitoring system.

Verifies that memory tracking works correctly and reports are generated.
"""

import asyncio
import time

from src.backend.services.memory_monitor import initialize_memory_monitor, get_memory_monitor, log_memory


def allocate_memory(size_mb: int) -> list:
    """Allocate approximately size_mb megabytes of memory."""
    # Allocate list of integers (each int is ~28 bytes in Python)
    num_ints = (size_mb * 1024 * 1024) // 28
    return [i for i in range(num_ints)]


async def test_basic_memory_tracking():
    """Test basic memory tracking functionality."""
    print("\n" + "="*60)
    print("TEST: Basic Memory Tracking")
    print("="*60 + "\n")
    
    # Initialize monitor
    monitor = initialize_memory_monitor(enable_tracemalloc=True)
    
    print("[Test] Initial memory usage:")
    monitor.log_memory_usage("Initial")
    
    # Allocate some memory
    print("\n[Test] Allocating ~10 MB of memory...")
    data = allocate_memory(10)
    
    print("[Test] After allocation:")
    monitor.log_memory_usage("After 10 MB allocation")
    
    # Check delta
    delta = monitor.get_memory_delta()
    print(f"\n[Test] Memory delta from baseline: {delta:.2f} MB")
    
    # Free memory
    del data
    
    print("\n[Test] After freeing memory:")
    monitor.log_memory_usage("After freeing")
    
    if delta > 5:  # Should have allocated at least 5 MB
        print("[PASS] Test PASSED: Memory tracking detected allocation")
    else:
        print(f"[FAIL] Test FAILED: Expected delta > 5 MB, got {delta:.2f} MB")
    
    print("="*60 + "\n")


async def test_memory_report():
    """Test memory report generation."""
    print("\n" + "="*60)
    print("TEST: Memory Report Generation")
    print("="*60 + "\n")
    
    monitor = get_memory_monitor()
    if not monitor:
        print("[FAIL] Monitor not initialized")
        return
    
    # Generate report
    print("[Test] Generating memory report...\n")
    report = monitor.generate_report(include_allocations=True)
    print(report)
    
    if "MEMORY USAGE REPORT" in report:
        print("\n[PASS] Test PASSED: Memory report generated successfully")
    else:
        print("\n[FAIL] Test FAILED: Memory report missing expected content")
    
    print("="*60 + "\n")


async def test_garbage_collection():
    """Test garbage collection functionality."""
    print("\n" + "="*60)
    print("TEST: Garbage Collection")
    print("="*60 + "\n")
    
    monitor = get_memory_monitor()
    if not monitor:
        print("[FAIL] Monitor not initialized")
        return
    
    # Create some garbage
    print("[Test] Creating garbage objects...")
    garbage = []
    for i in range(1000):
        garbage.append([j for j in range(1000)])
    
    print("[Test] Memory before GC:")
    monitor.log_memory_usage("Before GC")
    
    # Delete references
    del garbage
    
    # Force GC
    print("\n[Test] Forcing garbage collection...")
    collected, freed = monitor.force_garbage_collection()
    
    print(f"[Test] GC collected {collected} objects, freed {freed:.2f} MB")
    
    print("\n[Test] Memory after GC:")
    monitor.log_memory_usage("After GC")
    
    if collected > 0:
        print("\n[PASS] Test PASSED: Garbage collection worked")
    else:
        print("\n[FAIL] Test FAILED: No objects collected")
    
    print("="*60 + "\n")


async def test_leak_detection():
    """Test memory leak detection."""
    print("\n" + "="*60)
    print("TEST: Memory Leak Detection")
    print("="*60 + "\n")
    
    monitor = get_memory_monitor()
    if not monitor:
        print("[FAIL] Monitor not initialized")
        return
    
    # Simulate a leak by allocating a lot of memory
    print("[Test] Simulating memory leak (allocating 60 MB)...")
    leak = allocate_memory(60)
    
    print("[Test] Checking for leak...")
    is_leak = monitor.check_memory_leak(threshold_mb=50.0)
    
    if is_leak:
        print("[PASS] Test PASSED: Memory leak detected")
    else:
        print("[FAIL] Test FAILED: Memory leak not detected")
    
    # Clean up
    del leak
    monitor.force_garbage_collection()
    
    print("="*60 + "\n")


async def test_periodic_monitoring():
    """Test periodic memory monitoring (simulated)."""
    print("\n" + "="*60)
    print("TEST: Periodic Monitoring")
    print("="*60 + "\n")
    
    monitor = get_memory_monitor()
    if not monitor:
        print("[FAIL] Monitor not initialized")
        return
    
    print("[Test] Simulating periodic monitoring checks...")
    
    for i in range(3):
        print(f"\n[Test] Check #{i+1}")
        log_memory(f"Periodic check {i+1}")
        await asyncio.sleep(1)
    
    print("\n[PASS] Test PASSED: Periodic monitoring completed")
    print("="*60 + "\n")


async def main():
    """Run all memory monitoring tests."""
    print("Memory Monitoring System Tests")
    print("="*60)
    
    await test_basic_memory_tracking()
    await test_memory_report()
    await test_garbage_collection()
    await test_leak_detection()
    await test_periodic_monitoring()
    
    print("All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
