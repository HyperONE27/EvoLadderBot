# Admin System: Complete Architecture Explanation

## HIGH LEVEL: What Admin Commands Should Do

Admin commands let authorized users inspect and modify the bot's live state:

```
[Admin Command] → [Inspect/Modify System State] → [Update All Affected Systems] → [Notify Players]
```

**Core Principle:** Admin actions must affect the REAL system state, not phantom/shadow copies.

### Command Categories:
1. **Inspection** (read-only) - View system state, player info, match details
2. **Modification** (controlled) - Adjust MMR, resolve conflicts, reset aborts  
3. **Emergency** (nuclear) - Clear queue, force remove players

---

## MID LEVEL: System Components and Connections

### The Systems That Need to Stay in Sync:

```
┌─────────────────────────────────────────────────────────────┐
│                      BOT STATE LAYERS                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. DATABASE (Supabase/PostgreSQL)                           │
│     - Persistent storage                                      │
│     - Updated async via write queue                           │
│                                                               │
│  2. IN-MEMORY DATAFRAMES (DataAccessService)                 │
│     - Hot cache for MMR, players, matches                    │
│     - Updated immediately on changes                          │
│                                                               │
│  3. MATCHMAKING QUEUE (Matchmaker.players)                   │
│     - Live list of queued players                            │
│     - Used by matching algorithm                             │
│                                                               │
│  4. QUEUE TRACKING (QueueService)                            │
│     - Secondary tracking for admin visibility                │
│     - Must stay synced with Matchmaker                       │
│                                                               │
│  5. RANKING CACHE (RankingService._rankings)                 │
│     - Calculated ranks for all player-race combos            │
│     - Refreshed when MMR/leaderboard changes                 │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Admin Command Flow (Fixed):

```
/admin adjust_mmr
       ↓
AdminService.adjust_player_mmr()
       ↓
   ┌───┴────────────────────────┐
   ↓                            ↓
DataAccessService         RankingService
   ↓                            ↓
Update MMR DF            Refresh rankings
   ↓                            
Queue DB write
```

```
/admin remove_queue
       ↓
AdminService.force_remove_from_queue()
       ↓
Matchmaker.remove_player()
       ↓
   ┌───┴────────────────────────┐
   ↓                            ↓
matchmaker.players       QueueService
(Real queue)            (Tracking)
```

### What Was Broken Before:

```
❌ OLD (BROKEN):
   /admin clear_queue → QueueService.clear_queue()
                           ↓
                    Cleared QueueService._queued_players
                           ↓
                    matchmaker.players UNTOUCHED
                           ↓
                    NO EFFECT ON MATCHMAKING!

✅ NEW (FIXED):
   /admin clear_queue → AdminService.emergency_clear_queue()
                           ↓
                    matchmaker.players.clear()
                           ↓
                    QueueService.clear_queue() (sync)
                           ↓
                    ACTUALLY CLEARS QUEUE!
```

---

## LOW LEVEL: Code Implementation Details

### Key Classes and Their Roles:

#### 1. **AdminService** (`src/backend/services/admin_service.py`)
**Role:** Facade for all admin operations. Ensures atomic updates across all systems.

**Key Methods:**
- `get_system_snapshot()` - Read-only inspection (safe)
- `get_player_full_state(discord_uid)` - Player debug info
- `adjust_player_mmr(discord_uid, race, operation, value)` - MMR modification
- `force_remove_from_queue(discord_uid)` - Queue removal
- `emergency_clear_queue()` - Nuclear queue clear
- `resolve_match_conflict(match_id, resolution)` - Conflict resolution

**Pattern:** Each method...
1. Validates input
2. Updates PRIMARY system (DataAccessService or Matchmaker)
3. Invalidates/refreshes dependent caches
4. Logs action to audit trail
5. Returns success/error dict

#### 2. **Matchmaker** (`src/backend/services/matchmaking_service.py`)
**Role:** Core matchmaking logic and queue management.

**Key State:**
```python
class Matchmaker:
    self.players: List[Player] = []  # THE REAL QUEUE
    self.lock: asyncio.Lock  # Thread safety
    self.recent_activity: Dict[int, float]  # Activity tracking
```

**Key Methods:**
```python
async def add_player(player: Player):
    # 1. Look up MMR from DataAccessService
    # 2. Add to self.players
    # 3. Sync to QueueService ← NEW!
    
async def remove_player(discord_user_id: int):
    # 1. Remove from self.players
    # 2. Sync to QueueService ← NEW!
    
async def is_player_in_queue(discord_user_id: int) -> bool:
    # Check if player in self.players
```

**Synchronization Added:**
Every add/remove now calls corresponding QueueService method to keep both in sync.

#### 3. **QueueService** (`src/backend/services/queue_service.py`)
**Role:** Secondary queue tracking for admin visibility and statistics.

**Key State:**
```python
class QueueService:
    self._queued_players: Dict[int, Player] = {}  # Tracking dict
    self._lock: asyncio.Lock
