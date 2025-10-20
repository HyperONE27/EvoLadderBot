"""
Comprehensive test suite for discord_utils.

Tests flag emotes, race emotes, timestamp formatting, and other Discord utilities.
"""

import pytest
import time
from src.bot.utils.discord_utils import (
    get_flag_emote,
    get_race_emote,
    format_discord_timestamp,
    get_current_unix_timestamp,
)


class TestFlagEmotes:
    """Test flag emote generation"""
    
    def test_get_flag_emote_valid_countries(self):
        """Test flag emotes for valid country codes"""
        
        test_cases = [
            # (country_code, should_contain_emoji)
            ("US", True),
            ("CA", True),
            ("GB", True),
            ("FR", True),
            ("DE", True),
            ("JP", True),
            ("KR", True),
            ("CN", True),
            ("BR", True),
            ("AU", True),
            ("MX", True),
            ("ES", True),
            ("IT", True),
            ("RU", True),
            ("IN", True),
        ]
        
        for country_code, should_have_emoji in test_cases:
            result = get_flag_emote(country_code)
            assert result is not None, f"Flag emote for {country_code} should not be None"
            assert isinstance(result, str), f"Flag emote for {country_code} should be a string"
            if should_have_emoji:
                assert len(result) > 0, f"Flag emote for {country_code} should not be empty"
    
    def test_get_flag_emote_invalid_codes(self):
        """Test flag emotes for invalid/unknown country codes"""
        
        test_cases = [
            # (country_code, description)
            ("XX", "Unknown country"),
            ("ZZ", "Invalid code"),
            ("", "Empty string"),
            (None, "None value"),
            ("USA", "Three-letter code"),
            ("U", "Single letter"),
            ("12", "Numbers"),
            ("us", "Lowercase"),
        ]
        
        for country_code, description in test_cases:
            result = get_flag_emote(country_code)
            # Should return a default emote or handle gracefully
            assert result is not None, f"Should handle {description} gracefully"
            assert isinstance(result, str), f"Should return string for {description}"
    
    def test_get_flag_emote_consistency(self):
        """Test that flag emotes are consistent across multiple calls"""
        
        test_cases = ["US", "KR", "JP", "GB", "FR", "DE", "XX"]
        
        for country_code in test_cases:
            result1 = get_flag_emote(country_code)
            result2 = get_flag_emote(country_code)
            assert result1 == result2, \
                f"Flag emote for {country_code} should be consistent: {result1} != {result2}"


class TestRaceEmotes:
    """Test race emote generation"""
    
    def test_get_race_emote_brood_war(self):
        """Test race emotes for Brood War races"""
        
        test_cases = [
            # (race_code, description)
            ("bw_terran", "BW Terran"),
            ("bw_zerg", "BW Zerg"),
            ("bw_protoss", "BW Protoss"),
            ("bw_random", "BW Random"),
        ]
        
        for race_code, description in test_cases:
            result = get_race_emote(race_code)
            assert result is not None, f"Race emote for {description} should not be None"
            assert isinstance(result, str), f"Race emote for {description} should be a string"
            assert len(result) > 0, f"Race emote for {description} should not be empty"
    
    def test_get_race_emote_starcraft2(self):
        """Test race emotes for StarCraft II races"""
        
        test_cases = [
            # (race_code, description)
            ("sc2_terran", "SC2 Terran"),
            ("sc2_zerg", "SC2 Zerg"),
            ("sc2_protoss", "SC2 Protoss"),
            ("sc2_random", "SC2 Random"),
        ]
        
        for race_code, description in test_cases:
            result = get_race_emote(race_code)
            assert result is not None, f"Race emote for {description} should not be None"
            assert isinstance(result, str), f"Race emote for {description} should be a string"
            assert len(result) > 0, f"Race emote for {description} should not be empty"
    
    def test_get_race_emote_invalid_codes(self):
        """Test race emotes for invalid race codes"""
        
        test_cases = [
            # (race_code, description)
            ("invalid_race", "Invalid race"),
            ("", "Empty string"),
            (None, "None value"),
            ("terran", "Missing prefix"),
            ("BW_TERRAN", "Wrong case"),
            ("sc3_terran", "Wrong game"),
        ]
        
        for race_code, description in test_cases:
            result = get_race_emote(race_code)
            # Should return a default emote or handle gracefully
            assert result is not None, f"Should handle {description} gracefully"
            assert isinstance(result, str), f"Should return string for {description}"
    
    def test_get_race_emote_consistency(self):
        """Test that race emotes are consistent across multiple calls"""
        
        test_cases = [
            "bw_terran", "bw_zerg", "bw_protoss",
            "sc2_terran", "sc2_zerg", "sc2_protoss",
        ]
        
        for race_code in test_cases:
            result1 = get_race_emote(race_code)
            result2 = get_race_emote(race_code)
            assert result1 == result2, \
                f"Race emote for {race_code} should be consistent: {result1} != {result2}"


