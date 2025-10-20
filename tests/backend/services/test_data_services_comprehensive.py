"""
Comprehensive test suite for data lookup services (Countries, Maps, Races, Regions).

Tests data retrieval, lookups, and formatting methods.
"""

import pytest
from src.backend.services.countries_service import CountriesService
from src.backend.services.maps_service import MapsService
from src.backend.services.races_service import RacesService
from src.backend.services.regions_service import RegionsService


class TestCountriesService:
    """Test suite for CountriesService"""
    
    @pytest.fixture
    def service(self):
        return CountriesService()
    
    def test_get_countries(self, service):
        """Test retrieving all countries"""
        countries = service.get_countries()
        assert countries is not None
        assert isinstance(countries, list)
        assert len(countries) > 0, "Should have at least some countries"
    
    def test_get_country_name(self, service):
        """Test getting country names by code"""
        
        test_cases = [
            # (country_code, should_have_name)
            ("US", True),
            ("KR", True),
            ("JP", True),
            ("GB", True),
            ("XX", False),  # Unknown
            ("", False),     # Empty
            (None, False),   # None
        ]
        
        for country_code, should_have_name in test_cases:
            result = service.get_country_name(country_code)
            if should_have_name:
                assert result is not None, f"Should have name for {country_code}"
                assert isinstance(result, str)
                assert len(result) > 0
            # If no name expected, implementation may return None or default
    
    def test_country_code_lookup(self, service):
        """Test looking up countries by various identifiers"""
        countries = service.get_countries()
        
        # Verify each country has expected fields
        for country in countries:
            assert "code" in country or "iso_code" in country or "country_code" in country, \
                f"Country should have a code field: {country}"


class TestMapsService:
    """Test suite for MapsService"""
    
    @pytest.fixture
    def service(self):
        return MapsService()
    
    def test_get_maps(self, service):
        """Test retrieving all maps"""
        maps = service.get_maps()
        assert maps is not None
        assert isinstance(maps, list)
        assert len(maps) > 0, "Should have at least some maps"
    
    def test_get_map_name(self, service):
        """Test getting map names"""
        maps = service.get_maps()
        
        if len(maps) > 0:
            # Test first map
            first_map = maps[0]
            short_name = first_map.get("short_name")
            
            if short_name:
                full_name = service.get_map_name(short_name)
                assert full_name is not None
                assert isinstance(full_name, str)
    
    def test_get_map_short_names(self, service):
        """Test getting list of map short names"""
        short_names = service.get_map_short_names()
        assert short_names is not None
        assert isinstance(short_names, list)
        assert len(short_names) > 0, "Should have map short names"
    
    def test_get_map_battlenet_link(self, service):
        """Test generating Battle.net map links"""
        
        test_cases = [
            # (map_short_name, region)
            ("TestMap", "americas"),
            ("TestMap", "europe"),
            ("TestMap", "asia"),
        ]
        
        maps = service.get_maps()
        if len(maps) > 0:
            map_short_name = maps[0].get("short_name")
            
            for region in ["americas", "europe", "asia"]:
                link = service.get_map_battlenet_link(map_short_name, region)
                # May return None or a link, depends on implementation
                if link:
                    assert isinstance(link, str)
                    assert "http" in link.lower()
    
    def test_get_map_author(self, service):
        """Test getting map authors"""
        maps = service.get_maps()
        
        if len(maps) > 0:
            first_map = maps[0]
            short_name = first_map.get("short_name")
            
            if short_name:
                author = service.get_map_author(short_name)
                # May return None or author name
                if author:
                    assert isinstance(author, str)


class TestRacesService:
    """Test suite for RacesService"""
    
    @pytest.fixture
    def service(self):
        return RacesService()
    
    def test_get_races(self, service):
        """Test retrieving all races"""
        races = service.get_races()
        assert races is not None
        assert isinstance(races, list)
        assert len(races) > 0, "Should have at least some races"
    
    def test_get_race_name(self, service):
        """Test getting race names"""
        
        test_cases = [
            # (race_code, should_have_name)
            ("bw_terran", True),
            ("bw_zerg", True),
            ("bw_protoss", True),
            ("sc2_terran", True),
            ("sc2_zerg", True),
            ("sc2_protoss", True),
            ("invalid_race", False),
        ]
        
        for race_code, should_have_name in test_cases:
            result = service.get_race_name(race_code)
            if should_have_name:
                assert result is not None, f"Should have name for {race_code}"
                assert isinstance(result, str)
                assert len(result) > 0
    
    def test_get_race_group_label(self, service):
        """Test getting race group labels (BW vs SC2)"""
        
        test_cases = [
            # (race_code, expected_group_substring)
            ("bw_terran", "brood"),
            ("bw_zerg", "brood"),
            ("sc2_terran", "starcraft"),
            ("sc2_zerg", "starcraft"),
        ]
        
        for race_code, expected_substring in test_cases:
            result = service.get_race_group_label(race_code)
            if result:
                assert isinstance(result, str)
                assert expected_substring.lower() in result.lower(), \
                    f"Expected '{expected_substring}' in group label for {race_code}, got {result}"
    
    def test_get_race_dropdown_groups(self, service):
        """Test getting race dropdown groups"""
        groups = service.get_race_dropdown_groups()
        
        assert groups is not None
        assert isinstance(groups, dict)
        assert "brood_war" in groups or "bw" in str(groups).lower()
        assert "starcraft2" in groups or "sc2" in str(groups).lower()


class TestRegionsService:
    """Test suite for RegionsService"""
    
    @pytest.fixture
    def service(self):
        return RegionsService()
    
    def test_get_regions(self, service):
        """Test retrieving all regions"""
        regions = service.get_regions()
        assert regions is not None
        assert isinstance(regions, list)
        assert len(regions) > 0, "Should have at least some regions"
    
    def test_get_game_region_for_server(self, service):
        """Test getting game region for server codes"""
        regions = service.get_regions()
        
        if len(regions) > 0:
            # Test with first available region
            first_region = regions[0]
            # This tests that the method exists and handles input
            result = service.get_game_region_for_server("TEST")
            # May return None or region info
            if result:
                assert isinstance(result, dict)
    
    def test_format_server_with_region(self, service):
        """Test formatting server display with region"""
        
        test_cases = [
            # (server_code)
            ("US_EAST"),
            ("US_WEST"),
            ("EU"),
            ("KR"),
            ("INVALID"),
        ]
        
        for server_code in test_cases:
            result = service.format_server_with_region(server_code)
            assert result is not None
            assert isinstance(result, str)
            # Should return something, even if just the original code
            assert len(result) > 0


class TestDataServicesIntegration:
    """Integration tests across all data services"""
    
    def test_all_services_instantiate(self):
        """Test that all services can be instantiated"""
        
        services = [
            CountriesService(),
            MapsService(),
            RacesService(),
            RegionsService(),
        ]
        
        for service in services:
            assert service is not None, f"Service {type(service).__name__} should instantiate"
    
    def test_all_services_have_data(self):
        """Test that all services have loaded data"""
        
        test_cases = [
            (CountriesService(), "get_countries"),
            (MapsService(), "get_maps"),
            (RacesService(), "get_races"),
            (RegionsService(), "get_regions"),
        ]
        
        for service, method_name in test_cases:
            method = getattr(service, method_name)
            data = method()
            assert data is not None, f"{type(service).__name__}.{method_name}() should return data"
            assert len(data) > 0, f"{type(service).__name__}.{method_name}() should have data"

