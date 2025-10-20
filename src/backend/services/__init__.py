"""
This file initializes all backend services as singletons.

By importing services from this module, you ensure that only one instance of each
service is created and used throughout the application's lifecycle. This reduces
object creation overhead and provides a centralized place to manage all services.
"""

from .countries_service import CountriesService
from .leaderboard_service import LeaderboardService
from .localization_service import LocalizationService
from .maps_service import MapsService
from .match_completion_service import MatchCompletionService
from .matchmaking_service import Matchmaker
from .mmr_service import MMRService
from .races_service import RacesService
from .regions_service import RegionsService
from .replay_service import ReplayService
from .user_info_service import UserInfoService
from .validation_service import ValidationService
from .command_guard_service import CommandGuardService


# --- Initialize all services as singletons ---

countries_service = CountriesService()
leaderboard_service = LeaderboardService()
localization_service = LocalizationService()
maps_service = MapsService()
match_completion_service = MatchCompletionService() # This service runs its own loop
matchmaker = Matchmaker()
mmr_service = MMRService()
races_service = RacesService()
regions_service = RegionsService()
replay_service = ReplayService()
user_info_service = UserInfoService()
validation_service = ValidationService()
command_guard_service = CommandGuardService()

print("[Services] All backend services initialized as singletons.")
