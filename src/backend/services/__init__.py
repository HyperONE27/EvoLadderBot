"""
Backend services package.

Exports singleton service instances for use throughout the application.
"""

# Re-export singleton instances from service_instances module
from src.backend.services.service_instances import (
    user_info_service,
    command_guard_service,
    countries_service,
    regions_service,
    races_service,
    maps_service,
    leaderboard_service,
    mmr_service,
    validation_service,
    replay_service,
)

__all__ = [
    'user_info_service',
    'command_guard_service',
    'countries_service',
    'regions_service',
    'races_service',
    'maps_service',
    'leaderboard_service',
    'mmr_service',
    'validation_service',
    'replay_service',
]

