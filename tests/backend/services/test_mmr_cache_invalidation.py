"""
Test suite for MMR cache invalidation system.

This test verifies that the foolproof MMR cache invalidation system works correctly
by ensuring that any MMR modification automatically triggers cache invalidation.
"""

import asyncio
import unittest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from src.backend.db.db_reader_writer import DatabaseWriter, invalidate_leaderboard_on_mmr_change
from src.backend.services.leaderboard_service import invalidate_leaderboard_cache


class TestMMRCacheInvalidation(unittest.TestCase):
    """Test the MMR cache invalidation system."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.db_writer = DatabaseWriter()
        self.cache_invalidated = False
        
    def mock_invalidate_cache(self):
        """Mock cache invalidation function."""
        self.cache_invalidated = True
        print("[Test] Cache invalidation triggered")
    
    def test_decorator_applied_to_mmr_methods(self):
        """Test that the decorator is applied to MMR methods."""
        # Check that the decorator is applied to create_or_update_mmr_1v1
        self.assertTrue(hasattr(self.db_writer.create_or_update_mmr_1v1, '__wrapped__'))
        
        # Check that the decorator is applied to update_mmr_after_match
        self.assertTrue(hasattr(self.db_writer.update_mmr_after_match, '__wrapped__'))
        
        # Check that the decorator is applied to update_match_mmr_change
        self.assertTrue(hasattr(self.db_writer.update_match_mmr_change, '__wrapped__'))
        
        print("[OK] All MMR methods have the cache invalidation decorator")
    
    @patch('src.backend.services.leaderboard_service.invalidate_leaderboard_cache')
    def test_create_or_update_mmr_triggers_invalidation(self, mock_invalidate):
        """Test that create_or_update_mmr_1v1 triggers cache invalidation."""
        # Mock the database adapter to return success
        with patch.object(self.db_writer.adapter, 'execute_write', return_value=True):
            result = self.db_writer.create_or_update_mmr_1v1(
                discord_uid=12345,
                player_name="TestPlayer",
                race="bw_terran",
                mmr=1500
            )
            
            # Verify the operation succeeded
            self.assertTrue(result)
            
            # Verify cache invalidation was called
            mock_invalidate.assert_called_once()
            print("[OK] create_or_update_mmr_1v1 triggers cache invalidation")
    
    @patch('src.backend.services.leaderboard_service.invalidate_leaderboard_cache')
    def test_update_mmr_after_match_triggers_invalidation(self, mock_invalidate):
        """Test that update_mmr_after_match triggers cache invalidation."""
        # Mock the database adapter methods
        with patch.object(self.db_writer.adapter, 'execute_query', return_value=[]), \
             patch.object(self.db_writer.adapter, 'execute_write', return_value=True):
            
            result = self.db_writer.update_mmr_after_match(
                discord_uid=12345,
                race="bw_terran",
                new_mmr=1600,
                won=True
            )
            
            # Verify the operation succeeded
            self.assertTrue(result)
            
            # Verify cache invalidation was called
            mock_invalidate.assert_called_once()
            print("[OK] update_mmr_after_match triggers cache invalidation")
    
    @patch('src.backend.services.leaderboard_service.invalidate_leaderboard_cache')
    def test_update_match_mmr_change_triggers_invalidation(self, mock_invalidate):
        """Test that update_match_mmr_change triggers cache invalidation."""
        # Mock the database adapter to return success
        with patch.object(self.db_writer.adapter, 'execute_write', return_value=True):
            result = self.db_writer.update_match_mmr_change(
                match_id=123,
                mmr_change=50
            )
            
            # Verify the operation succeeded
            self.assertTrue(result)
            
            # Verify cache invalidation was called
            mock_invalidate.assert_called_once()
            print("[OK] update_match_mmr_change triggers cache invalidation")
    
    @patch('src.backend.services.leaderboard_service.invalidate_leaderboard_cache')
    def test_failed_operations_dont_trigger_invalidation(self, mock_invalidate):
        """Test that failed operations don't trigger cache invalidation."""
        # Mock the database adapter to return failure
        with patch.object(self.db_writer.adapter, 'execute_write', return_value=False):
            result = self.db_writer.create_or_update_mmr_1v1(
                discord_uid=12345,
                player_name="TestPlayer",
                race="bw_terran",
                mmr=1500
            )
            
            # Verify the operation failed
            self.assertFalse(result)
            
            # Verify cache invalidation was NOT called
            mock_invalidate.assert_not_called()
            print("[OK] Failed operations don't trigger cache invalidation")
    
    def test_decorator_handles_import_errors_gracefully(self):
        """Test that the decorator handles import errors gracefully."""
        # Create a test function with the decorator
        @invalidate_leaderboard_on_mmr_change
        def test_function():
            return True
        
        # Mock the import to fail
        with patch('src.backend.services.leaderboard_service.invalidate_leaderboard_cache', 
                   side_effect=ImportError("Module not found")):
            # The decorator should handle the error gracefully
            result = test_function()
            self.assertTrue(result)
            print("[OK] Decorator handles import errors gracefully")
    
    def test_decorator_preserves_function_behavior(self):
        """Test that the decorator preserves the original function behavior."""
        # Create a test function with the decorator
        @invalidate_leaderboard_on_mmr_change
        def test_function(value):
            return value * 2
        
        # Test that the function still works correctly
        result = test_function(5)
        self.assertEqual(result, 10)
        print("[OK] Decorator preserves original function behavior")
    
    def test_decorator_handles_exceptions_in_cache_invalidation(self):
        """Test that exceptions in cache invalidation don't break the operation."""
        # Create a test function with the decorator
        @invalidate_leaderboard_on_mmr_change
        def test_function():
            return True
        
        # Mock cache invalidation to raise an exception
        with patch('src.backend.services.leaderboard_service.invalidate_leaderboard_cache', 
                   side_effect=Exception("Cache invalidation failed")):
            # The operation should still succeed despite the exception
            result = test_function()
            self.assertTrue(result)
            print("[OK] Decorator handles cache invalidation exceptions gracefully")


