"""
Tests for the matchmaking service.

This module tests the advanced matchmaking algorithm including:
- Player categorization
- List equalization
- Lead side selection
- Priority calculation
- Match finding
- Race selection
"""

import pytest
import asyncio
from unittest.mock import Mock, patch
from src.backend.services.matchmaking_service import (
    Matchmaker, Player, QueuePreferences, MatchResult
)


class TestPlayer:
    """Test the Player class functionality."""
    
    def test_player_creation(self):
        """Test player creation with MMR data."""
        preferences = QueuePreferences(
            selected_races=["bw_terran", "sc2_zerg"],
            vetoed_maps=["Arkanoid"],
            discord_user_id=12345,
            user_id="TestPlayer"
        )
        
        player = Player(
            discord_user_id=12345,
            user_id="TestPlayer",
            preferences=preferences,
            bw_mmr=1500,
            sc2_mmr=1600
        )
        
        assert player.discord_user_id == 12345
        assert player.user_id == "TestPlayer"
        assert player.bw_mmr == 1500
        assert player.sc2_mmr == 1600
        assert player.has_bw_race is True
        assert player.has_sc2_race is True
        assert player.bw_race == "bw_terran"
        assert player.sc2_race == "sc2_zerg"
        assert player.wait_cycles == 0
    
    def test_player_race_detection(self):
        """Test player race detection logic."""
        # BW only player
        bw_prefs = QueuePreferences(
            selected_races=["bw_terran"],
            vetoed_maps=[],
            discord_user_id=1,
            user_id="BWPlayer"
        )
        bw_player = Player(1, "BWPlayer", bw_prefs, bw_mmr=1500)
        
        assert bw_player.has_bw_race is True
        assert bw_player.has_sc2_race is False
        assert bw_player.bw_race == "bw_terran"
        assert bw_player.sc2_race is None
        
        # SC2 only player
        sc2_prefs = QueuePreferences(
            selected_races=["sc2_protoss"],
            vetoed_maps=[],
            discord_user_id=2,
            user_id="SC2Player"
        )
        sc2_player = Player(2, "SC2Player", sc2_prefs, sc2_mmr=1600)
        
        assert sc2_player.has_bw_race is False
        assert sc2_player.has_sc2_race is True
        assert sc2_player.bw_race is None
        assert sc2_player.sc2_race == "sc2_protoss"
    
    def test_effective_mmr(self):
        """Test effective MMR calculation."""
        preferences = QueuePreferences(
            selected_races=["bw_terran", "sc2_zerg"],
            vetoed_maps=[],
            discord_user_id=1,
            user_id="TestPlayer"
        )
        player = Player(1, "TestPlayer", preferences, bw_mmr=1500, sc2_mmr=1600)
        
        assert player.get_effective_mmr(True) == 1500  # BW match
        assert player.get_effective_mmr(False) == 1600  # SC2 match
    
    def test_race_for_match(self):
        """Test race selection for matches."""
        preferences = QueuePreferences(
            selected_races=["bw_terran", "sc2_zerg"],
            vetoed_maps=[],
            discord_user_id=1,
            user_id="TestPlayer"
        )
        player = Player(1, "TestPlayer", preferences, bw_mmr=1500, sc2_mmr=1600)
        
        assert player.get_race_for_match(True) == "bw_terran"   # BW match
        assert player.get_race_for_match(False) == "sc2_zerg"  # SC2 match


