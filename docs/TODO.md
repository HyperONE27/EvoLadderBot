## PRE-ALPHA

### Account Configuration
- ⏰ Update Terms of Service for closed alpha/open beta stage
- ✅ Fix country setup descriptions for XX (nonrepresenting) / ZZ (other)
- ✅ /setup persists pre-existing values as defaults (so you don't have to fill them all out again to change one thing)
- ✅ nulling of alt names is properly recorded in action logs table

### Admin & Monitoring
- ⏰ Add automatic logging/pinging of admins when a match disagreement arises
  - ⏰ Send replay data to admins
- ⏰ Add an interface to allow admins to view conflicts in matches and resolve with 1 click

### Core Architecture & Performance
- ✅ Complete DataAccessService migration from legacy db_reader/db_writer pattern
- ✅ In-memory hot tables using Polars DataFrames for sub-millisecond reads
- ✅ Asynchronous write-back queue for non-blocking database operations
- ✅ Singleton pattern ensuring consistent data access across application
- ✅ Service dependency injection with app_context.py
- ✅ Performance monitoring with comprehensive timing and memory tracking
- ✅ 99%+ performance improvement across all critical operations
  - ✅ Rank lookup: 280-316ms → 0.00ms (99.9% improvement)
  - ✅ Player info lookups: 500-800ms → <2ms (99.7% improvement)
  - ✅ Abort count lookups: 400-600ms → <2ms (99.5% improvement)
  - ✅ Match data lookups: 200-300ms → <2ms (99% improvement)
  - ✅ Embed generation: 400-500ms → <50ms (90% improvement)

### Critical Bug Fixes
- ✅ Leaderboard ranks: Fixed missing rank calculations and display
- ✅ Match result calculation: Corrected player report interpretation (0=draw, 1=P1 wins, 2=P2 wins)
- ✅ Abort flow: Fixed "Aborted by Unknown", queue lock releases, and race conditions
- ✅ Replay database writes: Fixed missing uploaded_at field and replay update handlers
- ✅ MMR updates: Fixed in-memory MMR updates and frontend display
- ✅ Player names: Fixed leaderboard displaying "PlayerUnknown" → actual player names
- ✅ Shared replay views: Fixed players seeing each other's replay status
- ✅ Graceful shutdown: Fixed event loop conflicts and task cancellation
- ✅ Error handling: Removed all fallback values, promoting explicit error handling
- ✅ Database consistency: Fixed schema mismatches and missing field handlers

### Database & Infrastructure
- ✅ Define PostgreSQL schema
- ✅ Full migrate to PostgreSQL
  - ✅ Hybrid architecture with SQLAlchemy adapter allows local testing with SQLite and remote host testing with PostgresSQL
- ✅ Store replays in separate persistent storage and not in SQL tables
- ✅ Optimize the shit out of PostgreSQL queries
  - ✅ Bundle queries
  - ✅ Change query types
- ✅ Implement spawning helper processes for replay parsing (multiprocessing with ProcessPoolExecutor)
  - ✅ Created parse_replay_data_blocking() worker function
  - ✅ Implemented global process pool with configurable workers
  - ✅ Updated on_message() to use run_in_executor()
  - ✅ Comprehensive test suite (6/6 tests passing)
  - ✅ Full documentation and demonstration scripts
- ✅ Implement service locator pattern for global service instances
- ✅ Migrate timestamps from TIMESTAMP to TIMESTAMPZ with explicit UTC declaration
  - ✅ Source-internal architecture continues to assume UTC

### Legacy Cleanup
- ✅ De-activate the outdated /activation command

### Matchmaking & Match Flow
- ⏰ Fill out the full cross-table for 16 regions
- ⏰ Get the matchmaker to correctly assign server based on the cross-table
- ✅ Add more information/clean up existing information on the match found embed
- ✅ Matchmaker now assigns matches in waves occurring every 45 seconds, up from 5, trading time for fairer matches
- ✅ Expanding MMR window for matchmaking scales dynamically with active player count and proportion of active player count 
- ✅ 99 race conditions on the wall, 99 race conditions, take one down, pass it around, 157 race conditions on the wall...
- ✅ Forbid queueing while a match is active, or queueing again while already queueing.
- ✅ Consolidated management of QueueSearchingView locks into a single class
- ⏰ FIGURE OUT HOW TO BALANCE LOW PING MATCHING WITH FAIREST MMR MATCHING
  - High MMR/top competitive players are used to playing across oceans and continents
  - Low MMR players just want to not fight the game
  - Tune the matchmaker to prefer low ping at lower MMR at expense of MMR fairness? Default to strict MMR fairness higher up??? Is this fair?

### Match Reporting & Completion
- ✅ Make the match reporting pipeline more robust
- ✅ Fix race conditions resulting in the first player to report match result not getting any updates
- ✅ Add replay uploading and storage to the database (no automatic parsing for now)
- ✅ Fix some lag associated with both players receiving confirmation of match results
- ✅ Fix the main embed being overwritten with an error embed when players report disagreeing match results
- ✅ Add an option to abort 3 matches a month. Aborting matches causes no MMR change.
  - ✅ Exceeding this count and throwing games/smurfing will result in bans.
- ✅ Fix the display of remaining abortions to players
- ✅ Match completion on backend is properly abstracted away from frontend
- ✅ Consolidated management of MatchFoundView locks into a single class

### MMR & Ranking System
- ✅ MMR is now ELO-like rather than classic ELO spec-compliant (divisor = 500 rather than 400; 100-point gap predicts a 62-38 win chance instead of 64-36)
- ✅ MMR is now integer-based rather than float-based
- ✅ MMR curve now more closely resembles that of Brood War
- ✅ Add dynamic rank calculations (S/A/B/C/D/E/F) to leaderboard and player profiles
- ✅ Add rank filter toggling
- ✅ Edit and add rank emotes

### Replay System
- ✅ Replays are now redirected to storage instead of being stored directly in tables
- ✅ Tables now store replay paths
- ✅ Move replays to a dedicated table and add pointer logic between tables
- ✅ Parse replays for basic info: players, player races, observers, map, timestamp, length, etc.
- ✅ Send a message to the user with this information when they upload a replay
- ❌ Update the MatchFoundViewEmbed with this information
  - ✅ Send a new embed message with this information

### System Hardening & Optimization
- ✅ No 60-second leaderboard refresh loop, invalidate cache specifically only when services modify MMR
- ✅ Remove synchronous leaderboard path (async path should not fall back to it)
- ⏰ Implement a smarter prune protection algorithm than using string matching
- ⏰ Implement frontend mock testing

### User Interface & Commands
- ✅ Command guard: Fully decoupled command guarding errors from frontend
- ✅ Add a /profile page to view one's own MMRs and settings
- ✅ Add flag emojis to country dropdowns in /setup (including XX and ZZ custom emotes)
- ✅ Add flag emojis to /setcountry confirmation embeds
- ❌ Implement action deferral? And add loading bars + disable UI while waiting
  - ✅ Removed all action deferral, since the bot is now so fast that deferral hurts UX

### MORE RANDOM BUGS???
- ⏰ Accepting ToS does not properly record having accepted

## PRE-BETA

- Command timeouts:
  - ⏰ Check that everything lasts as long as it needs to
- Gamemodes:
  - ⏰ Add support for no-party 2v2s
  - ⏰ Add support for forming parties
  - ⏰ Add support for party-okay 2v2s
- Localization:
  - ⏰ Add support for koKR and other languages
  - ⏰ Replace 1 million hardcoded formatted strings...sobbing

## PRE-RELEASE

- Account config:
  - ⏰ Create Paddle payment page
  - ⏰ Wire up Paddle 
  - ❌ Add columns to `players` table for managing subscription status
  - ⏰ Create a new `subscriptions` table to handle subscription status management