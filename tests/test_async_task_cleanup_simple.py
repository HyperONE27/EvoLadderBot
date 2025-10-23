"""
Simple test to verify async task cleanup in view-like objects.

This test demonstrates the task lifecycle management pattern used in
QueueSearchingView to prevent memory leaks from uncancelled tasks.
"""

import asyncio


class MockView:
    """Simplified view that mimics QueueSearchingView task management."""
    
    def __init__(self):
        self.is_active = True
        self.match_task = None
        self.status_task = None
        self._counter = 0
        
        # Start background tasks
        self.match_task = asyncio.create_task(self._listen_for_match())
        self.status_task = asyncio.create_task(self._status_updates())
    
    async def _listen_for_match(self):
        """Simulates listening for match notifications."""
        try:
            while self.is_active:
                await asyncio.sleep(0.1)
                self._counter += 1
        except asyncio.CancelledError:
            print("[MockView] match_task cancelled successfully")
            raise
    
    async def _status_updates(self):
        """Simulates periodic status updates."""
        try:
            while self.is_active:
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            print("[MockView] status_task cancelled successfully")
            raise
    
    async def on_timeout(self):
        """Handle timeout - must cancel all tasks."""
        print("[MockView] on_timeout called")
        self.is_active = False
        
        if self.match_task and not self.match_task.done():
            self.match_task.cancel()
        
        if self.status_task and not self.status_task.done():
            self.status_task.cancel()
    
    def deactivate(self):
        """Synchronous deactivation - cancel all tasks."""
        print("[MockView] deactivate called")
        self.is_active = False
        
        if self.match_task and not self.match_task.done():
            self.match_task.cancel()
        
        if self.status_task and not self.status_task.done():
            self.status_task.cancel()


async def test_on_timeout_cancels_tasks():
    """Test that on_timeout properly cancels background tasks."""
    print("\n[Test 1] Testing on_timeout cancels tasks...")
    
    tasks_before = set(asyncio.all_tasks())
    
    # Create view
    view = MockView()
    await asyncio.sleep(0.05)  # Let tasks start
    
    # Verify tasks are running
    assert view.match_task is not None
    assert view.status_task is not None
    assert not view.match_task.done()
    assert not view.status_task.done()
    print("[Test 1] Tasks created and running")
    
    # Call on_timeout
    await view.on_timeout()
    await asyncio.sleep(0.01)  # Give cancellation time to process
    
    # Verify tasks were cancelled
    assert view.match_task.cancelled() or view.match_task.done()
    assert view.status_task.cancelled() or view.status_task.done()
    print("[Test 1] Tasks cancelled after on_timeout")
    
    # Verify no leaked tasks
    tasks_after = set(asyncio.all_tasks())
    new_tasks = {t for t in (tasks_after - tasks_before) if not t.done()}
    assert len(new_tasks) == 0, f"Found {len(new_tasks)} leaked tasks"
    
    print("[Test 1] PASS: on_timeout cancels all tasks, no leaks\n")


async def test_deactivate_cancels_tasks():
    """Test that deactivate properly cancels background tasks."""
    print("[Test 2] Testing deactivate cancels tasks...")
    
    tasks_before = set(asyncio.all_tasks())
    
    # Create view
    view = MockView()
    await asyncio.sleep(0.05)
    
    # Verify tasks running
    assert not view.match_task.done()
    assert not view.status_task.done()
    print("[Test 2] Tasks created and running")
    
    # Call deactivate
    view.deactivate()
    await asyncio.sleep(0.01)
    
    # Verify tasks cancelled
    assert view.match_task.cancelled() or view.match_task.done()
    assert view.status_task.cancelled() or view.status_task.done()
    print("[Test 2] Tasks cancelled after deactivate")
    
    # Verify no leaked tasks
    tasks_after = set(asyncio.all_tasks())
    new_tasks = {t for t in (tasks_after - tasks_before) if not t.done()}
    assert len(new_tasks) == 0
    
    print("[Test 2] PASS: deactivate cancels all tasks, no leaks\n")


async def test_multiple_views_no_leaks():
    """Test that creating and destroying multiple views doesn't leak tasks."""
    print("[Test 3] Testing multiple view lifecycles...")
    
    tasks_before = set(asyncio.all_tasks())
    
    # Create and destroy 10 views
    for i in range(10):
        view = MockView()
        await asyncio.sleep(0.01)
        view.deactivate()
        await asyncio.sleep(0.01)
    
    # Verify no leaked tasks
    tasks_after = set(asyncio.all_tasks())
    new_tasks = {t for t in (tasks_after - tasks_before) if not t.done()}
    assert len(new_tasks) == 0, f"Found {len(new_tasks)} leaked tasks after 10 views"
    
    print(f"[Test 3] PASS: 10 view lifecycles, no task leaks\n")


async def test_task_cleanup_under_exception():
    """Test that tasks are cleaned up even when exceptions occur."""
    print("[Test 4] Testing task cleanup with exceptions...")
    
    class ExceptionView(MockView):
        async def _listen_for_match(self):
            try:
                await asyncio.sleep(0.02)
                raise ValueError("Simulated error")
            except asyncio.CancelledError:
                print("[ExceptionView] match_task cancelled during exception handling")
                raise
    
    tasks_before = set(asyncio.all_tasks())
    
    # Create view that will encounter an exception
    view = ExceptionView()
    await asyncio.sleep(0.05)
    
    # Task should have failed
    assert view.match_task.done()
    print("[Test 4] match_task completed (with exception)")
    
    # Clean up remaining task
    view.deactivate()
    await asyncio.sleep(0.01)
    
    # Verify no leaked tasks
    tasks_after = set(asyncio.all_tasks())
    new_tasks = {t for t in (tasks_after - tasks_before) if not t.done()}
    assert len(new_tasks) == 0
    
    print("[Test 4] PASS: Tasks cleaned up even with exceptions\n")


async def run_all_tests():
    """Run all tests sequentially."""
    print("="*80)
    print("Async Task Cleanup Tests")
    print("="*80)
    
    await test_on_timeout_cancels_tasks()
    await test_deactivate_cancels_tasks()
    await test_multiple_views_no_leaks()
    await test_task_cleanup_under_exception()
    
    print("="*80)
    print("All async task cleanup tests PASSED!")
    print("\nPattern Summary:")
    print("  - Always store task references (self.task = asyncio.create_task(...))")
    print("  - Always cancel tasks in cleanup methods (task.cancel())")
    print("  - Use is_active flag to stop task loops gracefully")
    print("  - Implement both async (on_timeout) and sync (deactivate) cleanup")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(run_all_tests())

