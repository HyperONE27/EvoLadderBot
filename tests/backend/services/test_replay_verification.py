"""
Tests for replay verification functionality.

This module tests the replay verification logic in MatchCompletionService
that checks if uploaded replays match the assigned match parameters.
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any
from unittest.mock import MagicMock, patch

from src.backend.core.types import VerificationResult
from src.backend.services.match_completion_service import MatchCompletionService
from src.backend.services.replay_service import parse_replay_data_blocking


class TestReplayVerification:
    """Test suite for replay verification logic."""
    
    @pytest.fixture
    def match_completion_service(self):
        """Get the MatchCompletionService singleton."""
        return MatchCompletionService()
    
    @pytest.fixture
    def sample_match_data(self) -> Dict[str, Any]:
        """
        Sample match data based on the JSON provided in the proposal.
        
        This corresponds to match ID 14 from the matches_1v1 table.
        """
        return {
            "id": 14,
            "player_1_discord_uid": 218147282875318274,
            "player_2_discord_uid": 473117604488151043,
            "player_1_race": "bw_zerg",
            "player_2_race": "sc2_protoss",
            "player_1_mmr": 1610,
            "player_2_mmr": 1500,
            "player_1_report": 2,
            "player_2_report": 2,
            "match_result": 2,
            "mmr_change": -25,
            "map_played": "Tokamak LE",
            "server_used": "USE",
            "played_at": "2025-10-24 06:42:00+00",
            "player_1_replay_path": "https://example.com/replay1.SC2Replay",
            "player_1_replay_time": "2025-10-24 06:45:14+00",
            "player_2_replay_path": "https://example.com/replay2.SC2Replay",
            "player_2_replay_time": "2025-10-24 06:45:13+00"
        }
    
    @pytest.fixture
    def test_replay_files(self) -> Dict[str, Path]:
        """Get paths to test replay files."""
        test_data_dir = Path(__file__).parent.parent.parent / "test_data" / "test_replay_files"
        return {
            "matching": test_data_dir / "HyperONEgunnerTokamak.SC2Replay",
            "mismatched_1": test_data_dir / "DarkReBellionIsles.SC2Replay",
            "mismatched_2": test_data_dir / "threepointPSIArcGoldenWall.SC2Replay"
        }
    
    def parse_replay_file(self, replay_path: Path) -> Dict[str, Any]:
        """Helper to parse a replay file."""
        with open(replay_path, 'rb') as f:
            replay_bytes = f.read()
        return parse_replay_data_blocking(replay_bytes)
    
    def test_verify_races_match(self, match_completion_service, sample_match_data):
        """Test race verification when races match."""
        replay_data = {
            "player_1_race": "bw_zerg",
            "player_2_race": "sc2_protoss"
        }
        
        result = match_completion_service._verify_races(sample_match_data, replay_data)
        assert result['success'] is True
        assert result['expected_races'] == {"bw_zerg", "sc2_protoss"}
        assert result['played_races'] == {"bw_zerg", "sc2_protoss"}
    
    def test_verify_races_mismatch(self, match_completion_service, sample_match_data):
        """Test race verification when races don't match."""
        replay_data = {
            "player_1_race": "sc2_terran",
            "player_2_race": "sc2_zerg"
        }
        
        result = match_completion_service._verify_races(sample_match_data, replay_data)
        assert result['success'] is False
        assert result['expected_races'] == {"bw_zerg", "sc2_protoss"}
        assert result['played_races'] == {"sc2_terran", "sc2_zerg"}
    
    def test_verify_races_swapped(self, match_completion_service, sample_match_data):
        """Test race verification when races are swapped (should still pass)."""
        replay_data = {
            "player_1_race": "sc2_protoss",
            "player_2_race": "bw_zerg"
        }
        
        result = match_completion_service._verify_races(sample_match_data, replay_data)
        assert result['success'] is True
    
    def test_verify_map_match(self, match_completion_service, sample_match_data):
        """Test map verification when maps match."""
        replay_data = {
            "map_name": "Tokamak LE"
        }
        
        result = match_completion_service._verify_map(sample_match_data, replay_data)
        assert result['success'] is True
        assert result['expected_map'] == "Tokamak LE"
        assert result['played_map'] == "Tokamak LE"
    
    def test_verify_map_mismatch(self, match_completion_service, sample_match_data):
        """Test map verification when maps don't match."""
        replay_data = {
            "map_name": "Golden Wall LE"
        }
        
        result = match_completion_service._verify_map(sample_match_data, replay_data)
        assert result['success'] is False
        assert result['expected_map'] == "Tokamak LE"
        assert result['played_map'] == "Golden Wall LE"
    
    def test_verify_timestamp_within_window(self, match_completion_service, sample_match_data):
        """Test timestamp verification when replay is within 20 minutes."""
        played_at = datetime.fromisoformat("2025-10-24T06:42:00+00:00")
        replay_date = played_at + timedelta(minutes=10)
        
        replay_data = {
            "replay_date": replay_date.isoformat(),
            "duration": 300
        }
        
        result = match_completion_service._verify_timestamp(sample_match_data, replay_data)
        assert result['success'] is True
        assert result['time_difference_minutes'] < 20
    
    def test_verify_timestamp_outside_window(self, match_completion_service, sample_match_data):
        """Test timestamp verification when replay is outside 20 minutes."""
        played_at = datetime.fromisoformat("2025-10-24T06:42:00+00:00")
        replay_date = played_at + timedelta(minutes=30)
        
        replay_data = {
            "replay_date": replay_date.isoformat(),
            "duration": 300
        }
        
        result = match_completion_service._verify_timestamp(sample_match_data, replay_data)
        assert result['success'] is False
        assert result['time_difference_minutes'] > 20
    
    def test_verify_timestamp_with_game_duration(self, match_completion_service, sample_match_data):
        """Test timestamp verification accounting for game duration."""
        played_at = datetime.fromisoformat("2025-10-24T06:42:00+00:00")
        replay_date = played_at + timedelta(minutes=10)
        game_duration = 600
        
        replay_data = {
            "replay_date": replay_date.isoformat(),
            "duration": game_duration
        }
        
        result = match_completion_service._verify_timestamp(sample_match_data, replay_data)
        assert result['success'] is True
    
    def test_verify_observers_none(self, match_completion_service):
        """Test observer verification with no observers."""
        replay_data = {
            "observers": None
        }
        
        result = match_completion_service._verify_observers(replay_data)
        assert result['success'] is True
        assert result['observers_found'] == []
    
    def test_verify_observers_empty_list(self, match_completion_service):
        """Test observer verification with empty list."""
        replay_data = {
            "observers": []
        }
        
        result = match_completion_service._verify_observers(replay_data)
        assert result['success'] is True
        assert result['observers_found'] == []
    
    def test_verify_observers_empty_json_string(self, match_completion_service):
        """Test observer verification with empty JSON string."""
        replay_data = {
            "observers": "[]"
        }
        
        result = match_completion_service._verify_observers(replay_data)
        assert result['success'] is True
        assert result['observers_found'] == []
    
    def test_verify_observers_present_list(self, match_completion_service):
        """Test observer verification with observers present (list)."""
        replay_data = {
            "observers": ["Observer1", "Observer2"]
        }
        
        result = match_completion_service._verify_observers(replay_data)
        assert result['success'] is False
        assert result['observers_found'] == ["Observer1", "Observer2"]
    
    def test_verify_observers_present_json_string(self, match_completion_service):
        """Test observer verification with observers present (JSON string)."""
        replay_data = {
            "observers": json.dumps(["Observer1"])
        }
        
        result = match_completion_service._verify_observers(replay_data)
        assert result['success'] is False
        assert result['observers_found'] == ["Observer1"]
    
    @pytest.mark.skipif(
        not (Path(__file__).parent.parent.parent / "test_data" / "test_replay_files" / "HyperONEgunnerTokamak.SC2Replay").exists(),
        reason="Test replay files not available"
    )
    def test_parse_matching_replay(self, test_replay_files):
        """Test parsing the replay that should match all criteria."""
        replay_path = test_replay_files["matching"]
        assert replay_path.exists(), f"Test replay file not found: {replay_path}"
        
        parsed = self.parse_replay_file(replay_path)
        
        assert parsed.get("error") is None, f"Parsing error: {parsed.get('error')}"
        assert parsed.get("map_name") is not None
        assert parsed.get("player_1_race") is not None
        assert parsed.get("player_2_race") is not None
        assert parsed.get("replay_date") is not None
        assert parsed.get("duration") is not None
        assert parsed.get("observers") is not None
    
    @pytest.mark.skipif(
        not (Path(__file__).parent.parent.parent / "test_data" / "test_replay_files" / "DarkReBellionIsles.SC2Replay").exists(),
        reason="Test replay files not available"
    )
    def test_parse_mismatched_replay_1(self, test_replay_files):
        """Test parsing the first mismatched replay."""
        replay_path = test_replay_files["mismatched_1"]
        assert replay_path.exists(), f"Test replay file not found: {replay_path}"
        
        parsed = self.parse_replay_file(replay_path)
        
        assert parsed.get("error") is None, f"Parsing error: {parsed.get('error')}"
        assert parsed.get("map_name") != "Tokamak LE"


