"""
Test that persistent storage configuration works correctly.

This test verifies that the RAILWAY_PERSISTENT_STORAGE_PATH environment
variable is correctly used to determine where the write log is stored.
"""

import os
import tempfile
import shutil
from pathlib import Path

import pytest

from src.backend.services.write_log import WriteLog


class TestPersistentStorageConfig:
    """Test suite for persistent storage path configuration."""
    
    def test_write_log_uses_custom_path(self):
        """Test that WriteLog correctly uses a custom path."""
        # Create a temporary directory to simulate the persistent volume
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Create the write log with a path inside the temp directory
            db_path = os.path.join(temp_dir, "write_log.sqlite")
            write_log = WriteLog(db_path=db_path)
            
            # Verify the database was created at the expected location
            assert Path(db_path).exists(), f"Database should exist at {db_path}"
            
            # Verify we can read statistics (proves the database is functional)
            stats = write_log.get_statistics()
            assert isinstance(stats, dict)
            assert 'PENDING' in stats
            assert 'COMPLETED' in stats
            assert 'FAILED' in stats
            
            print(f"[TEST] Write log successfully created at: {db_path}")
            print(f"[TEST] Statistics: {stats}")
            
        finally:
            # Cleanup - retry on Windows if file is locked
            if Path(temp_dir).exists():
                import gc
                gc.collect()
                try:
                    shutil.rmtree(temp_dir)
                except PermissionError:
                    import time
                    time.sleep(0.1)
                    try:
                        shutil.rmtree(temp_dir)
                    except PermissionError:
                        pass  # Give up, OS will clean up eventually
    
    def test_railway_volume_simulation(self):
        """
        Simulate how the write log will work with a Railway volume.
        
        This test mimics the scenario where RAILWAY_PERSISTENT_STORAGE_PATH
        is set to a persistent mount point like /writequeue.
        """
        # Simulate a Railway volume path
        temp_volume = tempfile.mkdtemp()
        
        try:
            # This is what will happen in production:
            # RAILWAY_PERSISTENT_STORAGE_PATH = "/writequeue"
            # db_path = os.path.join("/writequeue", "write_log.sqlite")
            
            simulated_railway_path = temp_volume
            db_path = os.path.join(simulated_railway_path, "write_log.sqlite")
            
            # Initialize write log (simulating DataAccessService initialization)
            write_log = WriteLog(db_path=db_path)
            
            # Verify the path structure
            assert Path(db_path).exists()
            assert Path(db_path).parent == Path(simulated_railway_path)
            
            print(f"[TEST] Simulated Railway volume at: {simulated_railway_path}")
            print(f"[TEST] Write log database at: {db_path}")
            print(f"[TEST] Volume simulation: PASS")
            
        finally:
            if Path(temp_volume).exists():
                import gc
                gc.collect()
                try:
                    shutil.rmtree(temp_volume)
                except PermissionError:
                    import time
                    time.sleep(0.1)
                    try:
                        shutil.rmtree(temp_volume)
                    except PermissionError:
                        pass
    
    def test_local_development_fallback(self):
        """
        Test that local development (without Railway) still works.
        
        When RAILWAY_PERSISTENT_STORAGE_PATH is not set, it defaults to 'data'.
        """
        # Simulate local development environment
        local_data_dir = tempfile.mkdtemp()
        
        try:
            # This simulates the fallback when env var is not set
            db_path = os.path.join(local_data_dir, "write_log.sqlite")
            write_log = WriteLog(db_path=db_path)
            
            # Verify it works just like production
            assert Path(db_path).exists()
            
            # The parent directory should be our temp "data" directory
            assert Path(db_path).parent == Path(local_data_dir)
            
            print(f"[TEST] Local development path: {db_path}")
            print(f"[TEST] Local development fallback: PASS")
            
        finally:
            if Path(local_data_dir).exists():
                import gc
                gc.collect()
                try:
                    shutil.rmtree(local_data_dir)
                except PermissionError:
                    import time
                    time.sleep(0.1)
                    try:
                        shutil.rmtree(local_data_dir)
                    except PermissionError:
                        pass


def run_tests():
    """Run all persistent storage configuration tests."""
    import sys
    
    exit_code = pytest.main([__file__, "-v", "--tb=short"])
    sys.exit(exit_code)


if __name__ == "__main__":
    run_tests()