```

**Key Methods:**
```python
async def add_player(player: Player):
    self._queued_players[player.discord_user_id] = player
    
async def remove_player(player_id: int) -> bool:
    if player_id in self._queued_players:
        del self._queued_players[player_id]
        return True
    return False
    
async def clear_queue() -> int:
    count = len(self._queued_players)
    self._queued_players.clear()
    return count
```

**Note:** Now kept in sync by Matchmaker operations (never called directly by UI).

#### 4. **DataAccessService** (`src/backend/services/data_access_service.py`)
**Role:** Single source of truth for all persistent data (players, MMRs, matches).

**Key State:**
```python
class DataAccessService:
    self._players_df: pl.DataFrame  # In-memory player data
    self._mmrs_1v1_df: pl.DataFrame  # In-memory MMR data
    self._matches_1v1_df: pl.DataFrame  # In-memory match data
    self._write_queue: asyncio.Queue  # Async DB writes
```

**Update Pattern:**
1. Update in-memory DataFrame immediately (instant read visibility)
2. Queue async write to database (eventual consistency)
3. Write worker processes queue in background

#### 5. **RankingService** (`src/backend/services/ranking_service.py`)
**Role:** Calculate and cache rank assignments for all player-race combinations.

**Key State:**
```python
class RankingService:
    self._rankings: Dict[Tuple[int, str], Dict] = {}  # (discord_uid, race) → rank
    self._refresh_lock: Lock
```

**Refresh Trigger:**
Must be called when leaderboard changes (MMR adjustments, new games).

```python
await ranking_service.trigger_refresh()
```

---

## WHAT'S BEEN FIXED ✅

### 1. Queue Synchronization
- Matchmaker now syncs all add/remove operations to QueueService
- Admin commands use Matchmaker (not QueueService directly)
- `/admin clear_queue` and `/admin remove_queue` **now actually work**

### 2. Broken Method Calls
- Fixed `ranking_service.invalidate_player_rank()` → `trigger_refresh()`
- Fixed `ranking_service._rank_cache` → `_rankings`
- Fixed missing `await` on async QueueService methods

### 3. MMR Adjustment UX
- Added set/add/subtract operations (instead of only absolute values)
- Better confirmation previews
- Clearer success messages

### 4. Button Restrictions
- Admin command buttons restricted to the calling admin only
- Prevents accidental clicks by other admins

---

## WHAT STILL NEEDS TO BE DONE 🚧

### 1. Player Notifications (TODO)
When admin actions affect a player, they should receive a DM:

**Examples:**
```
🚨 Admin Action: You've been removed from the matchmaking queue.
Reason: Testing queue system
Admin: FuncR

📊 Admin Action: Your MMR has been adjusted.
Race: bw_zerg
Old MMR: 1500 → New MMR: 1550 (+50)
Reason: Compensation for server downtime
Admin: FuncR

⚖️ Match Resolved: Your match conflict has been resolved by an admin.
Match #12345: You vs Player2
Resolution: Draw
Admin: FuncR
```

**Implementation needed:**
- Add `_notify_player()` helper in AdminService
- Call after each player-affecting action
- Handle DM failures gracefully

### 2. Username Resolution (TODO)
Admin commands should accept usernames, not just IDs:

**Current:** `/admin remove_queue discord_id="218147282875318274"`  
**Desired:** `/admin remove_queue user="@FuncR"` or `/admin remove_queue user="FuncR"`

**Implementation needed:**
- Add `_resolve_user()` helper that looks up Discord ID from username/mention
- Update all admin command parameters to accept string user input
- Parse `<@123456>` mentions, `@username`, or plain `username`

### 3. Audit Other Commands (TODO)
Verify these commands connect to the right systems:
- ✅ `get_system_snapshot()` - Read-only, OK
- ✅ `get_player_full_state()` - Read-only, OK
- ✅ `get_match_full_state()` - Read-only, OK
- ✅ `resolve_match_conflict()` - Updates DB correctly
- ✅ `adjust_player_mmr()` - Updates DB + caches correctly
- ✅ `force_remove_from_queue()` - NOW FIXED
- ✅ `emergency_clear_queue()` - NOW FIXED
- ✅ `reset_player_aborts()` - Updates DB correctly

---

## SUMMARY

### What Was Wrong:
Admin commands were calling **phantom systems** (QueueService) that weren't connected to the real systems (Matchmaker).

### What's Been Fixed:
- Made Matchmaker and QueueService synchronize automatically
- Made admin commands target the real systems
- Fixed all broken method calls

### What's Next:
- Player notifications for admin actions
- Username resolution for easier admin use
- Full audit complete

The system now has a **single source of truth** for each component, with proper synchronization between layers.

