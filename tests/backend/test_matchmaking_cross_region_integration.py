"""
Integration tests for matchmaking service with cross-region server selection.
"""

import pytest

from src.backend.services.matchmaking_service import Matchmaker, Player, QueuePreferences
from src.backend.services.regions_service import RegionsService, RegionMappingNotFoundError


class TestMatchmakingCrossRegionIntegration:
    """Integration tests for cross-region matchmaking."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.matchmaker = Matchmaker()
        self.regions_service = RegionsService()
    
    def test_regions_service_integration_with_matchmaker(self):
        """Test that the matchmaker has access to RegionsService and its new methods."""
        assert self.matchmaker.regions_service is not None
        assert hasattr(self.matchmaker.regions_service, 'get_match_server')
        assert hasattr(self.matchmaker.regions_service, 'get_game_server_name_by_short_name')
        assert hasattr(self.matchmaker.regions_service, 'get_game_server_short_name_by_name')
    
    def test_server_selection_logic_for_same_region(self):
        """Test server name resolution for players in the same region."""
        region = "NAW"
        
        server_name = self.regions_service.get_match_server(region, region)
        assert server_name == "Western United States"
        
        server_code = self.regions_service.get_game_server_code_by_name(server_name)
        assert server_code == "USW"
    
    def test_server_selection_logic_for_different_regions(self):
        """Test server name resolution for players in different regions."""
        region1 = "NAW"
        region2 = "NAE"
        
        server_name = self.regions_service.get_match_server(region1, region2)
        assert server_name == "Central United States"
        
        server_code = self.regions_service.get_game_server_code_by_name(server_name)
        assert server_code == "USC"
    
    def test_server_selection_logic_handles_invalid_regions(self):
        """Test that invalid regions raise appropriate exceptions."""
        region1 = "INVALID1"
        region2 = "INVALID2"
        
        with pytest.raises(RegionMappingNotFoundError):
            self.regions_service.get_match_server(region1, region2)
    
    def test_server_selection_logic_for_europe(self):
        """Test server selection for European regions."""
        region1 = "EUW"
        region2 = "EUE"
        
        server_name = self.regions_service.get_match_server(region1, region2)
        assert server_name == "Central Europe"
        
        server_code = self.regions_service.get_game_server_code_by_name(server_name)
        assert server_code == "EUC"
    
    def test_complete_flow_region_to_server_code(self):
        """Test the complete flow from regions to server code."""
        test_cases = [
            ("NAW", "NAW", "USW"),
            ("NAE", "NAE", "USE"),
            ("NAW", "NAE", "USC"),
            ("EUW", "EUE", "EUC"),
        ]
        
        for region1, region2, expected_code in test_cases:
            server_name = self.regions_service.get_match_server(region1, region2)
            server_code = self.regions_service.get_game_server_code_by_name(server_name)
            assert server_code == expected_code, (
                f"Expected {expected_code} for {region1}+{region2}, got {server_code}"
            )
    
    def test_matchmaker_has_correct_regions_service_instance(self):
        """Test that matchmaker uses the singleton RegionsService."""
        matchmaker1 = Matchmaker()
        matchmaker2 = Matchmaker()
        
        result1 = matchmaker1.regions_service.get_match_server("NAW", "NAE")
        result2 = matchmaker2.regions_service.get_match_server("NAW", "NAE")
        
        assert result1 == result2
        assert result1 == "Central United States"


class TestPlayerRegionHandling:
    """Test Player class residential_region handling."""
    
    def test_player_creation_with_region(self):
        """Test that Player can be created with residential_region."""
        prefs = QueuePreferences(
            selected_races=["bw_terran"],
            vetoed_maps=[],
            discord_user_id=7001,
            user_id="testplayer"
        )
        
        player = Player(7001, "testplayer", prefs, bw_mmr=1500, residential_region="NAW")
        
        assert player.residential_region == "NAW"
    
    def test_player_creation_without_region(self):
        """Test that Player can be created without residential_region."""
        prefs = QueuePreferences(
            selected_races=["bw_terran"],
            vetoed_maps=[],
            discord_user_id=7002,
            user_id="testplayer"
        )
        
        player = Player(7002, "testplayer", prefs, bw_mmr=1500)
        
        assert player.residential_region is None
    
    def test_player_region_can_be_updated(self):
        """Test that Player residential_region can be updated after creation."""
        prefs = QueuePreferences(
            selected_races=["bw_terran"],
            vetoed_maps=[],
            discord_user_id=7003,
            user_id="testplayer"
        )
        
        player = Player(7003, "testplayer", prefs, bw_mmr=1500)
        assert player.residential_region is None
        
        player.residential_region = "EUW"
        assert player.residential_region == "EUW"
    
    def test_player_with_multiple_regions(self):
        """Test players with different regions."""
        prefs1 = QueuePreferences(
            selected_races=["bw_terran"],
            vetoed_maps=[],
            discord_user_id=8001,
            user_id="player1"
        )
        prefs2 = QueuePreferences(
            selected_races=["sc2_protoss"],
            vetoed_maps=[],
            discord_user_id=8002,
            user_id="player2"
        )
        
        player1 = Player(8001, "player1", prefs1, bw_mmr=1500, residential_region="NAW")
        player2 = Player(8002, "player2", prefs2, sc2_mmr=1500, residential_region="NAE")
        
        assert player1.residential_region != player2.residential_region
        assert player1.residential_region == "NAW"
        assert player2.residential_region == "NAE"
        
        regions_service = RegionsService()
        server_name = regions_service.get_match_server(
            player1.residential_region,
            player2.residential_region
        )
        assert server_name == "Central United States"