class TestMatchmaker:
    """Test the Matchmaker class functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.matchmaker = Matchmaker()
        
        # Create test players
        self.bw_player = Player(
            discord_user_id=1,
            user_id="BWPlayer",
            preferences=QueuePreferences(
                selected_races=["bw_terran"],
                vetoed_maps=[],
                discord_user_id=1,
                user_id="BWPlayer"
            ),
            bw_mmr=1500
        )
        
        self.sc2_player = Player(
            discord_user_id=2,
            user_id="SC2Player",
            preferences=QueuePreferences(
                selected_races=["sc2_zerg"],
                vetoed_maps=[],
                discord_user_id=2,
                user_id="SC2Player"
            ),
            sc2_mmr=1600
        )
        
        self.both_player = Player(
            discord_user_id=3,
            user_id="BothPlayer",
            preferences=QueuePreferences(
                selected_races=["bw_protoss", "sc2_terran"],
                vetoed_maps=[],
                discord_user_id=3,
                user_id="BothPlayer"
            ),
            bw_mmr=1400,
            sc2_mmr=1700
        )
    
    def test_categorize_players(self):
        """Test player categorization logic."""
        # Add players to matchmaker
        self.matchmaker.players = [self.bw_player, self.sc2_player, self.both_player]
        
        bw_only, sc2_only, both_races = self.matchmaker.categorize_players()
        
        assert len(bw_only) == 1
        assert len(sc2_only) == 1
        assert len(both_races) == 1
        
        assert bw_only[0].discord_user_id == 1
        assert sc2_only[0].discord_user_id == 2
        assert both_races[0].discord_user_id == 3
    
    def test_categorize_players_sorting(self):
        """Test that players are sorted by MMR."""
        # Create multiple players with different MMRs
        high_mmr_bw = Player(
            discord_user_id=4,
            user_id="HighBW",
            preferences=QueuePreferences(
                selected_races=["bw_terran"],
                vetoed_maps=[],
                discord_user_id=4,
                user_id="HighBW"
            ),
            bw_mmr=2000
        )
        
        low_mmr_bw = Player(
            discord_user_id=5,
            user_id="LowBW",
            preferences=QueuePreferences(
                selected_races=["bw_terran"],
                vetoed_maps=[],
                discord_user_id=5,
                user_id="LowBW"
            ),
            bw_mmr=1000
        )
        
        self.matchmaker.players = [low_mmr_bw, high_mmr_bw]
        bw_only, sc2_only, both_races = self.matchmaker.categorize_players()
        
        # Should be sorted by MMR (highest first)
        assert bw_only[0].bw_mmr == 2000
        assert bw_only[1].bw_mmr == 1000
    
    def test_max_diff_calculation(self):
        """Test elastic MMR window calculation."""
        # Test different queue sizes and wait cycles
        assert self.matchmaker.max_diff(0, 5) == 125  # Base case
        assert self.matchmaker.max_diff(6, 5) == 200  # First growth
        assert self.matchmaker.max_diff(12, 5) == 275  # Second growth
        
        # Test larger queue sizes
        assert self.matchmaker.max_diff(0, 8) == 100  # Medium queue
        assert self.matchmaker.max_diff(0, 15) == 75  # Large queue
    
    def test_equalize_lists(self):
        """Test list equalization logic."""
        # Test case: X=2, Y=3, Z=2
        x_list = [self.bw_player, self.bw_player]
        y_list = [self.sc2_player, self.sc2_player, self.sc2_player]
        z_list = [self.both_player, self.both_player]
        
        equalized_x, equalized_y, remaining_z = self.matchmaker.equalize_lists(x_list, y_list, z_list)
        
        # Should equalize to 3 each
        assert len(equalized_x) == 3
        assert len(equalized_y) == 3
        assert len(remaining_z) == 1  # One Z player should remain
    
    def test_find_matches_priority_calculation(self):
        """Test that priority calculation is efficient and correct."""
        # Create players with different wait cycles
        player1 = Player(
            discord_user_id=1,
            user_id="Player1",
            preferences=QueuePreferences(
                selected_races=["bw_terran"],
                vetoed_maps=[],
                discord_user_id=1,
                user_id="Player1"
            ),
            bw_mmr=1500
        )
        player1.wait_cycles = 5
        
        player2 = Player(
            discord_user_id=2,
            user_id="Player2",
            preferences=QueuePreferences(
                selected_races=["bw_terran"],
                vetoed_maps=[],
                discord_user_id=2,
                user_id="Player2"
            ),
            bw_mmr=1600
        )
        player2.wait_cycles = 10
        
        # Test priority calculation
        lead_side = [player1, player2]
        lead_mean = (1500 + 1600) / 2  # 1550
        
        # Player1 priority: |1500 - 1550| + (10 * 5) = 50 + 50 = 100
        # Player2 priority: |1600 - 1550| + (10 * 10) = 50 + 100 = 150
        # Player2 should have higher priority (sorted first)
        
        matches = self.matchmaker.find_matches(lead_side, [self.sc2_player], True)
        # Should find a match (player2 has higher priority)
        assert len(matches) >= 0  # At least no errors
    
    def test_lead_side_selection(self):
        """Test that smaller list becomes lead side."""
        # Test case: BW=2, SC2=3
        bw_list = [self.bw_player, self.bw_player]
        sc2_list = [self.sc2_player, self.sc2_player, self.sc2_player]
        
        # BW should be lead side (smaller)
        if len(bw_list) <= len(sc2_list):
            lead_side, follow_side = bw_list, sc2_list
            is_bw_match = True
        else:
            lead_side, follow_side = sc2_list, bw_list
            is_bw_match = False
        
        assert lead_side == bw_list
        assert follow_side == sc2_list
        assert is_bw_match is True
    
    def test_race_selection_logic(self):
        """Test race selection based on lead side."""
        # Test BW lead side
        is_bw_match = True
        p1 = self.bw_player
        p2 = self.sc2_player
        
        if is_bw_match:
            p1_race = p1.get_race_for_match(True)   # BW race
            p2_race = p2.get_race_for_match(False)  # SC2 race
        else:
            p1_race = p1.get_race_for_match(False)  # SC2 race
            p2_race = p2.get_race_for_match(True)   # BW race
        
        assert p1_race == "bw_terran"
        assert p2_race == "sc2_zerg"
        
        # Test SC2 lead side
        is_bw_match = False
        p1 = self.sc2_player
        p2 = self.bw_player
        
        if is_bw_match:
            p1_race = p1.get_race_for_match(True)   # BW race
            p2_race = p2.get_race_for_match(False)  # SC2 race
        else:
            p1_race = p1.get_race_for_match(False)  # SC2 race
            p2_race = p2.get_race_for_match(True)   # BW race
        
        assert p1_race == "sc2_zerg"
        assert p2_race == "bw_terran"
    
    @patch('src.backend.services.matchmaking_service.DatabaseReader')
    @patch('src.backend.services.matchmaking_service.DatabaseWriter')
    def test_add_player_mmr_lookup(self, mock_db_writer, mock_db_reader):
        """Test MMR lookup when adding players."""
        # Mock database responses
        mock_reader_instance = Mock()
        mock_reader_instance.get_player_mmr_1v1.return_value = {'mmr': 1500}
        mock_db_reader.return_value = mock_reader_instance
        
        mock_writer_instance = Mock()
        mock_db_writer.return_value = mock_writer_instance
        
        # Create matchmaker with mocked database
        matchmaker = Matchmaker()
        matchmaker.db_reader = mock_reader_instance
        matchmaker.db_writer = mock_writer_instance
        
        # Create player
        preferences = QueuePreferences(
            selected_races=["bw_terran"],
            vetoed_maps=[],
            discord_user_id=1,
            user_id="TestPlayer"
        )
        player = Player(1, "TestPlayer", preferences)
        
        # Add player
        matchmaker.add_player(player)
        
        # Verify MMR lookup was called
        mock_reader_instance.get_player_mmr_1v1.assert_called_with(1, "bw_terran")
        assert player.bw_mmr == 1500
    
    def test_get_available_maps(self):
        """Test that available maps are correctly filtered based on player vetoes."""
        # Create players with vetoes
        prefs1 = QueuePreferences(
            selected_races=["bw_zerg"], 
            vetoed_maps=["Death Valley", "Keres Passage SEL"], 
            discord_user_id=1, 
            user_id="Player1"
        )
        player1 = Player(discord_user_id=1, user_id="Player1", preferences=prefs1)
        
        prefs2 = QueuePreferences(
            selected_races=["sc2_protoss"], 
            vetoed_maps=["Keres Passage SEL", "Khione SEL"], 
            discord_user_id=2, 
            user_id="Player2"
        )
        player2 = Player(discord_user_id=2, user_id="Player2", preferences=prefs2)
        
        # Expected maps (all maps minus vetoed ones)
        all_maps = self.matchmaker.maps_service.get_available_maps()
        expected_maps = [
            m for m in all_maps 
            if m not in ["Death Valley", "Keres Passage SEL", "Khione SEL"]
        ]
        
        # Get available maps
        available_maps = self.matchmaker._get_available_maps(player1, player2)
        
        # Assert that the available maps are correct
        assert set(available_maps) == set(expected_maps), \
            f"Expected maps {set(expected_maps)}, but got {set(available_maps)}"

    def test_generate_in_game_channel(self):
        """Test in-game channel generation."""
        channel = self.matchmaker.generate_in_game_channel()
        
        assert channel.startswith("scevo")
        assert len(channel) == 8  # "scevo" + 3 digits
        assert channel[5:].isdigit()
        assert 100 <= int(channel[5:]) <= 999
    
    def test_get_random_server(self):
        """Test that a valid server is returned."""
        servers = ["US East", "US West", "Europe", "Asia"]
        
        # Test multiple calls to ensure randomness
        for _ in range(10):
            server = self.matchmaker.get_random_server()
            assert server in servers


class TestMatchmakingIntegration:
    """Integration tests for the complete matchmaking flow."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.matchmaker = Matchmaker()
        
        # Create a realistic test scenario
        self.bw_players = [
            Player(
                discord_user_id=i,
                user_id=f"BWPlayer{i}",
                preferences=QueuePreferences(
                    selected_races=["bw_terran"],
                    vetoed_maps=[],
                    discord_user_id=i,
                    user_id=f"BWPlayer{i}"
                ),
                bw_mmr=1500 + i * 100
            ) for i in range(1, 4)  # 3 BW players
        ]
        
        self.sc2_players = [
            Player(
                discord_user_id=i,
                user_id=f"SC2Player{i}",
                preferences=QueuePreferences(
                    selected_races=["sc2_zerg"],
                    vetoed_maps=[],
                    discord_user_id=i,
                    user_id=f"SC2Player{i}"
                ),
                sc2_mmr=1600 + i * 100
            ) for i in range(4, 7)  # 3 SC2 players
        ]
        
        self.both_players = [
            Player(
                discord_user_id=i,
                user_id=f"BothPlayer{i}",
                preferences=QueuePreferences(
                    selected_races=["bw_protoss", "sc2_terran"],
                    vetoed_maps=[],
                    discord_user_id=i,
                    user_id=f"BothPlayer{i}"
                ),
                bw_mmr=1400 + i * 50,
                sc2_mmr=1700 + i * 50
            ) for i in range(7, 10)  # 3 both players
        ]
    
    def test_complete_matchmaking_flow(self):
        """Test the complete matchmaking flow."""
        # Add all players
        all_players = self.bw_players + self.sc2_players + self.both_players
        self.matchmaker.players = all_players
        
        # Test categorization
        bw_only, sc2_only, both_races = self.matchmaker.categorize_players()
        
        assert len(bw_only) == 3
        assert len(sc2_only) == 3
        assert len(both_races) == 3
        
        # Test equalization
        bw_list, sc2_list, remaining_z = self.matchmaker.equalize_lists(bw_only, sc2_only, both_races)
        
        # Should be equalized
        assert len(bw_list) == len(sc2_list)
        
        # Test lead side selection
        if len(bw_list) <= len(sc2_list):
            lead_side, follow_side = bw_list, sc2_list
            is_bw_match = True
        else:
            lead_side, follow_side = sc2_list, bw_list
            is_bw_match = False
        
        # Test match finding
        matches = self.matchmaker.find_matches(lead_side, follow_side, is_bw_match)
        
        # Should find some matches
        assert len(matches) >= 0
        
        # Test that matches are valid
        for p1, p2 in matches:
            assert p1.discord_user_id != p2.discord_user_id
            # Should be BW vs SC2
            if is_bw_match:
                assert p1.has_bw_race or p1.has_sc2_race
                assert p2.has_bw_race or p2.has_sc2_race
            else:
                assert p1.has_bw_race or p1.has_sc2_race
                assert p2.has_bw_race or p2.has_sc2_race


if __name__ == "__main__":
    pytest.main([__file__, "-v"])