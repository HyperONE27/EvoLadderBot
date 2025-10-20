"""
Comprehensive test suite for ValidationService.

This test suite uses pytest and follows the pattern of defining large test case lists
for each test method, then iterating over them with a single assert.
"""

import pytest
from src.backend.services.validation_service import ValidationService


class TestValidationService:
    """Test suite for ValidationService"""
    
    @pytest.fixture
    def validation_service(self):
        """Fixture to provide a ValidationService instance"""
        return ValidationService()
    
    def test_validate_user_id_english_only(self, validation_service):
        """Test user ID validation with English-only mode (allow_international=False)"""
        
        test_cases = [
            # (user_id, expected_valid, expected_error_substring)
            ("JohnDoe123", True, None),
            ("Player_Name", True, None),
            ("Pro-Gamer-1", True, None),
            ("abc", True, None),  # Minimum length
            ("123456789012", True, None),  # Maximum length
            ("Test_123-ABC", True, None),
            ("ValidName", True, None),
            ("", False, "cannot be empty"),
            ("  ", False, "cannot be empty"),
            ("ab", False, "at least 3 characters"),
            ("ThisNameIsTooLongForValidation", False, "cannot exceed 12 characters"),
            ("한글이름", False, "English letters"),
            ("中文名字", False, "English letters"),
            ("Русский", False, "English letters"),
            ("José", False, "English letters"),
            ("Müller", False, "English letters"),
            ("Test@User", False, "English letters"),
            ("User#123", False, "English letters"),
            ("Name$", False, "English letters"),
            ("Player.Name", False, "English letters"),
            ("User*Name", False, "English letters"),
            ("admin", False, "reserved"),
            ("ADMIN", False, "reserved"),
            ("Admin", False, "reserved"),
            ("moderator", False, "reserved"),
            ("mod", False, "reserved"),
            ("bot", False, "reserved"),
            ("discord", False, "reserved"),
            ("null", False, "reserved"),
            ("undefined", False, "reserved"),
            ("   ValidName   ", True, None),  # Leading/trailing spaces should be stripped
        ]
        
        for user_id, expected_valid, expected_error_substring in test_cases:
            is_valid, error = validation_service.validate_user_id(user_id, allow_international=False)
            assert is_valid == expected_valid, f"Failed for '{user_id}': expected {expected_valid}, got {is_valid}"
            if expected_error_substring:
                assert expected_error_substring.lower() in error.lower(), \
                    f"Failed for '{user_id}': expected error containing '{expected_error_substring}', got '{error}'"
            else:
                assert error is None, f"Failed for '{user_id}': expected no error, got '{error}'"
    
    def test_validate_user_id_international(self, validation_service):
        """Test user ID validation with international character support (allow_international=True)"""
        
        test_cases = [
            # (user_id, expected_valid, expected_error_substring)
            ("JohnDoe123", True, None),
            ("한글이름", True, None),
            ("中文名字", True, None),
            ("Русский", True, None),
            ("日本語名前", True, None),
            ("АлексейПетр", True, None),
            ("김철수", True, None),
            ("王小明", True, None),
            ("Müller", True, None),
            ("José", True, None),
            ("François", True, None),
            ("Αλέξανδρος", True, None),
            ("محمد", True, None),
            ("עברית", True, None),
            ("ไทย", True, None),
            ("한", False, "at least 3 characters"),
            ("이것은매우긴이름입니다", False, "cannot exceed 12 characters"),
            ("Test@User", False, "invalid characters"),
            ("User#123", False, "invalid characters"),
            ("Name$", False, "invalid characters"),
            ("Player<Name>", False, "invalid characters"),
            ("User|Name", False, "invalid characters"),
            ("", False, "cannot be empty"),
            ("ab", False, "at least 3 characters"),
            ("ValidName_123", True, None),
            ("Valid-Name", True, None),
            ("admin", False, "reserved"),
            ("MOD", False, "reserved"),
        ]
        
        for user_id, expected_valid, expected_error_substring in test_cases:
            is_valid, error = validation_service.validate_user_id(user_id, allow_international=True)
            assert is_valid == expected_valid, f"Failed for '{user_id}': expected {expected_valid}, got {is_valid}"
            if expected_error_substring:
                assert expected_error_substring.lower() in error.lower(), \
                    f"Failed for '{user_id}': expected error containing '{expected_error_substring}', got '{error}'"
            else:
                assert error is None, f"Failed for '{user_id}': expected no error, got '{error}'"
    
    def test_validate_battle_tag(self, validation_service):
        """Test BattleTag validation"""
        
        test_cases = [
            # (battle_tag, expected_valid, expected_error_substring)
            ("Username#1234", True, None),
            ("JohnDoe#5678", True, None),
            ("Player#123456", True, None),
            ("ABC#4567", True, None),
            ("LongUsername#1234", True, None),
            ("xyz#9999", True, None),
            ("", False, "cannot be empty"),
            ("  ", False, "cannot be empty"),
            ("NoHashtag", False, "format"),
            ("Username", False, "format"),
            ("Username#", False, "format"),
            ("Username#abc", False, "format"),
            ("Username#12", False, "4-12 digits"),
            ("Username#123", False, "4-12 digits"),
            ("Username#1234567890123", False, "4-12 digits"),
            ("#1234", False, "3-12 letters"),
            ("AB#1234", False, "3-12 letters"),
            ("TooLongUsername#1234", False, "3-12 characters"),
            ("User123#1234", False, "3-12 letters"),
            ("User_Name#1234", False, "3-12 letters"),
            ("admin#1234", False, "reserved"),
            ("moderator#1234", False, "reserved"),
            ("mod#1234", False, "reserved"),
            ("bot#1234", False, "reserved"),
            ("discord#1234", False, "reserved"),
            ("blizzard#1234", False, "reserved"),
            ("battle#1234", False, "reserved"),
            ("   Username#1234   ", True, None),  # Should be stripped
        ]
        
        for battle_tag, expected_valid, expected_error_substring in test_cases:
            is_valid, error = validation_service.validate_battle_tag(battle_tag)
            assert is_valid == expected_valid, f"Failed for '{battle_tag}': expected {expected_valid}, got {is_valid}"
            if expected_error_substring:
                assert expected_error_substring.lower() in error.lower(), \
                    f"Failed for '{battle_tag}': expected error containing '{expected_error_substring}', got '{error}'"
            else:
                assert error is None, f"Failed for '{battle_tag}': expected no error, got '{error}'"
    
    def test_validate_alt_ids_english_only(self, validation_service):
        """Test alternative IDs validation with English-only mode"""
        
        test_cases = [
            # (alt_ids_string, allow_international, expected_valid, expected_error_substring, expected_parsed_count)
            ("", False, True, None, 0),
            ("  ", False, True, None, 0),
            ("PlayerOne", False, True, None, 1),
            ("PlayerOne,PlayerTwo", False, True, None, 2),
            ("PlayerOne, PlayerTwo, PlayerThree", False, True, None, 3),
            ("P1,P2,P3,P4", False, True, None, 4),
            ("P1,P2,P3,P4,P5", False, True, None, 5),
            ("P1,P2,P3,P4,P5,P6", False, False, "Maximum 5", 0),
            ("PlayerOne,PlayerOne", False, False, "Duplicate", 0),
            ("P1,P2,P1", False, False, "Duplicate", 0),
            ("ab", False, False, "at least 3 characters", 0),
            ("P1,ab,P3", False, False, "at least 3 characters", 0),
            ("TooLongName123", False, False, "cannot exceed 12 characters", 0),
            ("한글이름", False, False, "English letters", 0),
            ("P1,한글이름", False, False, "English letters", 0),
            ("admin", False, False, "reserved", 0),
            ("P1,admin,P3", False, False, "reserved", 0),
        ]
        
        for alt_ids_string, allow_international, expected_valid, expected_error_substring, expected_parsed_count in test_cases:
            is_valid, error, parsed_ids = validation_service.validate_alt_ids(alt_ids_string, allow_international=allow_international)
            assert is_valid == expected_valid, f"Failed for '{alt_ids_string}': expected {expected_valid}, got {is_valid}"
            if expected_error_substring:
                assert expected_error_substring.lower() in error.lower(), \
                    f"Failed for '{alt_ids_string}': expected error containing '{expected_error_substring}', got '{error}'"
            else:
                assert error is None, f"Failed for '{alt_ids_string}': expected no error, got '{error}'"
            assert len(parsed_ids) == expected_parsed_count, \
                f"Failed for '{alt_ids_string}': expected {expected_parsed_count} parsed IDs, got {len(parsed_ids)}"
    
    def test_validate_alt_ids_international(self, validation_service):
        """Test alternative IDs validation with international character support"""
        
        test_cases = [
            # (alt_ids_string, allow_international, expected_valid, expected_error_substring, expected_parsed_count)
            ("", True, True, None, 0),
            ("한글이름", True, True, None, 1),
            ("中文名字", True, True, None, 1),
            ("한글이름,中文名字", True, True, None, 2),
            ("PlayerOne,한글이름,中文名字", True, True, None, 3),
            ("P1,P2,한글,中文,Русский", True, True, None, 5),
            ("P1,P2,P3,P4,P5,P6", True, False, "Maximum 5", 0),
            ("한글이름,한글이름", True, False, "Duplicate", 0),
            ("한", True, False, "at least 3 characters", 0),
            ("이것은매우긴이름입니다", True, False, "cannot exceed 12 characters", 0),
            ("Player@Name", True, False, "invalid characters", 0),
            ("admin", True, False, "reserved", 0),
            ("한글이름,admin,中文", True, False, "reserved", 0),
        ]
        
        for alt_ids_string, allow_international, expected_valid, expected_error_substring, expected_parsed_count in test_cases:
            is_valid, error, parsed_ids = validation_service.validate_alt_ids(alt_ids_string, allow_international=allow_international)
            assert is_valid == expected_valid, f"Failed for '{alt_ids_string}': expected {expected_valid}, got {is_valid}"
            if expected_error_substring:
                assert expected_error_substring.lower() in error.lower(), \
                    f"Failed for '{alt_ids_string}': expected error containing '{expected_error_substring}', got '{error}'"
            else:
                assert error is None, f"Failed for '{alt_ids_string}': expected no error, got '{error}'"
            assert len(parsed_ids) == expected_parsed_count, \
                f"Failed for '{alt_ids_string}': expected {expected_parsed_count} parsed IDs, got {len(parsed_ids)}"
    
    def test_edge_cases(self, validation_service):
        """Test edge cases and boundary conditions"""
        
        test_cases = [
            # (method, args, kwargs, expected_valid, expected_error_substring)
            ("validate_user_id", ["123"], {"allow_international": False}, True, None),  # Only numbers
            ("validate_user_id", ["___"], {"allow_international": False}, True, None),  # Only underscores
            ("validate_user_id", ["---"], {"allow_international": False}, True, None),  # Only hyphens
            ("validate_user_id", ["_-_"], {"allow_international": False}, True, None),  # Mix of allowed special chars
            ("validate_user_id", ["한글이름명칭호칭", {}], {"allow_international": True}, False, "exceed"),  # Exactly 13 chars
            ("validate_battle_tag", ["ABC#1234"], {}, True, None),  # Minimum username length
            ("validate_battle_tag", ["ABCDEFGHIJKL#1234"], {}, True, None),  # Maximum username length
            ("validate_battle_tag", ["Username#1234"], {}, True, None),  # Minimum number length
            ("validate_battle_tag", ["Username#123456789012"], {}, True, None),  # Maximum number length
        ]
        
        for method_name, args, kwargs, expected_valid, expected_error_substring in test_cases:
            method = getattr(validation_service, method_name)
            result = method(*args, **kwargs)
            is_valid = result[0]
            error = result[1]
            
            assert is_valid == expected_valid, \
                f"Failed for {method_name}{args}: expected {expected_valid}, got {is_valid}"
            if expected_error_substring:
                assert expected_error_substring.lower() in error.lower(), \
                    f"Failed for {method_name}{args}: expected error containing '{expected_error_substring}', got '{error}'"
            else:
                assert error is None, \
                    f"Failed for {method_name}{args}: expected no error, got '{error}'"

