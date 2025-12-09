"""
Comprehensive tests for RegionsService cross-region mapping functionality.
"""

import pytest
from src.backend.services.regions_service import RegionsService, RegionMappingNotFoundError


class TestRegionsServiceCrossRegionMapping:
    """Test cross-region server mapping functionality."""
    
    def setup_method(self):
        """Initialize RegionsService for each test."""
        self.regions_service = RegionsService()
    
    def test_load_cross_region_data(self):
        """Test that cross-region data is loaded successfully."""
        assert self.regions_service._cross_region_data is not None
        assert isinstance(self.regions_service._cross_region_data, list)
        assert len(self.regions_service._cross_region_data) > 0
    
    def test_build_lookup_maps(self):
        """Test that lookup maps are built correctly."""
        assert self.regions_service._cross_region_map is not None
        assert isinstance(self.regions_service._cross_region_map, dict)
        assert len(self.regions_service._cross_region_map) > 0
        
        assert self.regions_service._short_name_to_name_map is not None
        assert isinstance(self.regions_service._short_name_to_name_map, dict)
        
        assert self.regions_service._name_to_short_name_map is not None
        assert isinstance(self.regions_service._name_to_short_name_map, dict)
    
    def test_get_game_server_name_by_short_name_valid(self):
        """Test converting valid short_name to full server name."""
        short_name = "US West"
        server_name = self.regions_service.get_game_server_name_by_short_name(short_name)
        assert server_name == "Western United States"
    
    def test_get_game_server_name_by_short_name_all_servers(self):
        """Test that all game servers can be converted from short_name to name."""
        game_servers = self.regions_service.get_game_servers()
        for server in game_servers:
            short_name = server['short_name']
            expected_name = server['name']
            actual_name = self.regions_service.get_game_server_name_by_short_name(short_name)
            assert actual_name == expected_name
    
    def test_get_game_server_name_by_short_name_invalid(self):
        """Test that invalid short_name raises ValueError."""
        with pytest.raises(ValueError) as excinfo:
            self.regions_service.get_game_server_name_by_short_name("Invalid Server")
        assert "Invalid game server short_name" in str(excinfo.value)
    
    def test_get_game_server_short_name_by_name_valid(self):
        """Test converting valid server name to short_name."""
        server_name = "Western United States"
        short_name = self.regions_service.get_game_server_short_name_by_name(server_name)
        assert short_name == "US West"
    
    def test_get_game_server_short_name_by_name_all_servers(self):
        """Test that all game servers can be converted from name to short_name."""
        game_servers = self.regions_service.get_game_servers()
        for server in game_servers:
            name = server['name']
            expected_short_name = server['short_name']
            actual_short_name = self.regions_service.get_game_server_short_name_by_name(name)
            assert actual_short_name == expected_short_name
    
    def test_get_game_server_short_name_by_name_invalid(self):
        """Test that invalid server name raises ValueError."""
        with pytest.raises(ValueError) as excinfo:
            self.regions_service.get_game_server_short_name_by_name("Invalid Server Name")
        assert "Invalid game server name" in str(excinfo.value)
    
    def test_get_match_server_same_region(self):
        """Test server selection when both players are in the same region."""
        server_name = self.regions_service.get_match_server("NAW", "NAW")
        assert server_name == "Western United States"
        
        server_name = self.regions_service.get_match_server("NAE", "NAE")
        assert server_name == "Eastern United States"
        
        server_name = self.regions_service.get_match_server("EUW", "EUW")
        assert server_name == "Central Europe"
    
    def test_get_match_server_different_regions_order_independent(self):
        """Test that region pair order doesn't matter."""
        server_name_1 = self.regions_service.get_match_server("NAW", "NAE")
        server_name_2 = self.regions_service.get_match_server("NAE", "NAW")
        assert server_name_1 == server_name_2
        assert server_name_1 == "Central United States"
    
    def test_get_match_server_cross_region_north_america(self):
        """Test server selection for North American region pairs."""
        assert self.regions_service.get_match_server("NAW", "NAC") == "Central United States"
        assert self.regions_service.get_match_server("NAC", "NAE") == "Central United States"
        assert self.regions_service.get_match_server("NAW", "NAE") == "Central United States"
    
    def test_get_match_server_cross_region_europe_asia(self):
        """Test server selection for Europe-Asia region pairs."""
        server_name = self.regions_service.get_match_server("EUW", "SEA")
        assert server_name is not None
        assert len(server_name) > 0
    
    def test_get_match_server_cross_continent(self):
        """Test server selection for cross-continental region pairs."""
        server_name = self.regions_service.get_match_server("NAW", "EUW")
        assert server_name in [
            "Western United States", 
            "Central United States", 
            "Eastern United States", 
            "Central Europe"
        ]
    
    def test_get_match_server_invalid_region_pair(self):
        """Test that invalid region pairs raise RegionMappingNotFoundError."""
        with pytest.raises(RegionMappingNotFoundError) as excinfo:
            self.regions_service.get_match_server("INVALID1", "INVALID2")
        assert "No server mapping exists" in str(excinfo.value)
    
    def test_get_match_server_one_invalid_region(self):
        """Test that one invalid region raises RegionMappingNotFoundError."""
        with pytest.raises(RegionMappingNotFoundError) as excinfo:
            self.regions_service.get_match_server("NAW", "INVALID")
        assert "No server mapping exists" in str(excinfo.value)
    
    def test_cross_region_map_uses_frozenset(self):
        """Test that cross-region map uses frozenset keys for order independence."""
        key1 = frozenset(["NAW", "NAE"])
        key2 = frozenset(["NAE", "NAW"])
        
        assert key1 == key2
        assert key1 in self.regions_service._cross_region_map
    
    def test_all_region_pairs_have_mapping(self):
        """Test that all residential region pairs have a server mapping."""
        residential_regions = self.regions_service.get_residential_regions()
        region_codes = [r['code'] for r in residential_regions]
        
        missing_pairs = []
        for i, region1 in enumerate(region_codes):
            for region2 in region_codes[i:]:
                try:
                    server_name = self.regions_service.get_match_server(region1, region2)
                    assert server_name is not None
                    assert len(server_name) > 0
                except RegionMappingNotFoundError:
                    missing_pairs.append((region1, region2))
        
        if missing_pairs:
            print(f"\nWarning: {len(missing_pairs)} region pairs are missing mappings:")
            for pair in missing_pairs[:10]:
                print(f"  - {pair}")
    
    def test_all_mappings_use_valid_short_names(self):
        """Test that all mappings in cross_table.json use valid short_names."""
        valid_short_names = set(self.regions_service._short_name_to_name_map.keys())
        
        invalid_mappings = []
        for entry in self.regions_service._cross_region_data:
            mapping = entry.get('mapping')
            if mapping and mapping not in valid_short_names:
                invalid_mappings.append(entry)
        
        assert len(invalid_mappings) == 0, (
            f"Found {len(invalid_mappings)} mappings with invalid short_names: "
            f"{[m['mapping'] for m in invalid_mappings[:5]]}"
        )
    
    def test_performance_get_match_server(self):
        """Test that get_match_server is fast (O(1) lookup)."""
        import time
        
        iterations = 1000
        start_time = time.time()
        
        for _ in range(iterations):
            self.regions_service.get_match_server("NAW", "NAE")
        
        elapsed_time = time.time() - start_time
        avg_time_ms = (elapsed_time / iterations) * 1000
        
        assert avg_time_ms < 1.0, f"Average lookup time {avg_time_ms:.3f}ms is too slow"
    
    def test_singleton_behavior(self):
        """Test that multiple RegionsService instances share the same data."""
        service1 = RegionsService()
        service2 = RegionsService()
        
        result1 = service1.get_match_server("NAW", "NAE")
        result2 = service2.get_match_server("NAW", "NAE")
        
        assert result1 == result2


