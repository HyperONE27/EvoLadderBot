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
            allow_international: If True, allows any characters. If False, only A-Z a-z allowed.
            
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
        
        # Enforce character restrictions based on allow_international flag
        if not allow_international:
            if not re.match(r'^[A-Za-z]{3,}$', user_id):
                return False, "Main ID must contain only English letters (A-Z, a-z) and be at least 3 characters long"
        
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
        
        # Check that it contains exactly one "#"
        if battle_tag.count('#') != 1:
            return False, "BattleTag must contain exactly one '#' separator"
        
        # Split into username and numbers parts
        parts = battle_tag.split('#')
        username = parts[0]
        numbers = parts[1]
        
        # Check username length (any characters allowed)
        if len(username) < 1 or len(username) > 12:
            return False, "Username part must be 1-12 characters"
        
        # Check numbers part (must be digits only)
        if not numbers.isdigit():
            return False, "Numbers part must contain only digits"
        
        # Check numbers length
        if len(numbers) < 3 or len(numbers) > 12:
            return False, "Numbers part must be 3-12 digits"
        
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
