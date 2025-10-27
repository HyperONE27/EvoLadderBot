"""
Shared type definitions for the backend services.

This module contains TypedDict definitions and other type annotations
that are used across multiple backend services.
"""

from typing import TypedDict


class VerificationResult(TypedDict):
    """
    Standardized result of all replay verification checks.
    
    Attributes:
        races_match: Whether the races in the replay match the assigned races
        map_match: Whether the map played matches the assigned map
        timestamp_match: Whether the game started within 20 minutes of assignment
        observers_match: Whether no unauthorized observers were present
    """
    races_match: bool
    map_match: bool
    timestamp_match: bool
    observers_match: bool