class TestTimestampFormatting:
    """Test Discord timestamp formatting"""
    
    def test_format_discord_timestamp_valid_timestamps(self):
        """Test formatting valid Unix timestamps"""
        
        current_time = int(time.time())
        
        test_cases = [
            # (unix_timestamp, description)
            (current_time, "Current time"),
            (current_time - 3600, "1 hour ago"),
            (current_time + 3600, "1 hour from now"),
            (0, "Unix epoch"),
            (1609459200, "Jan 1, 2021"),
            (1640995200, "Jan 1, 2022"),
            (1672531200, "Jan 1, 2023"),
        ]
        
        for unix_timestamp, description in test_cases:
            result = format_discord_timestamp(unix_timestamp)
            assert result is not None, f"Timestamp format for {description} should not be None"
            assert isinstance(result, str), f"Timestamp format for {description} should be a string"
            # Discord timestamp format: <t:TIMESTAMP:STYLE>
            assert result.startswith("<t:"), f"Timestamp for {description} should start with '<t:'"
            assert result.endswith(">"), f"Timestamp for {description} should end with '>'"
            assert str(unix_timestamp) in result, \
                f"Timestamp for {description} should contain the timestamp value"
    
    def test_format_discord_timestamp_edge_cases(self):
        """Test formatting edge case timestamps"""
        
        test_cases = [
            # (unix_timestamp, description)
            (0, "Zero timestamp"),
            (-1, "Negative timestamp"),
            (999999999999, "Very large timestamp"),
            (1, "Minimal positive timestamp"),
        ]
        
        for unix_timestamp, description in test_cases:
            result = format_discord_timestamp(unix_timestamp)
            # Should handle gracefully, even if the timestamp is invalid
            assert result is not None, f"Should handle {description} gracefully"
            assert isinstance(result, str), f"Should return string for {description}"
    
    def test_get_current_unix_timestamp(self):
        """Test getting current Unix timestamp"""
        
        # Get timestamp
        result = get_current_unix_timestamp()
        
        # Verify it's close to current time
        current_time = int(time.time())
        
        assert isinstance(result, int), "Timestamp should be an integer"
        assert abs(result - current_time) <= 1, \
            f"Timestamp should be close to current time: {result} vs {current_time}"
        assert result > 1600000000, "Timestamp should be reasonable (after 2020)"
        assert result < 2000000000, "Timestamp should be reasonable (before 2033)"
    
    def test_get_current_unix_timestamp_consistency(self):
        """Test that timestamps are monotonically increasing"""
        
        timestamps = []
        for _ in range(5):
            timestamps.append(get_current_unix_timestamp())
            time.sleep(0.1)
        
        # Each timestamp should be >= the previous one
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i-1], \
                f"Timestamps should be monotonic: {timestamps[i-1]} -> {timestamps[i]}"
    
    def test_format_discord_timestamp_styles(self):
        """Test different Discord timestamp formatting styles"""
        
        current_time = int(time.time())
        result = format_discord_timestamp(current_time)
        
        # Verify format contains a style indicator (like :R, :F, :D, etc.)
        # The exact style depends on implementation, but should have the format
        assert "<t:" in result, "Should have Discord timestamp format"
        assert ":" in result[3:], "Should have style separator"
        assert result.endswith(">"), "Should end with >"

