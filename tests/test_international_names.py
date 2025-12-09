"""
Test international character support in validation service.
"""

import sys
from src.backend.services.validation_service import ValidationService

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_international_validation():
    """Test validation with various international characters."""
    
    validation_service = ValidationService()
    
    print("=" * 60)
    print("TESTING MAIN USER ID (English-only)")
    print("=" * 60)
    
    # Main User ID tests (English-only)
    main_tests = [
        ("JohnDoe123", True, "Valid English name"),
        ("User_Name", True, "Valid with underscore"),
        ("Player-1", True, "Valid with hyphen"),
        ("한글이름", False, "Korean should fail for main ID"),
        ("中文名字", False, "Chinese should fail for main ID"),
        ("Русский", False, "Cyrillic should fail for main ID"),
        ("日本語", False, "Japanese should fail for main ID"),
        ("Ab", False, "Too short"),
        ("ThisNameIsTooLong", False, "Too long"),
    ]
    
    for name, expected_valid, description in main_tests:
        is_valid, error = validation_service.validate_user_id(name, allow_international=False)
        status = "[OK]" if is_valid == expected_valid else "[FAIL]"
        print(f"{status} '{name}' - {description}")
        if is_valid != expected_valid:
            print(f"  Expected: {expected_valid}, Got: {is_valid}, Error: {error}")
    
    print("\n" + "=" * 60)
    print("TESTING ALTERNATIVE IDs (International support)")
    print("=" * 60)
    
    # Alt ID tests (International characters allowed)
    alt_tests = [
        ("JohnDoe123", True, "Valid English name"),
        ("한글이름", True, "Korean should work"),
        ("中文名字", True, "Chinese should work"),
        ("Русский", True, "Cyrillic should work"),
        ("日本語名前", True, "Japanese should work"),
        ("АлексейПетр", True, "Russian name should work"),
        ("김철수", True, "Korean full name"),
        ("王小明", True, "Chinese full name"),
        ("Müller", True, "German umlaut"),
        ("José", True, "Spanish accent"),
        ("François", True, "French accent"),
        ("Αλέξανδρος", True, "Greek"),
        ("محمد", True, "Arabic"),
        ("עברית", True, "Hebrew"),
        ("ไทย", True, "Thai"),
        ("한", False, "Too short (2 chars)"),
        ("이것은매우긴이름입니다", False, "Too long (>12 chars)"),
        ("Test@User", False, "Special char @ not allowed"),
        ("User#123", False, "Special char # not allowed"),
        ("Name$", False, "Special char $ not allowed"),
    ]
    
    for name, expected_valid, description in alt_tests:
        is_valid, error = validation_service.validate_user_id(name, allow_international=True)
        status = "[OK]" if is_valid == expected_valid else "[FAIL]"
        print(f"{status} '{name}' - {description}")
        if is_valid != expected_valid:
            print(f"  Expected: {expected_valid}, Got: {is_valid}, Error: {error}")
    
    print("\n" + "=" * 60)
    print("CHARACTER LENGTH TESTS (Discord modal enforces 3-12 anyway)")
    print("=" * 60)
    
    # Length tests for various scripts
    length_tests = [
        ("한글", 2, "Korean 2 chars"),
        ("한글이", 3, "Korean 3 chars (min)"),
        ("한글이름명칭호칭", 8, "Korean 8 chars"),
        ("한글이름명칭호칭여덟아홉열", 12, "Korean 12 chars (max)"),
        ("中", 1, "Chinese 1 char"),
        ("中文名", 3, "Chinese 3 chars (min)"),
        ("中文名字姓氏全名十二字", 12, "Chinese 12 chars (max)"),
        ("РусАБВГДЕЁЖЗИЙ", 12, "Cyrillic 12 chars (max)"),
    ]
    
    for name, length, description in length_tests:
        is_valid, error = validation_service.validate_user_id(name, allow_international=True)
        print(f"  '{name}' ({length} chars) - {description}")
        print(f"    Valid: {is_valid}, Error: {error}")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("[+] Main User ID: English-only (A-Z, 0-9, _, -)")
    print("[+] Alt IDs: International characters supported")
    print("[+] Length: 3-12 characters enforced by Discord modal")
    print("=" * 60)


if __name__ == "__main__":
    test_international_validation()

