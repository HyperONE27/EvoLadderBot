"""
Shared type definitions for the backend services.

This module contains TypedDict definitions and other type annotations
that are used across multiple backend services.
"""

from typing import TypedDict, List, Set, Optional


class RaceVerificationDetail(TypedDict):
    """Detailed result of race verification check."""
    success: bool
    expected_races: Set[str]
    played_races: Set[str]


class MapVerificationDetail(TypedDict):
    """Detailed result of map verification check."""
    success: bool
    expected_map: str
    played_map: str


class TimestampVerificationDetail(TypedDict):
    """Detailed result of timestamp verification check."""
    success: bool
    time_difference_minutes: Optional[float]  # Negative if match started before assignment, positive if after
    error: Optional[str]


class ObserverVerificationDetail(TypedDict):
    """Detailed result of observer verification check."""
    success: bool
    observers_found: List[str]


class GameSettingVerificationDetail(TypedDict):
    """Detailed result of a single game setting verification check."""
    success: bool
    expected: str
    found: str


class ModVerificationDetail(TypedDict):
    """Detailed result of mod cache handle verification check."""
    success: bool
    message: str
    region_detected: Optional[str]


class VerificationResult(TypedDict):
    """
    Standardized result of all replay verification checks with rich context.
    
    Attributes:
        races: Detailed race verification result
        map: Detailed map verification result
        timestamp: Detailed timestamp verification result
        observers: Detailed observer verification result
        game_privacy: Detailed game privacy verification result
        game_speed: Detailed game speed verification result
        game_duration: Detailed game duration verification result
        locked_alliances: Detailed locked alliances verification result
        mod: Detailed mod validation result
    """
    races: RaceVerificationDetail
    map: MapVerificationDetail
    timestamp: TimestampVerificationDetail
    observers: ObserverVerificationDetail
    game_privacy: GameSettingVerificationDetail
    game_speed: GameSettingVerificationDetail
    game_duration: GameSettingVerificationDetail
    locked_alliances: GameSettingVerificationDetail
    mod: ModVerificationDetail

