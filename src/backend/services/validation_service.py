"""
Validation service for user input validation.
"""
import re
from typing import Tuple, Optional, List


class ValidationService:
    """Service for validating user input data."""
    
    def validate_user_id(self, user_id: str, allow_international: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Validate a user ID (main name or alt name).
        
        Args:
            user_id: The user ID to validate
            allow_international: If True, allows international characters (Korean, Chinese, Cyrillic, etc.)
                                If False, only allows English letters, numbers, underscores, and hyphens
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not user_id or not user_id.strip():
            return False, "User ID cannot be empty"
        
        user_id = user_id.strip()
        
        if len(user_id) < 3:
            return False, "User ID must be at least 3 characters long"
        
        if len(user_id) > 12:
            return False, "User ID cannot exceed 12 characters"
        
        # Check for valid characters
        if allow_international:
            # Allow international characters: letters from any language, numbers, underscores, hyphens
            # \p{L} matches any Unicode letter (Korean, Chinese, Cyrillic, etc.)
            # \p{N} matches any Unicode number
            # Note: Python's re module doesn't support \p{L}, so we use a broader pattern
            # This allows any character that is NOT a control character or special symbol
            if not re.match(r'^[\w\u0080-\uFFFF_-]+$', user_id, re.UNICODE):
                return False, "User ID contains invalid characters"
        else:
            # English-only: only allow ASCII letters, numbers, underscores, and hyphens
            if not re.match(r'^[A-Za-z0-9_-]+$', user_id):
                return False, "User ID can only contain English letters, numbers, underscores, and hyphens"
        
        # Check for reserved words or inappropriate content (case-insensitive for English)
        reserved_words = ['admin', 'moderator', 'mod', 'bot', 'discord', 'null', 'undefined']
        if user_id.lower() in reserved_words:
            return False, "This user ID is reserved and cannot be used"
        
        return True, None

    def validate_battle_tag(self, battle_tag: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a BattleTag format
        
        Args:
            battle_tag: The BattleTag to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not battle_tag or not battle_tag.strip():
            return False, "BattleTag cannot be empty"
        
        battle_tag = battle_tag.strip()
        
        # Check basic format: 3-12 letters + # + 4-12 digits
        pattern = r'^[A-Za-z]{3,12}#[0-9]{4,12}$'
        if not re.match(pattern, battle_tag):
            return False, "BattleTag must be in format: 3-12 letters + # + 4-12 digits (e.g., Username#1234)"
        
        # Additional validation
        parts = battle_tag.split('#')
        username = parts[0]
        numbers = parts[1]
        
        # Check username length
        if len(username) < 3 or len(username) > 12:
            return False, "Username part must be 3-12 characters"
        
        # Check numbers length
        if len(numbers) < 4 or len(numbers) > 12:
            return False, "Numbers part must be 4-12 digits"
        
        # Check for reserved usernames
        reserved_usernames = ['admin', 'moderator', 'mod', 'bot', 'discord', 'blizzard', 'battle']
        if username.lower() in reserved_usernames:
            return False, "This username is reserved and cannot be used"
        
        return True, None

    def validate_alt_ids(self, alt_ids: str, allow_international: bool = True) -> Tuple[bool, Optional[str], List[str]]:
        """
        Validate alternative IDs.
        
        Args:
            alt_ids: Comma-separated string of alternative IDs
            allow_international: If True, allows international characters in alt IDs
            
        Returns:
            Tuple of (is_valid, error_message, parsed_ids)
        """
        if not alt_ids or not alt_ids.strip():
            return True, None, []
        
        # Split and clean the IDs
        parsed_ids = [aid.strip() for aid in alt_ids.split(',') if aid.strip()]
        
        if not parsed_ids:
            return True, None, []
        
        # Check for duplicates
        if len(parsed_ids) != len(set(parsed_ids)):
            return False, "Duplicate alternative IDs are not allowed", []
        
        # Limit number of alt IDs
        if len(parsed_ids) > 5:
            return False, "Maximum 5 alternative IDs allowed", []
        
        # Validate each ID with international character support
        for i, alt_id in enumerate(parsed_ids):
            is_valid, error = self.validate_user_id(alt_id, allow_international=allow_international)
            if not is_valid:
                return False, f"Alternative ID #{i+1}: {error}", []
        
        return True, None, parsed_ids
