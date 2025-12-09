"""
Tests for mod validation system including cache handle extraction and validation.
"""

import json
import pytest
from pathlib import Path

from src.backend.services.mods_service import ModsService
from src.backend.services.replay_service import parse_replay_data_blocking


class TestModsService:
    """Test the ModsService functionality."""
    
    def test_mods_service_loads_data(self):
        """Test that ModsService loads mods.json correctly."""
        mods_service = ModsService()
        
        assert mods_service.get_mod_name() == "SC: Evo Complete"
        assert mods_service.get_mod_author() == "SCEvoDev"
    
    def test_get_mod_link_by_region(self):
        """Test getting mod links for different regions."""
        mods_service = ModsService()
        
        am_link = mods_service.get_mod_link("am")
        eu_link = mods_service.get_mod_link("eu")
        as_link = mods_service.get_mod_link("as")
        
        assert am_link is not None
        assert "battlenet" in am_link.lower()
        assert eu_link is not None
        assert "battlenet" in eu_link.lower()
        assert as_link is not None
        assert "battlenet" in as_link.lower()
        
        # Test aliases
        assert mods_service.get_mod_link("americas") == am_link
        assert mods_service.get_mod_link("europe") == eu_link
        assert mods_service.get_mod_link("asia") == as_link
    
    def test_get_handles_for_region(self):
        """Test getting cache handles for different regions."""
        mods_service = ModsService()
        
        am_main, am_artmod = mods_service.get_handles_for_region("am")
        eu_main, eu_artmod = mods_service.get_handles_for_region("eu")
        as_main, as_artmod = mods_service.get_handles_for_region("as")
        
        # Verify we get handles
        assert len(am_main) > 0
        assert len(am_artmod) > 0
        assert len(eu_main) > 0
        assert len(eu_artmod) > 0
        assert len(as_main) > 0
        assert len(as_artmod) > 0
        
        # Verify they're different
        assert am_main != eu_main
        assert am_main != as_main
    
    def test_get_all_known_handles(self):
        """Test getting all known cache handles."""
        mods_service = ModsService()
        
        all_handles = mods_service.get_all_known_handles()
        
        assert isinstance(all_handles, set)
        assert len(all_handles) > 0
        
        # Verify handles are URLs
        for handle in list(all_handles)[:5]:
            assert handle.startswith("http")
            assert "depot.classic.blizzard.com" in handle
    
    def test_validate_cache_handles_with_valid_am_region(self):
        """Test validation with valid Americas region handles."""
        mods_service = ModsService()
        
        am_main, am_artmod = mods_service.get_handles_for_region("am")
        
        # Create test handles: all AM handles + 7 unknown
        unknown_handles = [f"https://fake-url-{i}.s2ma" for i in range(7)]
        test_handles = am_main + unknown_handles
        
        result = mods_service.validate_cache_handles(test_handles)
        
        assert result["valid"] is True
        assert result["region_detected"] == "am"
        assert "official" in result["message"].lower()
    
    def test_validate_cache_handles_with_too_few_unknown(self):
        """Test validation fails with wrong number of unknown handles."""
        mods_service = ModsService()
        
        am_main, _ = mods_service.get_handles_for_region("am")
        
        # Only 5 unknown handles instead of 7
        unknown_handles = [f"https://fake-url-{i}.s2ma" for i in range(5)]
        test_handles = am_main + unknown_handles
        
        result = mods_service.validate_cache_handles(test_handles)
        
        assert result["valid"] is False
        assert "7 unknown handles" in result["message"]
    
    def test_validate_cache_handles_with_missing_main_handles(self):
        """Test validation fails when missing required main handles."""
        mods_service = ModsService()
        
        am_main, _ = mods_service.get_handles_for_region("am")
        
        # Missing some main handles
        incomplete_main = am_main[:len(am_main)//2]
        unknown_handles = [f"https://fake-url-{i}.s2ma" for i in range(7)]
        test_handles = incomplete_main + unknown_handles
        
        result = mods_service.validate_cache_handles(test_handles)
        
        assert result["valid"] is False
    
    def test_validate_cache_handles_with_artmod(self):
        """Test validation passes with optional artmod handles."""
        mods_service = ModsService()
        
        am_main, am_artmod = mods_service.get_handles_for_region("am")
        
        # Include artmod handles
        unknown_handles = [f"https://fake-url-{i}.s2ma" for i in range(7)]
        test_handles = am_main + am_artmod + unknown_handles
        
        result = mods_service.validate_cache_handles(test_handles)
        
        assert result["valid"] is True
        assert result["region_detected"] == "am"


class TestReplayCacheHandleExtraction:
    """Test cache handle extraction from actual replay files."""
    
    @pytest.fixture
    def test_replay_dir(self):
        """Get the test replay directory."""
        return Path("tests/test_data/test_cache_handles")
    
    def test_official_replays_pass_validation(self, test_replay_dir):
        """Test that replays marked as (Official) pass cache handle validation."""
        if not test_replay_dir.exists():
            pytest.skip(f"Test replay directory not found: {test_replay_dir}")
        
        mods_service = ModsService()
        official_replays = list(test_replay_dir.glob("*Official*.SC2Replay"))
        
        if not official_replays:
            pytest.skip("No official test replays found")
        
        print(f"\nTesting {len(official_replays)} official replays:")
        
        passed = 0
        skipped = 0
        
        for replay_path in official_replays:
            try:
                # Use repr() for safe printing of filenames with special chars
                print(f"\n  Testing: {repr(replay_path.name)}")
            except:
                print(f"\n  Testing replay file...")
            
            with open(replay_path, 'rb') as f:
                replay_bytes = f.read()
            
            # Parse replay
            parsed_data = parse_replay_data_blocking(replay_bytes)
            
            # Check parsing succeeded - skip if it's not a 2-player replay
            if parsed_data.get("error"):
                if "Expected 2 players" in parsed_data.get("error", ""):
                    print(f"    Skipped - not a 2-player replay")
                    skipped += 1
                    continue
                else:
                    assert False, f"Failed to parse: {parsed_data.get('error')}"
            
            # Check cache handles exist
            cache_handles = parsed_data.get("cache_handles")
            assert cache_handles is not None, f"No cache_handles in replay"
            assert isinstance(cache_handles, list), f"cache_handles not a list"
            assert len(cache_handles) > 0, f"Empty cache_handles"
            
            # Validate cache handles
            validation_result = mods_service.validate_cache_handles(cache_handles)
            
            print(f"    Cache handles: {len(cache_handles)}")
            print(f"    Region: {validation_result.get('region_detected', 'unknown')}")
            print(f"    Valid: {validation_result['valid']}")
            print(f"    Message: {validation_result['message']}")
            
            assert validation_result["valid"] is True, \
                f"Replay should pass validation but failed: {validation_result['message']}"
            
            passed += 1
        
        print(f"\n  Summary: {passed} passed, {skipped} skipped")
        
        # At least some replays should have passed
        assert passed > 0, "No replays were successfully validated"
    
    def test_fake_replays_fail_validation(self, test_replay_dir):
        """Test that replays marked as (Fake) fail cache handle validation."""
        if not test_replay_dir.exists():
            pytest.skip(f"Test replay directory not found: {test_replay_dir}")
        
        mods_service = ModsService()
        fake_replays = list(test_replay_dir.glob("*Fake*.SC2Replay"))
        
        if not fake_replays:
            pytest.skip("No fake test replays found")
        
        print(f"\nTesting {len(fake_replays)} fake replays:")
        
        failed_validation = 0
        skipped = 0
        
        for replay_path in fake_replays:
            try:
                # Use repr() for safe printing of filenames with special chars
                print(f"\n  Testing: {repr(replay_path.name)}")
            except:
                print(f"\n  Testing replay file...")
            
            with open(replay_path, 'rb') as f:
                replay_bytes = f.read()
            
            # Parse replay
            parsed_data = parse_replay_data_blocking(replay_bytes)
            
            # Check parsing succeeded (we're testing validation, not parsing)
            if parsed_data.get("error"):
                if "Expected 2 players" in parsed_data.get("error", ""):
                    print(f"    Skipping - not a 2-player replay")
                else:
                    print(f"    Skipping due to parse error: {parsed_data.get('error')}")
                skipped += 1
                continue
            
            # Check cache handles exist
            cache_handles = parsed_data.get("cache_handles")
            if not cache_handles:
                print(f"    Skipping - no cache_handles found")
                skipped += 1
                continue
            
            # Validate cache handles
            validation_result = mods_service.validate_cache_handles(cache_handles)
            
            print(f"    Cache handles: {len(cache_handles)}")
            print(f"    Region: {validation_result.get('region_detected', 'unknown')}")
            print(f"    Valid: {validation_result['valid']}")
            print(f"    Message: {validation_result['message']}")
            
            assert validation_result["valid"] is False, \
                f"Replay should fail validation but passed"
            
            failed_validation += 1
        
        print(f"\n  Summary: {failed_validation} failed validation (as expected), {skipped} skipped")
        
        # At least some replays should have failed validation
        assert failed_validation > 0, "No replays were successfully tested for validation failure"
    
    def test_cache_handle_extraction_format(self, test_replay_dir):
        """Test that extracted cache handles have the correct format."""
        if not test_replay_dir.exists():
            pytest.skip(f"Test replay directory not found: {test_replay_dir}")
        
        all_replays = list(test_replay_dir.glob("*.SC2Replay"))
        
        if not all_replays:
            pytest.skip("No test replays found")
        
        # Test first replay
        replay_path = all_replays[0]
        
        with open(replay_path, 'rb') as f:
            replay_bytes = f.read()
        
        parsed_data = parse_replay_data_blocking(replay_bytes)
        
        if parsed_data.get("error"):
            pytest.skip(f"Could not parse test replay: {parsed_data.get('error')}")
        
        cache_handles = parsed_data.get("cache_handles")
        
        assert cache_handles is not None
        assert isinstance(cache_handles, list)
        
        # Check format of handles
        for handle in cache_handles:
            assert isinstance(handle, str)
            assert handle.startswith("http")
            assert ".s2ma" in handle or ".s2mod" in handle


class TestModVerificationIntegration:
    """Integration tests for mod verification in match completion service."""
    
    def test_verify_mod_with_valid_handles(self):
        """Test mod verification with valid cache handles."""
        from src.backend.services.match_completion_service import MatchCompletionService
        
        service = MatchCompletionService()
        
        # Create mock match details
        match_details = {"id": 1}
        
        # Create mock replay data with valid AM handles
        mods_service = ModsService()
        am_main, _ = mods_service.get_handles_for_region("am")
        unknown = [f"https://fake-{i}.s2ma" for i in range(7)]
        cache_handles = am_main + unknown
        
        replay_data = {
            "cache_handles": cache_handles
        }
        
        result = service._verify_mod(match_details, replay_data)
        
        assert result["success"] is True
        assert "official" in result["message"].lower()
        assert result["region_detected"] == "am"
    
    def test_verify_mod_with_invalid_handles(self):
        """Test mod verification with invalid cache handles."""
        from src.backend.services.match_completion_service import MatchCompletionService
        
        service = MatchCompletionService()
        
        # Create mock match details
        match_details = {"id": 1}
        
        # Create mock replay data with only fake handles
        fake_handles = [f"https://fake-{i}.s2ma" for i in range(20)]
        
        replay_data = {
            "cache_handles": fake_handles
        }
        
        result = service._verify_mod(match_details, replay_data)
        
        assert result["success"] is False
        assert "unofficial" in result["message"].lower() or "7 unknown handles" in result["message"]
    
    def test_verify_mod_with_json_string(self):
        """Test mod verification handles JSON string format."""
        from src.backend.services.match_completion_service import MatchCompletionService
        
        service = MatchCompletionService()
        
        # Create mock match details
        match_details = {"id": 1}
        
        # Create mock replay data with JSON string (as stored in DB)
        mods_service = ModsService()
        am_main, _ = mods_service.get_handles_for_region("am")
        unknown = [f"https://fake-{i}.s2ma" for i in range(7)]
        cache_handles = am_main + unknown
        
        replay_data = {
            "cache_handles": json.dumps(cache_handles)
        }
        
        result = service._verify_mod(match_details, replay_data)
        
        assert result["success"] is True
        assert "official" in result["message"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

