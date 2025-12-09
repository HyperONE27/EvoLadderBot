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
        """Test user ID validation with English-only mode (now permissive, allows any characters)"""
        
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
            ("한글이름", True, None),  # Now allowed
            ("中文名字", True, None),  # Now allowed
            ("Русский", True, None),  # Now allowed
            ("José", True, None),  # Now allowed
            ("Müller", True, None),  # Now allowed
            ("Test@User", True, None),  # Now allowed
            ("User#123", True, None),  # Now allowed
            ("Name$", True, None),  # Now allowed
            ("Player.Name", True, None),  # Now allowed
            ("User*Name", True, None),  # Now allowed
            ("admin", True, None),  # No longer reserved
            ("ADMIN", True, None),  # No longer reserved
            ("Admin", True, None),  # No longer reserved
            ("moderator", True, None),  # No longer reserved
            ("mod", True, None),  # No longer reserved
            ("bot", True, None),  # No longer reserved
            ("discord", True, None),  # No longer reserved
            ("null", True, None),  # No longer reserved
            ("undefined", True, None),  # No longer reserved
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
        """Test user ID validation with international character support (now permissive, allows any characters)"""
        
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
            ("이것은매우긴이름입니다정말", False, "cannot exceed 12 characters"),
            ("Test@User", True, None),  # Now allowed
            ("User#123", True, None),  # Now allowed
            ("Name$", True, None),  # Now allowed
            ("Player<Name>", True, None),  # Now allowed
            ("User|Name", True, None),  # Now allowed
            ("", False, "cannot be empty"),
            ("ab", False, "at least 3 characters"),
            ("ValidName_123", True, None),
            ("Valid-Name", True, None),
            ("admin", True, None),  # No longer reserved
            ("MOD", True, None),  # No longer reserved
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
        """Test BattleTag validation (now permissive, allows any characters and 3-12 digits)"""
        
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
            ("NoHashtag", False, "one '#'"),
            ("Username", False, "one '#'"),
            ("Username#", False, "only digits"),
            ("Username#abc", False, "only digits"),
            ("Username#12", False, "3-12 digits"),  # Now 3-12 instead of 4-12
            ("Username#123", True, None),  # Now valid (3 digits)
            ("Username#1234567890123", False, "3-12 digits"),
            ("#1234", False, "1-12 characters"),  # Empty username not allowed
            ("A#123", True, None),  # Minimum username length (1 character)
            ("AB#1234", True, None),  # Now allowed (2 characters)
            ("TooLongUsername#1234", False, "1-12 characters"),
            ("User123#1234", True, None),  # Now allowed
            ("User_Name#1234", True, None),  # Now allowed
            ("한글이름#1234", True, None),  # Now allowed
            ("Test@User#123", True, None),  # Now allowed
            ("admin#1234", True, None),  # No longer reserved
            ("moderator#1234", True, None),  # No longer reserved
            ("mod#1234", True, None),  # No longer reserved
            ("bot#1234", True, None),  # No longer reserved
            ("discord#1234", True, None),  # No longer reserved
            ("blizzard#1234", True, None),  # No longer reserved
            ("battle#1234", True, None),  # No longer reserved
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
        """Test alternative IDs validation with English-only mode (now permissive, allows any characters)"""
        
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
            ("한글이름", False, True, None, 1),  # Now allowed
            ("P1,한글이름", False, True, None, 2),  # Now allowed
            ("admin", False, True, None, 1),  # No longer reserved
            ("P1,admin,P3", False, True, None, 3),  # No longer reserved
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
        """Test alternative IDs validation with international character support (now permissive, allows any characters)"""
        
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
            ("Player@Name", True, True, None, 1),  # Now allowed
            ("admin", True, True, None, 1),  # No longer reserved
            ("한글이름,admin,中文", True, True, None, 3),  # No longer reserved
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
            ("validate_battle_tag", ["A#123"], {}, True, None),  # Minimum username (1) and number length (3)
            ("validate_battle_tag", ["ABCDEFGHIJKL#123"], {}, True, None),  # Maximum username length (12) with min digits
            ("validate_battle_tag", ["Username#123"], {}, True, None),  # Minimum number length (3 digits now)
            ("validate_battle_tag", ["Username#123456789012"], {}, True, None),  # Maximum number length (12 digits)
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

