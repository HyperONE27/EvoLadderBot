"""
Comprehensive test suite for CacheService (PlayerRecordCache and StaticDataCache).

Tests caching logic, TTL expiration, hit/miss rates, and cache invalidation.
"""

import pytest
import time
from src.backend.services.cache_service import PlayerRecordCache, static_cache


class TestPlayerRecordCache:
    """Comprehensive test suite for PlayerRecordCache"""
    
    @pytest.fixture
    def cache(self):
        """Fixture to provide a fresh cache instance with short TTL for testing"""
        return PlayerRecordCache(ttl_seconds=1)  # 1 second TTL for fast tests
    
    def test_cache_set_and_get(self, cache):
        """Test basic set and get operations"""
        
        test_cases = [
            # (discord_uid, player_record)
            (123456, {"discord_uid": 123456, "player_name": "Player1", "mmr": 1500}),
            (789012, {"discord_uid": 789012, "player_name": "Player2", "mmr": 1600}),
            (111111, {"discord_uid": 111111, "player_name": "Player3", "mmr": 1400}),
            (999999, {"discord_uid": 999999, "player_name": "Player4"}),
            (555555, {}),  # Empty record
        ]
        
        for discord_uid, player_record in test_cases:
            cache.set(discord_uid, player_record)
            result = cache.get(discord_uid)
            
            assert result is not None, f"Cache miss for {discord_uid} immediately after set"
            assert result == player_record, \
                f"Cache mismatch for {discord_uid}: expected {player_record}, got {result}"
            # Verify it's a copy, not the same object
            assert result is not player_record, f"Cache should return a copy, not the original object"
    
    def test_cache_miss(self, cache):
        """Test cache misses for non-existent keys"""
        
        test_cases = [
            # discord_uids that were never set
            123456,
            789012,
            999999,
            0,
            -1,
        ]
        
        for discord_uid in test_cases:
            result = cache.get(discord_uid)
            assert result is None, f"Expected cache miss for {discord_uid}, got {result}"
    
    def test_cache_ttl_expiration(self, cache):
        """Test that cache entries expire after TTL"""
        
        test_cases = [
            # (discord_uid, player_record)
            (123456, {"discord_uid": 123456, "player_name": "Player1"}),
            (789012, {"discord_uid": 789012, "player_name": "Player2"}),
        ]
        
        for discord_uid, player_record in test_cases:
            cache.set(discord_uid, player_record)
            
            # Should be in cache immediately
            result = cache.get(discord_uid)
            assert result is not None, f"Immediate cache miss for {discord_uid}"
            
            # Wait for TTL to expire (1 second + small buffer)
            time.sleep(1.1)
            
            # Should be expired now
            result = cache.get(discord_uid)
            assert result is None, f"Cache entry for {discord_uid} should have expired after TTL"
    
    def test_cache_invalidation(self, cache):
        """Test explicit cache invalidation"""
        
        test_cases = [
            # (discord_uid, player_record)
            (123456, {"discord_uid": 123456, "player_name": "Player1"}),
            (789012, {"discord_uid": 789012, "player_name": "Player2"}),
            (111111, {"discord_uid": 111111, "player_name": "Player3"}),
        ]
        
        # Set all test cases
        for discord_uid, player_record in test_cases:
            cache.set(discord_uid, player_record)
        
        # Verify all are cached
        for discord_uid, _ in test_cases:
            assert cache.get(discord_uid) is not None, f"Setup failed: {discord_uid} not cached"
        
        # Invalidate each one
        for discord_uid, _ in test_cases:
            cache.invalidate(discord_uid)
            result = cache.get(discord_uid)
            assert result is None, f"Cache entry for {discord_uid} should be invalidated"
    
    def test_cache_clear(self, cache):
        """Test clearing the entire cache"""
        
        test_cases = [
            (123456, {"discord_uid": 123456, "player_name": "Player1"}),
            (789012, {"discord_uid": 789012, "player_name": "Player2"}),
            (111111, {"discord_uid": 111111, "player_name": "Player3"}),
            (222222, {"discord_uid": 222222, "player_name": "Player4"}),
            (333333, {"discord_uid": 333333, "player_name": "Player5"}),
        ]
        
        # Set all test cases
        for discord_uid, player_record in test_cases:
            cache.set(discord_uid, player_record)
        
        # Verify all are cached
        for discord_uid, _ in test_cases:
            assert cache.get(discord_uid) is not None, f"Setup failed: {discord_uid} not cached"
        
        # Clear cache
        cache.clear()
        
        # Verify all are cleared
        for discord_uid, _ in test_cases:
            result = cache.get(discord_uid)
            assert result is None, f"Cache entry for {discord_uid} should be cleared"
    
    def test_cache_stats_tracking(self, cache):
        """Test that cache statistics are tracked correctly"""
        
        test_cases = [
            # (discord_uid, player_record, should_hit)
            (123456, {"discord_uid": 123456, "player_name": "Player1"}, False),  # First access = miss
            (123456, None, True),   # Second access = hit
            (123456, None, True),   # Third access = hit
            (789012, {"discord_uid": 789012, "player_name": "Player2"}, False),  # First access = miss
            (789012, None, True),   # Second access = hit
            (999999, None, False),  # Never set = miss
        ]
        
        expected_hits = 0
        expected_misses = 0
        
        for discord_uid, player_record, should_hit in test_cases:
            if player_record is not None:
                cache.set(discord_uid, player_record)
            
            result = cache.get(discord_uid)
            
            if should_hit:
                expected_hits += 1
                assert result is not None, f"Expected cache hit for {discord_uid}"
            else:
                expected_misses += 1
        
        stats = cache.get_stats()
        
        assert stats["hits"] == expected_hits, \
            f"Hit count mismatch: expected {expected_hits}, got {stats['hits']}"
        assert stats["misses"] == expected_misses, \
            f"Miss count mismatch: expected {expected_misses}, got {stats['misses']}"
        
        # Verify hit rate calculation
        total_requests = expected_hits + expected_misses
        expected_hit_rate = (expected_hits / total_requests * 100) if total_requests > 0 else 0
        assert abs(stats["hit_rate_pct"] - expected_hit_rate) < 0.01, \
            f"Hit rate mismatch: expected {expected_hit_rate:.2f}%, got {stats['hit_rate_pct']:.2f}%"
    
    def test_cache_stats_after_clear(self, cache):
        """Test that cache stats are reset after clear"""
        
        # Add some entries and access them
        cache.set(123456, {"discord_uid": 123456})
        cache.get(123456)  # Hit
        cache.get(789012)  # Miss
        
        # Clear cache
        cache.clear()
        
        stats = cache.get_stats()
        
        assert stats["hits"] == 0, "Hits should be reset to 0"
        assert stats["misses"] == 0, "Misses should be reset to 0"
        assert stats["cached_players"] == 0, "Cached players should be 0"
        assert stats["hit_rate_pct"] == 0, "Hit rate should be 0"
    
    def test_cache_update_existing_entry(self, cache):
        """Test updating an existing cache entry"""
        
        test_cases = [
            # (discord_uid, initial_record, updated_record)
            (123456, {"discord_uid": 123456, "mmr": 1500}, {"discord_uid": 123456, "mmr": 1520}),
            (789012, {"discord_uid": 789012, "mmr": 1600}, {"discord_uid": 789012, "mmr": 1580}),
        ]
        
        for discord_uid, initial_record, updated_record in test_cases:
            # Set initial value
            cache.set(discord_uid, initial_record)
            result = cache.get(discord_uid)
            assert result == initial_record, f"Initial set failed for {discord_uid}"
            
            # Update value
            cache.set(discord_uid, updated_record)
            result = cache.get(discord_uid)
            assert result == updated_record, \
                f"Update failed for {discord_uid}: expected {updated_record}, got {result}"
    
    def test_cache_isolation(self, cache):
        """Test that cache entries are isolated (modifications to retrieved objects don't affect cache)"""
        
        discord_uid = 123456
        original_record = {"discord_uid": discord_uid, "mmr": 1500, "wins": 10}
        
        cache.set(discord_uid, original_record)
        
        # Get the record and modify it
        retrieved = cache.get(discord_uid)
        retrieved["mmr"] = 9999
        retrieved["wins"] = 9999
        
        # Get the record again and verify it's unchanged
        retrieved_again = cache.get(discord_uid)
        assert retrieved_again["mmr"] == 1500, "Cache entry was incorrectly modified"
        assert retrieved_again["wins"] == 10, "Cache entry was incorrectly modified"


class TestStaticDataCache:
    """Test suite for StaticDataCache singleton"""
    
    def test_static_cache_exists(self):
        """Test that the static_cache singleton is available"""
        assert static_cache is not None
        assert hasattr(static_cache, "countries")
        assert hasattr(static_cache, "maps")
        assert hasattr(static_cache, "races")
        assert hasattr(static_cache, "regions")
    
    def test_static_cache_immutability(self):
        """Test that static cache data is loaded and accessible"""
        # This test verifies the cache works but doesn't test the actual data
        # since that would depend on the JSON files
        try:
            _ = static_cache.countries
            _ = static_cache.maps
            _ = static_cache.races
            _ = static_cache.regions
        except Exception as e:
            pytest.fail(f"Static cache should be accessible: {e}")

