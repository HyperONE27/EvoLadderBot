# Comprehensive Implementation Guide: Performance & Architecture Overhaul

**Status**: 📝 DRAFT  
**Date**: October 20, 2025

---

## 1. Introduction & Goals

This document provides a highly detailed, step-by-step guide for implementing the performance and architectural overhaul. It expands upon `PERFORMANCE_OVERHAUL_PLAN_V2.md` with specific code, architectural justifications, and a clear rationale for each change.

The two primary goals are:
1.  **Solve Performance Bottlenecks**: By implementing a database connection pool.
2.  **Improve Architectural Quality**: By refactoring the application from a Service Locator pattern to true Dependency Injection (DI), enhancing testability and maintainability.

---

## 2. Phase 1: Database Connection Pooling

This phase is purely an internal enhancement to the data access layer. It is designed to be completely invisible to the rest of the application, perfectly demonstrating the power of the existing adapter abstraction.

### Task 1.1: Create the Connection Pool Manager

**File Location**: `src/backend/db/connection_pool.py`

**Justification**: This is a low-level database utility. Its sole purpose is to manage PostgreSQL connections. Placing it in `src/backend/db/` puts it alongside the other core database components it serves, like the adapters and the `db_connection` module.

**Implementation**:
This module will create a `ConnectionPool` class and a singleton instance that can be initialized, accessed, and closed by the application's lifecycle events.

```python
# src/backend/db/connection_pool.py

"""
Manages a singleton PostgreSQL connection pool for the application.
"""

from typing import Optional
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager

# This global variable will hold the single pool instance.
_global_pool: Optional[pool.SimpleConnectionPool] = None

def initialize_pool(dsn: str, min_conn: int = 2, max_conn: int = 15):
    """
    Initializes the global connection pool. Should be called once at startup.
    """
    global _global_pool
    if _global_pool is not None:
        print("[DB Pool] WARNING: Pool already initialized.")
        return

    try:
        print(f"[DB Pool] Initializing pool (min={min_conn}, max={max_conn})...")
        _global_pool = pool.SimpleConnectionPool(
            minconn=min_conn,
            maxconn=max_conn,
            dsn=dsn
        )
        print("[DB Pool] Connection pool initialized successfully.")
    except psycopg2.OperationalError as e:
        print(f"[DB Pool] FATAL: Failed to initialize connection pool: {e}")
        _global_pool = None
        raise

@contextmanager
def get_connection():
    """
    Provides a managed connection from the pool.
    Usage:
        with get_connection() as conn:
            # use conn
    """
    if _global_pool is None:
        raise RuntimeError("Database connection pool has not been initialized.")
    
    conn = None
    try:
        conn = _global_pool.getconn()
        yield conn
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            _global_pool.putconn(conn)

def close_pool():
    """
    Closes all connections in the pool. Should be called at shutdown.
    """
    global _global_pool
    if _global_pool:
        print("[DB Pool] Closing all connections in the pool...")
        _global_pool.closeall()
        _global_pool = None
        print("[DB Pool] Connection pool closed.")
```

### Task 1.2: Refactor the `PostgreSQLAdapter`

**File Location**: `src/backend/db/adapters/postgresql_adapter.py`

**Justification**: The adapter's role is to abstract away the specifics of a database's connection and query syntax. By modifying *only* this file, we honor that abstraction. The `DatabaseReader` and `DatabaseWriter` will continue to use the adapter's `get_connection` method, completely unaware of the pooling mechanism beneath. This is an internal optimization of the PostgreSQL implementation detail.

**Implementation**: We will replace the expensive `psycopg2.connect()` call with our new pooled connection manager.

```python
# src/backend/db/adapters/postgresql_adapter.py

# ... other imports ...
from contextlib import contextmanager
# Import our new pooled connection manager
from src.backend.db.connection_pool import get_connection as get_pooled_connection

class PostgreSQLAdapter(DatabaseAdapter):
    # ... __init__ and other methods remain the same ...

    @contextmanager
    def get_connection(self):
        """
        Gets a PostgreSQL database connection from the pool.
        This method's signature and behavior remain consistent with the base adapter.
        """
        # The core change is here. Instead of creating a new connection,
        # we borrow one from the pool. The context manager from the pool
        # handles all the try/finally/commit/rollback/putconn logic.
        with get_pooled_connection() as conn:
            yield conn

    # ... all other methods (execute_query, etc.) remain the same ...
    # They will now automatically use the pooled connection via the above method.
```