class TestMMRCacheInvalidationIntegration(unittest.TestCase):
    """Integration tests for MMR cache invalidation."""
    
    def setUp(self):
        """Set up integration test fixtures."""
        self.cache_invalidations = []
        
    def mock_invalidate_cache(self):
        """Track cache invalidations."""
        self.cache_invalidations.append("invalidated")
        print(f"[Integration Test] Cache invalidated (total: {len(self.cache_invalidations)})")
    
    @patch('src.backend.services.leaderboard_service.invalidate_leaderboard_cache')
    def test_multiple_mmr_operations_trigger_multiple_invalidations(self, mock_invalidate):
        """Test that multiple MMR operations trigger multiple cache invalidations."""
        db_writer = DatabaseWriter()
        
        # Mock database operations to succeed
        with patch.object(db_writer.adapter, 'execute_write', return_value=True), \
             patch.object(db_writer.adapter, 'execute_query', return_value=[]):
            
            # Perform multiple MMR operations
            db_writer.create_or_update_mmr_1v1(12345, "Player1", "bw_terran", 1500)
            db_writer.update_mmr_after_match(12345, "bw_terran", 1600, won=True)
            db_writer.update_match_mmr_change(123, 50)
            
            # Verify cache was invalidated for each operation
            self.assertEqual(mock_invalidate.call_count, 3)
            print("[OK] Multiple MMR operations trigger multiple cache invalidations")
    
    def test_cache_invalidation_function_exists(self):
        """Test that the cache invalidation function exists and is callable."""
        # Test that the function can be imported and called
        from src.backend.services.leaderboard_service import invalidate_leaderboard_cache
        
        # The function should be callable
        self.assertTrue(callable(invalidate_leaderboard_cache))
        
        # It should not raise an exception when called
        try:
            invalidate_leaderboard_cache()
            print("[OK] Cache invalidation function is callable")
        except Exception as e:
            self.fail(f"Cache invalidation function raised exception: {e}")


def run_mmr_cache_tests():
    """Run all MMR cache invalidation tests."""
    print("[TEST] Running MMR Cache Invalidation Tests...")
    print("=" * 50)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestMMRCacheInvalidation))
    suite.addTests(loader.loadTestsFromTestCase(TestMMRCacheInvalidationIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    if result.wasSuccessful():
        print("[SUCCESS] All MMR cache invalidation tests passed!")
        print(f"[STATS] Tests run: {result.testsRun}")
        print(f"[STATS] Failures: {len(result.failures)}")
        print(f"[STATS] Errors: {len(result.errors)}")
    else:
        print("[FAIL] Some MMR cache invalidation tests failed!")
        print(f"[STATS] Tests run: {result.testsRun}")
        print(f"[STATS] Failures: {len(result.failures)}")
        print(f"[STATS] Errors: {len(result.errors)}")
        
        # Print failure details
        for test, traceback in result.failures:
            print(f"\n[FAILURE] {test}")
            print(traceback)
        
        for test, traceback in result.errors:
            print(f"\n[ERROR] {test}")
            print(traceback)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_mmr_cache_tests()
    exit(0 if success else 1)
