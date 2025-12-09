"""
Unit test to verify the faulty cache mechanism has been removed.

This test checks that:
1. The obsolete cache methods no longer exist in DataAccessService
2. The LeaderboardService no longer performs on-demand database reloads
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import inspect


def test_cache_removal():
    """Test that the faulty caching mechanism has been completely removed."""
    print("\n" + "="*80)
    print("TEST: Verify Faulty Cache Mechanism Removed")
    print("="*80)
    
    all_passed = True
    
    # Test 1: DataAccessService should not have cache methods
    print("\n[Test 1] Checking DataAccessService for removed cache methods...")
    from src.backend.services.data_access_service import DataAccessService
    
    removed_methods = [
        'invalidate_leaderboard_cache',
        'is_leaderboard_cache_valid',
        'mark_leaderboard_cache_valid'
    ]
    
    for method_name in removed_methods:
        if hasattr(DataAccessService, method_name):
            print(f"    X FAIL: Method '{method_name}' still exists in DataAccessService")
            all_passed = False
        else:
            print(f"    OK: Method '{method_name}' successfully removed")
    
    # Test 2: DataAccessService should not have _leaderboard_cache_is_valid attribute
    print("\n[Test 2] Checking DataAccessService instance for removed cache flag...")
    service = DataAccessService()
    
    if hasattr(service, '_leaderboard_cache_is_valid'):
        print(f"    X FAIL: Attribute '_leaderboard_cache_is_valid' still exists")
        all_passed = False
    else:
        print(f"    OK: Attribute '_leaderboard_cache_is_valid' successfully removed")
    
    # Test 3: LeaderboardService should not reload from database
    print("\n[Test 3] Checking LeaderboardService.get_leaderboard_data for database reload...")
    from src.backend.services.leaderboard_service import LeaderboardService
    
    # Get the source code of get_leaderboard_data
    source = inspect.getsource(LeaderboardService.get_leaderboard_data)
    
    # Check for the problematic patterns
    if 'is_leaderboard_cache_valid' in source:
        print(f"    X FAIL: get_leaderboard_data still calls is_leaderboard_cache_valid()")
        all_passed = False
    else:
        print(f"    OK: get_leaderboard_data does not call is_leaderboard_cache_valid()")
    
    if 'get_leaderboard_1v1' in source:
        print(f"    X FAIL: get_leaderboard_data still performs database reload")
        all_passed = False
    else:
        print(f"    OK: get_leaderboard_data does not perform database reload")
    
    if 'mark_leaderboard_cache_valid' in source:
        print(f"    X FAIL: get_leaderboard_data still calls mark_leaderboard_cache_valid()")
        all_passed = False
    else:
        print(f"    OK: get_leaderboard_data does not call mark_leaderboard_cache_valid()")
    
    # Test 4: Check that LeaderboardService uses DataAccessService directly
    print("\n[Test 4] Checking that LeaderboardService uses DataAccessService as single source...")
    
    if '_get_cached_leaderboard_dataframe' in source:
        print(f"    OK: get_leaderboard_data calls _get_cached_leaderboard_dataframe()")
    else:
        print(f"    X FAIL: get_leaderboard_data does not call _get_cached_leaderboard_dataframe()")
        all_passed = False
    
    # Test 5: Check db_reader_writer decorator
    print("\n[Test 5] Checking db_reader_writer decorator for removed cache calls...")
    from src.backend.db import db_reader_writer
    
    decorator_source = inspect.getsource(db_reader_writer.invalidate_leaderboard_on_mmr_change)
    
    if 'invalidate_leaderboard_cache()' in decorator_source and 'pass' not in decorator_source:
        print(f"    X FAIL: Decorator still calls invalidate_leaderboard_cache()")
        all_passed = False
    else:
        print(f"    OK: Decorator does not call invalidate_leaderboard_cache()")
    
    # Final result
    print("\n" + "="*80)
    if all_passed:
        print("ALL TESTS PASSED - Cache mechanism successfully removed")
        print("="*80)
        return True
    else:
        print("SOME TESTS FAILED - Cache mechanism not fully removed")
        print("="*80)
        return False


if __name__ == "__main__":
    try:
        success = test_cache_removal()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nTest failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