---

## 3. Phase 2: Dependency Injection (DI)

This is a significant architectural refactor. We are moving from a "Service Locator" pattern (where components implicitly pull in global singletons via imports) to Dependency Injection (where dependencies are explicitly passed in).

### Task 2.1: Centralize Service Instantiation

**File Location**: `src/bot/app_context.py`

**Justification**: While we are moving to DI, we still want a single instance of each service for the application's lifetime. This file will be the canonical source for creating these instances. It acts as a manifest of all available services, defining the application's shared "context." Placing it in the `bot` directory is appropriate as it's a high-level component responsible for constructing the application's object graph, which is initiated by the bot's main entry point.

**Implementation**: This file will instantiate each service. In a later step, we will refactor the services themselves to accept dependencies, and this file is where we will wire them together.

```python
# src/bot/app_context.py

"""
Creates and configures the singleton instances of all backend services.
This acts as the dependency configuration for the application.
"""

from src.backend.db.db_reader_writer import DatabaseReader, DatabaseWriter
from .user_info_service import UserInfoService
from .command_guard_service import CommandGuardService
# ... import all other service classes ...

# First, create the lowest-level dependencies
db_reader = DatabaseReader()
db_writer = DatabaseWriter()

# Now, create services and inject their dependencies
user_info_service = UserInfoService(reader=db_reader, writer=db_writer)
command_guard_service = CommandGuardService(user_info_service=user_info_service)
# ... instantiate other services, injecting their dependencies ...
```

### Task 2.2: Refactor Services to Accept Dependencies

**File Location**: `src/backend/services/*.py`

**Justification**: This is the core of making services testable and loosely coupled. Instead of creating their own `DatabaseReader`, they will now accept it as a dependency.

**Implementation (Example: `UserInfoService`)**:

```python
# src/backend/services/user_info_service.py (BEFORE)

from src.backend.db.db_reader_writer import DatabaseReader, DatabaseWriter

class UserInfoService:
    def __init__(self) -> None:
        self.reader = DatabaseReader() # Creates its own dependency
        self.writer = DatabaseWriter() # Creates its own dependency
    
    # ... methods ...
```

```python
# src/backend/services/user_info_service.py (AFTER)

from src.backend.db.db_reader_writer import DatabaseReader, DatabaseWriter

class UserInfoService:
    def __init__(self, reader: DatabaseReader, writer: DatabaseWriter):
        self.reader = reader # Accepts dependency
        self.writer = writer # Accepts dependency

    # ... methods ...
```

### Task 2.3: Refactor Command Handlers to Classes

**File Location**: `src/bot/interface/commands/*.py`

**Justification**: To use DI, the command logic needs a place to receive its dependencies. A class with a constructor (`__init__`) is the perfect place. The class encapsulates the command's logic and its dependencies, creating a self-contained, testable unit.

**Implementation (Example: `profile_command.py`)**:

```python
# src/bot/interface/commands/profile_command.py (BEFORE)

from src.backend.services import user_info_service, command_guard_service
# ... other imports ...

async def profile_command(interaction: discord.Interaction):
    # logic uses global singletons
    player = command_guard_service.ensure_player_record(...)
    player_data = user_info_service.get_player(...)
    # ...
```

```python
# src/bot/interface/commands/profile_command.py (AFTER)

from src.backend.services.user_info_service import UserInfoService
from src.backend.services.command_guard_service import CommandGuardService
# ... other imports ...

class ProfileCommand:
    def __init__(self, user_info_service: UserInfoService, command_guard_service: CommandGuardService):
        # Dependencies are injected and stored
        self.user_info_service = user_info_service
        self.command_guard_service = command_guard_service

    async def handle(self, interaction: discord.Interaction):
        # Logic now uses instance variables
        player = self.command_guard_service.ensure_player_record(...)
        player_data = self.user_info_service.get_player(...)
        # ...

# The registration function is updated to accept the class instance
def register_profile_command(tree: app_commands.CommandTree, profile_command: ProfileCommand):
    @tree.command(name="profile", description="View your player profile")
    async def profile(interaction: discord.Interaction):
        await profile_command.handle(interaction)
```

