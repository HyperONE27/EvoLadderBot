"""
Global singleton instances of backend services.

All services are initialized once at application startup to avoid
repeated instantiation overhead on every command.

Expected impact:
- Reduces object creation overhead
- Centralizes service management
- Enforces singleton pattern for stateful services
"""

from src.backend.services.user_info_service import UserInfoService
from src.backend.services.command_guard_service import CommandGuardService
from src.backend.services.countries_service import CountriesService
from src.backend.services.regions_service import RegionsService
from src.backend.services.races_service import RacesService
from src.backend.services.maps_service import MapsService
from src.backend.services.leaderboard_service import LeaderboardService
from src.backend.services.mmr_service import MMRService
from src.backend.services.validation_service import ValidationService
from src.backend.services.replay_service import ReplayService


# Initialize singleton instances once
print("[Services] Initializing singleton service instances...")

user_info_service = UserInfoService()
command_guard_service = CommandGuardService()
countries_service = CountriesService()
regions_service = RegionsService()
races_service = RacesService()
maps_service = MapsService()
leaderboard_service = LeaderboardService()
mmr_service = MMRService()
validation_service = ValidationService()
replay_service = ReplayService()

print("[Services] All singleton services initialized")

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