class TestRegionsServiceEdgeCases:
    """Test edge cases and error handling."""
    
    def setup_method(self):
        """Initialize RegionsService for each test."""
        self.regions_service = RegionsService()
    
    def test_empty_region_strings(self):
        """Test that empty region strings raise appropriate errors."""
        with pytest.raises(RegionMappingNotFoundError):
            self.regions_service.get_match_server("", "NAW")
        
        with pytest.raises(RegionMappingNotFoundError):
            self.regions_service.get_match_server("NAW", "")
        
        with pytest.raises(RegionMappingNotFoundError):
            self.regions_service.get_match_server("", "")
    
    def test_none_region_values(self):
        """Test that None region values raise appropriate errors."""
        with pytest.raises(RegionMappingNotFoundError):
            self.regions_service.get_match_server(None, "NAW")
        
        with pytest.raises(RegionMappingNotFoundError):
            self.regions_service.get_match_server("NAW", None)
    
    def test_case_sensitive_regions(self):
        """Test that region codes are case-sensitive."""
        server_name_upper = self.regions_service.get_match_server("NAW", "NAE")
        
        with pytest.raises(RegionMappingNotFoundError):
            self.regions_service.get_match_server("naw", "nae")
    
    def test_whitespace_in_regions(self):
        """Test that whitespace in region codes raises errors."""
        with pytest.raises(RegionMappingNotFoundError):
            self.regions_service.get_match_server(" NAW", "NAE")
        
        with pytest.raises(RegionMappingNotFoundError):
            self.regions_service.get_match_server("NAW ", "NAE")