### Task 2.4: Create the Composition Root

**File Location**: `src/bot/interface/interface_main.py`

**Justification**: This is the main entry point of the application, and it is the single, ideal place to "compose" the application's object graph. Here, we will create all our service instances and inject them into the command handlers that need them. This makes the application's entire dependency structure visible and manageable in one file.

**Implementation**:

```python
# src/bot/interface/interface_main.py

# ... other discord imports ...

# 1. Import all the singleton service instances from the new app_context
from .app_context import (
    user_info_service,
    command_guard_service,
    leaderboard_service,
    # ... and so on
)

# 2. Import the command classes and their registration functions
from .commands.profile_command import ProfileCommand, register_profile_command
from .commands.leaderboard_command import LeaderboardCommand, register_leaderboard_command
# ... and so on for all commands

# ... bot setup ...

def register_commands(bot: commands.Bot):
    # === COMPOSITION ROOT ===
    # This is where we wire everything together.

    # 3. Instantiate command handlers, injecting dependencies
    profile_command = ProfileCommand(
        user_info_service=user_info_service,
        command_guard_service=command_guard_service
    )
    leaderboard_command = LeaderboardCommand(
        leaderboard_service=leaderboard_service,
        command_guard_service=command_guard_service
    )
    # ... instantiate all other command handlers ...

    # 4. Pass the instances to the registration functions
    register_profile_command(bot.tree, profile_command)
    register_leaderboard_command(bot.tree, leaderboard_command)
    # ... register all other commands ...

if __name__ == "__main__":
    # --- Application Lifecycle Management ---
    
    # Initialize the connection pool at startup
    initialize_pool(dsn=DATABASE_URL)
    
    # ... rest of startup logic (testing connection, running bot) ...

    try:
        bot.run(EVOLADDERBOT_TOKEN)
    finally:
        # Gracefully close the pool at shutdown
        close_pool()
```

This comprehensive approach ensures that the performance issues are solved while simultaneously paying down technical debt and setting the project up for a more maintainable and testable future.

---

## 4. Phase 3: Streamlining the Application Entry Point

**Justification**: The `interface_main.py` file should serve as a minimal entry point. Currently, it's cluttered with responsibilities that can be delegated, such as bot subclassing, lifecycle management for resource pools (database and processes), and event handling. By abstracting this logic into a dedicated module, we improve separation of concerns, making the application easier to understand and maintain.

### Task 3.1: Create a Bot Lifecycle and Configuration Module

**File Location**: `src/bot/bot_setup.py`

**Justification**: This new module will become the central place for configuring the bot instance and managing its lifecycle. It will handle the creation and teardown of shared resources like connection pools and process pools, and it will attach global event listeners. This isolates setup logic from the application's main execution script.

**Implementation**:
This file will define our custom `EvoLadderBot` class and contain functions to initialize and shut down the application's resources.

