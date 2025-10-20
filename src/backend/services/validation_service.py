"""
Validation service for user input validation.
"""
import re
from typing import Tuple, Optional, List


class ValidationService:
    """Service for validating user input data."""
    
    def validate_user_id(self, user_id: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a user ID
        
        Args:
            user_id: The user ID to validate
            
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
        
        # Check for valid characters (alphanumeric and common gaming characters)
        if not re.match(r'^[A-Za-z0-9_-]+$', user_id):
            return False, "User ID can only contain letters, numbers, underscores, and hyphens"
        
        # Check for reserved words or inappropriate content
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

    def validate_alt_ids(self, alt_ids: str) -> Tuple[bool, Optional[str], List[str]]:
        """
        Validate alternative IDs
        
        Args:
            alt_ids: Comma-separated string of alternative IDs
            
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
        
        # Validate each ID using the existing validate_user_id function
        for i, alt_id in enumerate(parsed_ids):
            is_valid, error = self.validate_user_id(alt_id)
            if not is_valid:
                return False, f"Alternative ID #{i+1}: {error}", []
        
        return True, None, parsed_ids
