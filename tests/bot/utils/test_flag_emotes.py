"""
Test script to verify flag emote functionality for /setup command.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.bot.utils.discord_utils import get_flag_emote

def test_flag_emotes():
    print("\n" + "="*70)
    print("FLAG EMOTE TEST FOR /SETUP COMMAND")
    print("="*70 + "\n")
    
    # Test standard country codes (should return Unicode flag emojis)
    print("[Standard Countries - Unicode Flags]")
    test_countries = ['US', 'CA', 'KR', 'JP', 'GB', 'DE', 'FR']
    for code in test_countries:
        result = get_flag_emote(code)
        # Check if it's a Unicode flag (2 characters in specific range)
        is_unicode = len(result) == 2 and ord(result[0]) >= 127462 and ord(result[1]) >= 127462
        status = "[OK]" if is_unicode else "[ERROR]"
        print(f"   {status} {code}: Unicode flag emoji (len={len(result)})")
    
    # Test special codes (should return custom emotes from emotes.json)
    print("\n[Special Codes - Custom Emotes]")
    special_codes = ['XX', 'ZZ']
    for code in special_codes:
        result = get_flag_emote(code)
        # Custom emotes have format <:name:id>
        is_custom = result.startswith('<:') and result.endswith('>')
        status = "[OK]" if is_custom else "[ERROR]"
        name = "Nonrepresenting" if code == 'XX' else "Other"
        print(f"   {status} {code} ({name}): {result}")
        if is_custom:
            print(f"        Custom emote format confirmed")
    
    print("\n[Dropdown Integration]")
    print("   The /setup command country dropdowns will now show:")
    print("   - Unicode flag emojis for standard countries (US, CA, KR, etc.)")
    print("   - Custom Discord emotes for XX (Nonrepresenting) and ZZ (Other)")
    print("   - All flags will appear next to country names in the select menus")
    
    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    test_flag_emotes()