```python
# src/bot/bot_setup.py

import sys
import asyncio
import discord
from discord.ext import commands
from concurrent.futures import ProcessPoolExecutor

from src.bot.config import WORKER_PROCESSES, DATABASE_URL
from src.backend.db.connection_pool import initialize_pool, close_pool
from src.backend.db.test_connection_startup import test_database_connection
from src.backend.services.cache_service import static_cache
from src.backend.db.db_reader_writer import DatabaseWriter

class EvoLadderBot(commands.Bot):
    """Custom bot class to attach resources and handle global events."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.process_pool: ProcessPoolExecutor = None

    async def on_interaction(self, interaction: discord.Interaction):
        """A global listener for all interactions to log command calls."""
        if interaction.type == discord.InteractionType.application_command:
            command_name = interaction.command.name if interaction.command else "unknown"
            user = interaction.user
            # We instantiate the writer here to ensure it's fresh for each event
            db_writer = DatabaseWriter()
            db_writer.insert_command_call(
                discord_uid=user.id,
                player_name=user.name,
                command=command_name
            )
        
        # Important: ensure default behavior is still processed
        await super().on_interaction(interaction)

def initialize_bot_resources(bot: EvoLadderBot):
    """Initializes and attaches all necessary resources for the bot."""
    print("[Startup] Initializing application resources...")
    
    # 1. Initialize Database Pool
    initialize_pool(dsn=DATABASE_URL)
    
    # 2. Test DB Connection
    success, message = test_database_connection()
    if not success:
        print(f"\n[FATAL] Database connection test failed: {message}")
        sys.exit(1)
        
    # 3. Initialize Static Cache
    try:
        static_cache.initialize()
    except Exception as e:
        print(f"\n[FATAL] Failed to initialize static data cache: {e}")
        sys.exit(1)
        
    # 4. Create and Attach Process Pool
    bot.process_pool = ProcessPoolExecutor(max_workers=WORKER_PROCESSES)
    print(f"[INFO] Initialized Process Pool with {WORKER_PROCESSES} worker process(es)")

def shutdown_bot_resources(bot: EvoLadderBot):
    """Gracefully shuts down all application resources."""
    print("[Shutdown] Closing application resources...")
    
    # 1. Close Database Pool
    close_pool()
    
    # 2. Shutdown Process Pool
    if bot.process_pool:
        bot.process_pool.shutdown(wait=True)
    
    print("[Shutdown] All resources closed.")
```

### Task 3.2: Refactor `interface_main.py` to be a Minimal Launcher

**File Location**: `src/bot/interface/interface_main.py`

**Justification**: With the setup and lifecycle logic moved, this file becomes a clean, readable entry point. Its only job is to compose the application and run it.

**Implementation**: The file is drastically simplified. It imports the configured bot class, creates an instance, wires up the command handlers, and runs the bot within the managed lifecycle.

```python
# src/bot/interface/interface_main.py (AFTER)

import asyncio
import discord
from discord.ext import commands

from src.bot.config import EVOLADDERBOT_TOKEN
from src.bot.bot_setup import EvoLadderBot, initialize_bot_resources, shutdown_bot_resources
from src.backend.services.matchmaking_service import matchmaker
from .commands.queue_command import on_message as handle_replay_message

# 1. Import all singleton service instances from the app_context
from .app_context import (
    user_info_service, command_guard_service, leaderboard_service # ... etc
)

# 2. Import command classes and their registration functions
from .commands.profile_command import ProfileCommand, register_profile_command
from .commands.leaderboard_command import LeaderboardCommand, register_leaderboard_command
# ... and so on for all commands

# Define intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

# Create bot instance
bot = EvoLadderBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot online as {bot.user}")
    try:
        register_commands(bot)
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
        asyncio.create_task(matchmaker.run())
        print("Matchmaker started")
    except Exception as e:
        print("Sync failed:", e)

@bot.event
async def on_message(message):
    await handle_replay_message(message, bot)

def register_commands(bot: commands.Bot):
    # === COMPOSITION ROOT ===
    profile_command = ProfileCommand(
        user_info_service=user_info_service,
        command_guard_service=command_guard_service
    )
    leaderboard_command = LeaderboardCommand(
        leaderboard_service=leaderboard_service,
        command_guard_service=command_guard_service
    )
    # ... instantiate all other command handlers ...

    register_profile_command(bot.tree, profile_command)
    register_leaderboard_command(bot.tree, leaderboard_command)
    # ... register all other commands ...

if __name__ == "__main__":
    initialize_bot_resources(bot)
    try:
        bot.run(EVOLADDERBOT_TOKEN)
    finally:
        shutdown_bot_resources(bot)
```

This refactoring further enhances the architectural quality by adhering to the Single Responsibility Principle for the application's main entry point.

---

## 5. Phase 4: Refactor Redundant Logic in `UserInfoService`

**Justification**: The `user_info_service.py` module contains repetitive code for determining a player's display name, which is primarily used for logging. This violates the DRY (Don't Repeat Yourself) principle. Centralizing this logic into a single helper method makes the code cleaner, easier to maintain, and less prone to inconsistencies.

### Task 4.1: Consolidate Display Name Logic

**File Location**: `src/backend/services/user_info_service.py`

