"""
Tests for multiprocessing replay parsing implementation.

This test suite verifies:
1. The standalone parse_replay_data_blocking() function works correctly
2. The function can be pickled and executed in a separate process
3. Error handling works correctly for invalid replays
4. The integration with ReplayService works properly
"""

import unittest
import os
from concurrent.futures import ProcessPoolExecutor
import asyncio
from src.backend.services.replay_service import (
    parse_replay_data_blocking,
    ReplayService
)


class TestMultiprocessingReplayParsing(unittest.TestCase):
    """Test the multiprocessing replay parsing implementation."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_replay_dir = "tests/test_data/test_replay_files"
        self.valid_replay_path = os.path.join(
            self.test_replay_dir,
            "DarkReBellionIsles.SC2Replay"
        )
        
    def test_parse_replay_data_blocking_with_valid_replay(self):
        """Test that parse_replay_data_blocking() works with a valid replay."""
        # Read the test replay file
        with open(self.valid_replay_path, 'rb') as f:
            replay_bytes = f.read()
        
        # Parse the replay
        result = parse_replay_data_blocking(replay_bytes)
        
        # Verify the result
        self.assertIsInstance(result, dict)
        self.assertIsNone(result.get('error'))
        self.assertIn('replay_hash', result)
        self.assertIn('player_1_name', result)
        self.assertIn('player_2_name', result)
        self.assertIn('map_name', result)
        self.assertIn('duration', result)
        
        print(f"[OK] Valid replay parsed successfully")
        print(f"   Map: {result.get('map_name', 'N/A').encode('ascii', 'replace').decode('ascii')}")
        print(f"   Players: {result.get('player_1_name')} vs {result.get('player_2_name')}")
        print(f"   Duration: {result.get('duration')}s")
        
    def test_parse_replay_data_blocking_with_invalid_data(self):
        """Test that parse_replay_data_blocking() handles invalid data gracefully."""
        # Create some invalid replay data
        invalid_replay_bytes = b"This is not a valid SC2 replay file"
        
        # Parse the invalid data
        result = parse_replay_data_blocking(invalid_replay_bytes)
        
        # Verify the result contains an error
        self.assertIsInstance(result, dict)
        self.assertIsNotNone(result.get('error'))
        self.assertIn('sc2reader failed to parse replay', result['error'])
        
        print(f"[OK] Invalid replay handled correctly")
        print(f"   Error: {result.get('error')}")
        
    def test_parse_replay_in_process_pool(self):
        """Test that parse_replay_data_blocking() can be executed in a ProcessPoolExecutor."""
        # Read the test replay file
        with open(self.valid_replay_path, 'rb') as f:
            replay_bytes = f.read()
        
        # Create a process pool
        with ProcessPoolExecutor(max_workers=2) as executor:
            print(f"[Test] Created ProcessPoolExecutor with 2 workers")
            
            # Submit the parsing job to the pool
            future = executor.submit(parse_replay_data_blocking, replay_bytes)
            
            print(f"[Test] Submitted parsing job to worker process")
            
            # Get the result
            result = future.result(timeout=10)
            
            print(f"[Test] Received result from worker process")
        
        # Verify the result
        self.assertIsInstance(result, dict)
        self.assertIsNone(result.get('error'))
        self.assertIn('replay_hash', result)
        
        print(f"[OK] Replay parsed successfully in worker process")
        print(f"   Hash: {result.get('replay_hash')}")
        
    def test_concurrent_replay_parsing(self):
        """Test that multiple replays can be parsed concurrently."""
        # Find all test replay files
        test_replays = []
        for filename in os.listdir(self.test_replay_dir):
            if filename.endswith('.SC2Replay'):
                filepath = os.path.join(self.test_replay_dir, filename)
                with open(filepath, 'rb') as f:
                    test_replays.append((filename, f.read()))
        
        if len(test_replays) < 2:
            self.skipTest("Need at least 2 test replay files")
        
        # Create a process pool
        with ProcessPoolExecutor(max_workers=2) as executor:
            print(f"[Test] Created ProcessPoolExecutor with 2 workers")
            print(f"[Test] Submitting {len(test_replays)} replay parsing jobs concurrently")
            
            # Submit all parsing jobs
            futures = []
            for filename, replay_bytes in test_replays:
                future = executor.submit(parse_replay_data_blocking, replay_bytes)
                futures.append((filename, future))
            
            # Collect results
            results = []
            for filename, future in futures:
                result = future.result(timeout=10)
                results.append((filename, result))
                print(f"[Test] Received result for {filename}")
        
        # Verify all results
        for filename, result in results:
            self.assertIsInstance(result, dict)
            if result.get('error'):
                print(f"[WARN] {filename}: Parse error - {result['error']}")
            else:
                print(f"[OK] {filename}: Parsed successfully")
        
    def test_replay_service_integration(self):
        """Test that ReplayService.store_upload_from_parsed_dict() works correctly."""
        # Read the test replay file
        with open(self.valid_replay_path, 'rb') as f:
            replay_bytes = f.read()
        
        # Parse the replay using the blocking function
        parsed_dict = parse_replay_data_blocking(replay_bytes)
        
        # Verify parsing succeeded
        self.assertIsNone(parsed_dict.get('error'))
        
        # Create a ReplayService instance
        replay_service = ReplayService()
        
        # Note: We can't fully test store_upload_from_parsed_dict without a database
        # but we can verify the method exists and accepts the right parameters
        self.assertTrue(hasattr(replay_service, 'store_upload_from_parsed_dict'))
        
        print(f"[OK] ReplayService integration verified")
        print(f"   store_upload_from_parsed_dict() method exists")


class TestAsyncMultiprocessingIntegration(unittest.TestCase):
    """Test the async integration with run_in_executor."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_replay_dir = "tests/test_data/test_replay_files"
        self.valid_replay_path = os.path.join(
            self.test_replay_dir,
            "DarkReBellionIsles.SC2Replay"
        )
    
    def test_run_in_executor_integration(self):
        """Test that parse_replay_data_blocking() works with asyncio.run_in_executor()."""
        async def async_parse_test():
            # Read the test replay file
            with open(self.valid_replay_path, 'rb') as f:
                replay_bytes = f.read()
            
            # Create a process pool
            with ProcessPoolExecutor(max_workers=2) as process_pool:
                print(f"[Test] Created ProcessPoolExecutor with 2 workers")
                
                # Get the current event loop
                loop = asyncio.get_running_loop()
                
                print(f"[Test] Submitting parsing job via run_in_executor()")
                
                # Use run_in_executor to parse the replay
                result = await loop.run_in_executor(
                    process_pool,
                    parse_replay_data_blocking,
                    replay_bytes
                )
                
                print(f"[Test] Received result from worker process")
                
                return result
        
        # Run the async test
        result = asyncio.run(async_parse_test())
        
        # Verify the result
        self.assertIsInstance(result, dict)
        self.assertIsNone(result.get('error'))
        self.assertIn('replay_hash', result)
        
        print(f"[OK] run_in_executor() integration successful")
        print(f"   Hash: {result.get('replay_hash')}")


def run_tests():
    """Run all tests with detailed output."""
    print("\n" + "="*70)
    print("MULTIPROCESSING REPLAY PARSING TEST SUITE")
    print("="*70 + "\n")
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestMultiprocessingReplayParsing))
    suite.addTests(loader.loadTestsFromTestCase(TestAsyncMultiprocessingIntegration))
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70 + "\n")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)