class TestAsyncReplayVerification:
    """Test suite for async replay verification orchestration."""
    
    @pytest.fixture
    def match_completion_service(self):
        """Get the MatchCompletionService singleton."""
        return MatchCompletionService()
    
    @pytest.fixture
    def sample_match_data(self) -> Dict[str, Any]:
        """Sample match data for testing."""
        return {
            "id": 14,
            "player_1_discord_uid": 218147282875318274,
            "player_2_discord_uid": 473117604488151043,
            "player_1_race": "bw_zerg",
            "player_2_race": "sc2_protoss",
            "map_played": "Tokamak LE",
            "played_at": "2025-10-24 06:42:00+00",
        }
    
    @pytest.fixture
    def valid_replay_data(self) -> Dict[str, Any]:
        """Valid replay data that should pass all checks."""
        played_at = datetime.fromisoformat("2025-10-24T06:42:00+00:00")
        replay_date = played_at + timedelta(minutes=5)
        
        return {
            "player_1_race": "bw_zerg",
            "player_2_race": "sc2_protoss",
            "map_name": "Tokamak LE",
            "replay_date": replay_date.isoformat(),
            "duration": 300,
            "observers": []
        }
    
    @pytest.fixture
    def invalid_replay_data(self) -> Dict[str, Any]:
        """Invalid replay data that should fail multiple checks."""
        played_at = datetime.fromisoformat("2025-10-24T06:42:00+00:00")
        replay_date = played_at + timedelta(minutes=30)
        
        return {
            "player_1_race": "sc2_terran",
            "player_2_race": "sc2_zerg",
            "map_name": "Wrong Map LE",
            "replay_date": replay_date.isoformat(),
            "duration": 300,
            "observers": ["Observer1"]
        }
    
    @pytest.mark.asyncio
    async def test_verify_replay_data_success(
        self, 
        match_completion_service, 
        sample_match_data, 
        valid_replay_data
    ):
        """Test the awaitable verify_replay_data when all checks pass."""
        with patch('src.backend.services.data_access_service.DataAccessService') as mock_das:
            mock_das_instance = MagicMock()
            mock_das_instance.get_match.return_value = sample_match_data
            mock_das.return_value = mock_das_instance
            
            result = await match_completion_service.verify_replay_data(
                match_id=14,
                replay_data=valid_replay_data
            )
            
        assert result['races']['success'] is True
        assert result['map']['success'] is True
        assert result['timestamp']['success'] is True
        assert result['observers']['success'] is True
    
    @pytest.mark.asyncio
    async def test_verify_replay_data_failure(
        self, 
        match_completion_service, 
        sample_match_data, 
        invalid_replay_data
    ):
        """Test the awaitable verify_replay_data when checks fail."""
        with patch('src.backend.services.data_access_service.DataAccessService') as mock_das:
            mock_das_instance = MagicMock()
            mock_das_instance.get_match.return_value = sample_match_data
            mock_das.return_value = mock_das_instance
            
            result = await match_completion_service.verify_replay_data(
                match_id=14,
                replay_data=invalid_replay_data
            )
            
        assert result['races']['success'] is False
        assert result['map']['success'] is False
        assert result['timestamp']['success'] is False
        assert result['observers']['success'] is False
    
    @pytest.mark.asyncio
    async def test_verify_replay_data_match_not_found(
        self, 
        match_completion_service, 
        valid_replay_data
    ):
        """Test that ValueError is raised when match data is not found."""
        with patch('src.backend.services.data_access_service.DataAccessService') as mock_das:
            mock_das_instance = MagicMock()
            mock_das_instance.get_match.return_value = None
            mock_das.return_value = mock_das_instance
            
            with pytest.raises(ValueError, match="Match 999 not found"):
                await match_completion_service.verify_replay_data(
                    match_id=999,
                    replay_data=valid_replay_data
                )
    
    @pytest.mark.asyncio
    async def test_verify_replay_data_returns_detailed_info(
        self, 
        match_completion_service, 
        sample_match_data, 
        invalid_replay_data
    ):
        """Test that detailed information is returned in the result."""
        with patch('src.backend.services.data_access_service.DataAccessService') as mock_das:
            mock_das_instance = MagicMock()
            mock_das_instance.get_match.return_value = sample_match_data
            mock_das.return_value = mock_das_instance
            
            result = await match_completion_service.verify_replay_data(
                match_id=14,
                replay_data=invalid_replay_data
            )
            
        # Check races detail
        assert 'expected_races' in result['races']
        assert 'played_races' in result['races']
        assert result['races']['expected_races'] == {"bw_zerg", "sc2_protoss"}
        assert result['races']['played_races'] == {"sc2_terran", "sc2_zerg"}
        
        # Check map detail
        assert result['map']['expected_map'] == "Tokamak LE"
        assert result['map']['played_map'] == "Wrong Map LE"
        
        # Check timestamp detail
        assert 'time_difference_minutes' in result['timestamp']
        assert result['timestamp']['time_difference_minutes'] > 20
        
        # Check observers detail
        assert result['observers']['observers_found'] == ["Observer1"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
