## PRE-ALPHA

### Account Configuration
- ✅ Update Terms of Service for closed alpha/open beta stage
  - ✅ Create a Rentry/Github document for this and just link it
  - ✅ Create a page on official SC: Evo website
- ✅ Fix country setup descriptions for XX (nonrepresenting) / ZZ (other)
- ✅ /setup persists pre-existing values as defaults (so you don't have to fill them all out again to change one thing)
- ✅ nulling of alt names is properly recorded in action logs table

### Admin & Monitoring
- ✅ Add automatic logging/pinging of admins when a match disagreement arises
  - ✅ Send replay data to admins
- ✅ Add an interface to allow admins to view conflicts in matches and resolve with 1 click

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
- ✅ Fill out the full cross-table for 16 regions
- ✅ Get the matchmaker to correctly assign server based on the cross-table
- ✅ Add more information/clean up existing information on the match found embed
- ✅ Matchmaker now assigns matches in waves occurring every 45 seconds, up from 5, trading time for fairer matches
- ✅ Expanding MMR window for matchmaking scales dynamically with active player count and proportion of active player count 
- ✅ 99 race conditions on the wall, 99 race conditions, take one down, pass it around, 157 race conditions on the wall...
- ✅ Forbid queueing while a match is active, or queueing again while already queueing.
- ✅ Consolidated management of QueueSearchingView locks into a single class

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
- ✅ Check that uploaded replays comply with the match parameters
  - ✅ Throw a warning if the map link do not match exactly
  - ❌ Reject the replay outright if the wrong races are present

### System Hardening & Optimization
- ✅ No 60-second leaderboard refresh loop, invalidate cache specifically only when services modify MMR
- ✅ Remove synchronous leaderboard path (async path should not fall back to it)
- ❌ Implement a smarter prune protection algorithm than using string matching
  - ✅ Still using string matching but it's less stupid now
- ❓ Implement frontend mock testing
  - ✅ Characterization/regression tests including simulation of frontend flows but not true UI mocking

### User Interface & Commands
- ✅ Command guard: Fully decoupled command guarding errors from frontend
- ✅ Add a /profile page to view one's own MMRs and settings
- ✅ Add flag emojis to country dropdowns in /setup (including XX and ZZ custom emotes)
- ✅ Add flag emojis to /setcountry confirmation embeds
- ❌ Implement action deferral? And add loading bars + disable UI while waiting
  - ✅ Removed all action deferral, since the bot is now so fast that deferral hurts UX

### MORE RANDOM BUGS???
- ✅ Accepting ToS does not properly record having accepted (FIXED)

### Admin Commands
- Adjust MMR: ✅ Seems functional
  - ✅ MMR successfully updated
  - ✅ Player does not get a notification ([AdminCommand] Cannot send notification: bot instance not available)
- Clear Queue: ✅ Incomplete
  - ✅ Players are removed from the queue
  - ✅ Player does not get a notification ([AdminCommand] Cannot send notification: bot instance not available)
  - ✅ Player remains in queue-locked state, cannot queue again
- Player: ✅ Mostly functional
  - ✅ All information technically present and accounted for
  - ✅ Active Matches list needs to be pruned down
  - ✅ To be honest, this should just follow the formatting for the user /profile command, but with extra sections
- Snapshot: ✅ Functional
  - ✅ Info technically all present
  - ✅ Could/should include more detail about
    - Players in queue and their races
    - Ongoing matches and their IDs and players
    - A couple other metrics
- Match: ✅ Functional, but could use improvement
  - ✅ JSON payload is complete
  - ✅ Could use a guide for admins on how to interpret values
- Reset Aborts:
  - ✅ Abort count successfully updated
  - ✅ Player does not get a notification ([AdminCommand] Cannot send notification: bot instance not available)
  - ✅ Confirm embed does not show the old amount, only the complete embed does
- Resolve Match: ✅ Broken
  - ✅ Never recognizes a conflicted state
  - ✅ Should be able to resolve the match no matter what
- Remove Queue: ✅ Incomplete
  - ✅ Players are removed from the queue
  - ✅ Player does not get a notification ([AdminCommand] Cannot send notification: bot instance not available)
  - ✅ Player remains in queue-locked state, cannot queue again
- Needed additional features:
  - ✅ Match resolution must remove queue-locked state mid-match

### Other Last Minute Stuff
- ✅ Improve the matchmaking algorithm
  - ✅ Locally optimal solution instead of greedy matching
  - ⏰ Fill out pings in server cross-table
  - ⏰ Adjust matchmaking bias a little based on ping quality and fairness
- ✅ Send a follow-up message to players who do not confirm match in a third of the abort countdown timer after match assignment
- ✅ Send a dismissable message to players who enter a match involving BW Protoss about how to avoid Shield Battery lag
- ✅ I already updated admins.json with "owner" and "admin" roles, add an owner-only command to adjust admins while the bot is up

### MORE LAST MINUTE STUFF
- ✅ Figure out what cache handles fingerprint official SC: Evo Complete Extension mod
- ✅ Add cache handles column and cache handles check boolean to replays table
- ✅ Add functionality to replay parser to validate cache handles
- ✅ Add cache handle data to mods.json
- ✅ Add all needed emotes for the bot into test server
- ✅ Overwrite emotes in emotes.json
- ❌ Make admin commands DM-only???
- ✅ Actually, do send all match results to a dedicated channel
- ✅ Add the bot to the official server
- ⏰ Test and tidy up every command (DO LAST)
  - ❌ /help
    - ✅ Unregistered for now
  - ✅ /leaderboard
  - ⏰ /profile
  - ✅ /queue
  - ✅ /setcountry
  - ✅ /setup
  - ✅ /termsofservice
  - ✅ /admin adjust_mmr
  - ✅ /admin ban
  - ⏰ /admin snapshot
  - ✅ /admin clear_queue
  - ⏰ /admin match
  - ⏰ /admin player
  - ✅ /admin resolve
  - ✅ /admin remove_queue
  - ✅ /admin reset_aborts
  - ✅ /admin unblock_queue
  - ✅ /owner admin
- ✅ Clean up the /help command
- ✅ Check every command to add a "❌ Clear/Cancel" button to it

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
- Matchmaking:
  - ⏰ Add relative ping weights for each matchup in the cross-table
  - ⏰ More ping-aware algorithm to reduce bad matches at lower MMRs
  - ⏰ FIGURE OUT HOW TO BALANCE LOW PING MATCHING WITH FAIREST MMR MATCHING
    - ⏰ High MMR/top competitive players are used to playing across oceans and continents
    - ⏰ Low MMR players just want to not fight the game
    - ⏰ Tune the matchmaker to prefer low ping at lower MMR at expense of MMR fairness? Default to strict MMR fairness higher up??? Is this fair?
- Scaling:
  - Add extra API keys to handle Korean, Simplified Chinese, Spanish, Portugese, and German

## PRE-RELEASE

- Account config:
  - ⏰ Create Paddle payment page
  - ⏰ Wire up Paddle 
  - ❌ Add columns to `players` table for managing subscription status
  - ⏰ Create a new `subscriptions` table to handle subscription status management


  ===

Hi, all. Thanks for your ongoing patience and anticipation. The wait is almost over:
# The SC: Evo Complete ranked ladder OPEN ALPHA launches this calendar week (Pacific Time).

The core functionality for the alpha testing phase is already in place. I'm preparing a few final touches and tools so our bot team can quickly address any issues that occur during deployment without taking the bot down.
## You can expect the following:
- 🤖 **Automated Matchmaking:**
  - The alpha boasts full support for 1v1.
    - 2v2 and other gamemodes may be implemented for the beta testing phase and/or official release.
  - You can queue with **up to two races** at once: one from Brood War and one from StarCraft II.
  - Each of the six races has its **own separate MMR.**
  - We're fine-tuning matchmaking algorithm parameters:
    - During downtime, matches form quickly, even across wider skill gaps.
    - During peak activity, opponents will be matched more closely in MMR.
    - The matchmaker adjusts for players currently mid-match and those who have missed several rounds of matchmaking.
  - Beginning in the beta, we'll experiment with **ping-weighted matchmaking** at lower MMRs, prioritizing smoother connections over absolute MMR proximity.
- 🏆 **Global Leaderboard & Ranks**
  - Ranks will be determined based on percentiles (:SRank: :ARank: :BRank: :CRank: :DRank: :ERank: :FRank:) and displayed on a global leaderboard.
  - The leaderboard is filterable: you can view top players by race or country.
- ⚔️ **Match Experience**
  - The ladder bot automatically designates races, maps, and match settings based on player regions and preferences.
  - The bot assigns a dedicated in-game channel for each match to help you find your opponents more easily.
  - **Replay uploading** is required for match reporting:
    - The bot parses and stores replay records.
    - Due to technical limitations, reporting is manual for now — just click through a couple menus to confirm the winner.
    - Semi-automatic verification is planned for the beta and beyond.
  - **Mandatory match confirmation** ensures you're not stuck with an AFK opponent and can quickly queue again.
  - **Limited match abortion** provides flexibility in the rare occasion you have to end a session early.
- ⚖️ **Competitive Integrity**
  - As a community-run project, the SC: Evo Complete ladder can enforce standards of fairness and integrity long absent from the official ladder.
  - All bot interactions are logged and monitored for potential abuse.
  - All replays are stored permanently and can be retrieved for future review or analysis.
  - A dedicated team of volunteer admins will help investigate reports and uphold competitive integrity.
  
Please note:
- The alpha and beta testing phases will be free for all players, but the ladder will transition to a **low-cost paid subscription model** for the official release.
  - We want to ensure this cost is not a paywall, but a way to sustain what we’ve built together.
  - It goes toward everything that makes SC: Evo Complete great:
    - The servers that keep the ladder chugging.
    - The maps and modeling you admire for hours.
    - The tools that catch what breaks.
    - The admins who keep matches fair.
    - The developers who push update after update.
    - The prize pools that serious tournaments deserve.
  - We will strive to set the monthly cost as low as possible, at around **just a few dollars per month.**
- Player stats and MMR **may or may not be** reset closer to the official launch date.

This is an **alpha**, which means things **will** break! We're counting on your feedback to help us find and squash bugs, as well as report cheaters! We will have a dedicated channel for all reports.

Thanks for tuning in. I will see you later this week!