**Implementation**:
1.  Create a new private helper method within the `UserInfoService` class.
2.  Replace all occurrences of the repeated logic with a call to this new method.

```python
# src/backend/services/user_info_service.py

from src.backend.db.db_reader_writer import DatabaseReader, DatabaseWriter
from typing import Dict, Any

class UserInfoService:
    def __init__(self, reader: DatabaseReader, writer: DatabaseWriter):
        self.reader = reader # Accepts dependency
        self.writer = writer # Accepts dependency

    def _get_player_display_name(self, player: Dict[str, Any]) -> str:
        """Gets the best available display name for a player for logging."""
        if not player:
            return "Unknown"
        return (player.get("player_name") 
                or player.get("discord_username") 
                or "Unknown")

    def update_country(self, discord_uid: int, country: str) -> bool:
        player = self.get_player(discord_uid)
        old_country = player.get("country") if player else None
        
        success = self.writer.update_player_country(discord_uid, country)
        
        if success and player:
            # REFACTOR: Use the new helper method
            player_name = self._get_player_display_name(player)
            self.writer.log_player_action(
                discord_uid=discord_uid,
                player_name=player_name,
                setting_name="country",
                old_value=old_country,
                new_value=country
            )
        
        return success

    # ... apply the same refactoring to other methods like submit_activation_code,
    # accept_terms_of_service, and decrement_aborts ...
```

---

## 6. Phase 5: Decouple UI (Embeds) from Command Logic

**Justification**: The `profile_command.py` module currently contains a large, complex function (`create_profile_embed`) responsible for building the UI. This mixes presentation logic directly with command handling logic, making the file difficult to read, maintain, and test. Separating these concerns improves modularity and aligns with best practices for software architecture.

### Task 5.1: Create a Dedicated Embed Module

**File Location**: `src/bot/interface/components/profile_embed.py` (new file)

**Justification**: Creating a dedicated file for embed generation separates UI logic from command logic. Placing it in the existing `components` directory keeps all UI-related code organized together, avoiding the creation of new folders.

**Implementation**:
1.  Create the new file `src/bot/interface/components/profile_embed.py`.
2.  Move the `create_profile_embed` function from `profile_command.py` into this new file.
3.  Move any imports required *only* by the embed function (e.g., `get_race_emote`, `get_flag_emote`) into the new file as well.

```python
# src/bot/interface/components/profile_embed.py

import discord
from src.backend.services.countries_service import CountriesService
from src.backend.services.regions_service import RegionsService
from src.backend.services.races_service import RacesService
from src.bot.utils.discord_utils import get_race_emote, get_flag_emote, get_game_emote

# Instantiate services needed only for the embed
countries_service = CountriesService()
regions_service = RegionsService()
races_service = RacesService()

def create_profile_embed(user: discord.User, player_data: dict, mmr_data: list) -> discord.Embed:
    """Create an embed displaying player profile information."""
    # ... entire function implementation from profile_command.py ...
```

### Task 5.2: Refactor the Profile Command

**File Location**: `src/bot/interface/commands/profile_command.py`

**Implementation**: Update the command file to import the embed-creation function from its new location. The command file becomes much shorter and is now focused solely on handling the interaction and fetching data.

```python
# src/bot/interface/commands/profile_command.py (AFTER)

import discord
from discord import app_commands
from src.backend.services.command_guard_service import CommandGuardService, CommandGuardError
from src.backend.services.user_info_service import UserInfoService
from src.backend.db.db_reader_writer import DatabaseReader
from src.bot.utils.discord_utils import send_ephemeral_response
from src.bot.interface.components.command_guard_embeds import create_command_guard_error_embed
# Import the decoupled embed function
from src.bot.interface.components.profile_embed import create_profile_embed

guard_service = CommandGuardService()
user_info_service = UserInfoService()
db_reader = DatabaseReader()

async def profile_command(interaction: discord.Interaction):
    # ... data fetching logic remains the same ...
    
    # Create profile embed by calling the imported function
    embed = create_profile_embed(interaction.user, player_data, mmr_data)
    
    await send_ephemeral_response(interaction, embed=embed)

# ... registration logic remains the same ...
```