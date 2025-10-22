"""
Application context - centralized service locator pattern.

This module creates and configures singleton instances of all backend services.
All application code should import services from here rather than instantiating them directly.

This provides:
- Centralized service management
- Easy dependency wiring
- Consistent service instances across the application
- Simplified testing (can mock this module)

Usage:
    from src.backend.services.app_context import (
        user_info_service,
        command_guard_service,
        leaderboard_service
    )
"""

from src.backend.db.db_reader_writer import DatabaseReader, DatabaseWriter
from src.backend.services.command_guard_service import CommandGuardService
from src.backend.services.countries_service import CountriesService
from src.backend.services.leaderboard_service import LeaderboardService
from src.backend.services.maps_service import MapsService
from src.backend.services.match_completion_service import MatchCompletionService
from src.backend.services.matchmaking_service import matchmaker
from src.backend.services.mmr_service import MMRService
from src.backend.services.notification_service import initialize_notification_service
from src.backend.services.queue_service import initialize_queue_service
from src.backend.services.ranking_service import RankingService
from src.backend.services.races_service import RacesService
from src.backend.services.regions_service import RegionsService
from src.backend.services.replay_service import ReplayService
from src.backend.services.storage_service import StorageService
from src.backend.services.user_info_service import UserInfoService
from src.backend.services.validation_service import ValidationService


# =============================================================================
# DATABASE LAYER - Create shared reader/writer instances
# =============================================================================

# ⚠️  LEGACY WARNING: These instances are kept for backwards compatibility only.
# ⚠️  NEW CODE SHOULD USE DataAccessService INSTEAD:
# ⚠️  from src.backend.services.data_access_service import DataAccessService
# ⚠️  data_service = DataAccessService()
# ⚠️  DataAccessService provides in-memory data access with async write-back to DB.
# ⚠️  These legacy instances bypass the new architecture and should be avoided.

db_reader = DatabaseReader()
db_writer = DatabaseWriter()


# =============================================================================
# CORE SERVICES - Services with no dependencies or simple dependencies
# =============================================================================

# Static data services (no external dependencies)
countries_service = CountriesService()
regions_service = RegionsService()
races_service = RacesService()
maps_service = MapsService()

# Stateless utility services
mmr_service = MMRService()
validation_service = ValidationService()

# Storage service (uses config only)
storage_service = StorageService()

# Replay service (creates its own DatabaseWriter internally - legacy pattern)
replay_service = ReplayService()


# =============================================================================
# USER & PLAYER SERVICES - Services that manage user data
# =============================================================================

# User info service uses the shared db reader/writer
# Note: Currently creates its own in __init__, but we can pass them if refactored
user_info_service = UserInfoService()

# Command guard service uses user_info_service
command_guard_service = CommandGuardService(user_service=user_info_service)


# =============================================================================
# LEADERBOARD SERVICES - Services for rankings and leaderboards
# =============================================================================

# Ranking service for MMR-based percentile ranks
ranking_service = RankingService(db_reader=db_reader)

# Leaderboard service with injected dependencies
leaderboard_service = LeaderboardService(
    country_service=countries_service,
    race_service=races_service,
    db_reader=db_reader,
    ranking_service=ranking_service
)


# =============================================================================
# MATCHMAKING SERVICES - Already singletons, just reference them
# =============================================================================

# Matchmaker is already a singleton instance in matchmaking_service.py
# We import it directly above and expose it here for consistency
# matchmaker = matchmaker  # Already imported

# Match completion service is a singleton (uses __new__ pattern)
# Create the singleton instance
match_completion_service = MatchCompletionService()

# New event-driven matchmaking services
notification_service = initialize_notification_service()
queue_service = initialize_queue_service()


# =============================================================================
# EXPORTS - All services available for import
# =============================================================================

__all__ = [
    # Database layer
    "db_reader",
    "db_writer",
    # Static data services
    "countries_service",
    "regions_service",
    "races_service",
    "maps_service",
    # Utility services
    "mmr_service",
    "validation_service",
    "storage_service",
    "replay_service",
    # User services
    "user_info_service",
    "command_guard_service",
    # Leaderboard services
    "leaderboard_service",
    "ranking_service",
    # Matchmaking services
    "matchmaker",
    "match_completion_service",
    "notification_service",
    "queue_service",
]

