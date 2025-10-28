"""
Test for in-game channel naming based on match ID.

This test validates that the channel naming follows the rule:
- Channel format: scevo##
- ## is based on the ones digit of match_id
- If ones digit is 0, use 10
- If ones digit is 1-9, use that digit (padded to 2 digits)
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.backend.services.matchmaking_service import matchmaker


def test_channel_naming_ones_digits_1_to_9():
    """Test channel names for match IDs ending in 1-9."""
    print("\n[TEST] Channel naming for ones digits 1-9...")
    
    test_cases = [
        (1, "scevo01"),
        (2, "scevo02"),
        (3, "scevo03"),
        (4, "scevo04"),
        (5, "scevo05"),
        (6, "scevo06"),
        (7, "scevo07"),
        (8, "scevo08"),
        (9, "scevo09"),
    ]
    
    for match_id, expected_channel in test_cases:
        actual_channel = matchmaker.generate_in_game_channel(match_id)
        assert actual_channel == expected_channel, \
            f"Match {match_id}: expected {expected_channel}, got {actual_channel}"
        print(f"  [OK] Match {match_id} -> {actual_channel}")
    
    print("[PASS] All ones digits 1-9 handled correctly")


def test_channel_naming_ends_with_zero():
    """Test channel names for match IDs ending in 0."""
    print("\n[TEST] Channel naming for ones digit 0...")
    
    test_cases = [
        (10, "scevo10"),
        (20, "scevo10"),
        (30, "scevo10"),
        (100, "scevo10"),
        (1000, "scevo10"),
    ]
    
    for match_id, expected_channel in test_cases:
        actual_channel = matchmaker.generate_in_game_channel(match_id)
        assert actual_channel == expected_channel, \
            f"Match {match_id}: expected {expected_channel}, got {actual_channel}"
        print(f"  [OK] Match {match_id} -> {actual_channel}")
    
    print("[PASS] All ends-in-zero cases handled correctly")


def test_channel_naming_cycling():
    """Test that channel names cycle correctly through all matches."""
    print("\n[TEST] Channel naming cycles correctly...")
    
    expected_cycle = [
        (1, "scevo01"),
        (2, "scevo02"),
        (3, "scevo03"),
        (4, "scevo04"),
        (5, "scevo05"),
        (6, "scevo06"),
        (7, "scevo07"),
        (8, "scevo08"),
        (9, "scevo09"),
        (10, "scevo10"),
        (11, "scevo01"),
        (12, "scevo02"),
        (20, "scevo10"),
        (21, "scevo01"),
    ]
    
    for match_id, expected_channel in expected_cycle:
        actual_channel = matchmaker.generate_in_game_channel(match_id)
        assert actual_channel == expected_channel, \
            f"Match {match_id}: expected {expected_channel}, got {actual_channel}"
    
    print(f"  [OK] Verified {len(expected_cycle)} matches cycle correctly")
    print("[PASS] Channel naming cycles correctly")


def test_channel_naming_format():
    """Test that all channel names follow the correct format."""
    print("\n[TEST] Channel naming format validation...")
    
    # Test a range of match IDs
    for match_id in range(1, 101):
        channel = matchmaker.generate_in_game_channel(match_id)
        
        # Check format
        assert channel.startswith("scevo"), f"Channel {channel} doesn't start with 'scevo'"
        assert len(channel) == 7, f"Channel {channel} should be exactly 7 characters (scevo##)"
        
        # Extract number
        channel_number = int(channel[5:])
        assert 1 <= channel_number <= 10, f"Channel number {channel_number} should be 1-10"
    
    print(f"  [OK] Verified format for 100 sequential match IDs")
    print("[PASS] All channel names follow correct format")


def test_deterministic_behavior():
    """Test that the function produces deterministic results."""
    print("\n[TEST] Deterministic behavior validation...")
    
    # Call the same match_id multiple times and verify results are identical
    test_cases = [1, 5, 10, 17, 23, 30, 99, 100]
    
    for match_id in test_cases:
        result1 = matchmaker.generate_in_game_channel(match_id)
        result2 = matchmaker.generate_in_game_channel(match_id)
        result3 = matchmaker.generate_in_game_channel(match_id)
        
        assert result1 == result2 == result3, \
            f"Non-deterministic results for match {match_id}: {result1}, {result2}, {result3}"
    
    print(f"  [OK] Verified deterministic behavior for {len(test_cases)} test cases")


if __name__ == "__main__":
    try:
        test_channel_naming_ones_digits_1_to_9()
        test_channel_naming_ends_with_zero()
        test_channel_naming_cycling()
        test_channel_naming_format()
        test_deterministic_behavior()
        
        print("\n" + "=" * 60)
        print("[SUCCESS] All in-game channel naming tests passed!")
        print("=" * 60)
        print("\nImplementation Summary:")
        print("[OK] Channel names follow scevo## format")
        print("[OK] Ones digits 1-9 map correctly")
        print("[OK] Ones digit 0 maps to 10")
        print("[OK] Channel names cycle correctly through matches")
        print("[OK] All channel names follow correct format")
        print("[OK] Function produces deterministic results")
        print("\nChannel naming is working correctly.")
    except AssertionError as e:
        print(f"\n[FAILED] {e}")
        sys.exit(1)
