"""
Application context for the bot, holding shared resources.
"""

from src.backend.db.db_connection import get_db_connection_url
from src.backend.db.connection_pool import ConnectionPool
from src.backend.db.db_reader_writer import Database
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
from src.backend.services.storage_service import StorageService
from src.bot.config import DATABASE_TYPE


class AppContext:
    """
    Holds the application's shared resources, such as the database
    connection pool and service instances.
    """

    def __init__(self):
        print("[AppContext] Initializing application context...")

        self.db_pool = None
        if DATABASE_TYPE == "postgresql":
            connection_url = get_db_connection_url()
            self.db_pool = ConnectionPool(connection_url)
            print("[AppContext] PostgreSQL connection pool created.")

        # The Database object now gets the pool passed to it
        self.db = Database(pool=self.db_pool)

        # Initialize services, injecting the database dependency
        print("[AppContext] Initializing services...")
        self.storage_service = StorageService()
        self.user_info_service = UserInfoService(self.db)
        self.command_guard_service = CommandGuardService(self.user_info_service)
        self.countries_service = CountriesService()
        self.regions_service = RegionsService()
        self.races_service = RacesService()
        self.maps_service = MapsService()
        self.leaderboard_service = LeaderboardService(
            db=self.db,
            country_service=self.countries_service,
            race_service=self.races_service,
        )
        self.mmr_service = MMRService()
        self.validation_service = ValidationService()
        self.replay_service = ReplayService(self.db, self.storage_service)
        print("[AppContext] All services initialized.")

    def close(self):
        """Clean up resources."""
        if self.db_pool:
            print("[AppContext] Closing database connection pool.")
            self.db_pool.close_all()
