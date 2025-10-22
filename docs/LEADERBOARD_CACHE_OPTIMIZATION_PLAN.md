# Leaderboard Cache Optimization Plan

## Strategy Overview

**Key Insight:** The leaderboard cache already contains ALL mmrs_1v1 data (discord_uid, race, mmr, last_played) plus player info (country, player_name) in a Polars DataFrame that's kept fresh every 60 seconds by background processes.

**Impact:** This cache can completely eliminate 500-800ms DB queries for MMR lookups!

## Current Cache Data Structure

The `_leaderboard_cache["dataframe"]` contains:
```python
{
    "player_id": str,        # player_name
    "mmr": float,            # MMR value
    "race": str,             # race code (e.g., 'bw_terran', 'sc2_zerg')
    "country": str,          # country code
    "discord_uid": int,      # Discord user ID
    "rank": str,             # pre-computed rank (e.g., 's_rank', 'a_rank')
    "last_played": str       # ISO timestamp
}
```

**This is EXACTLY what we need for:**
1. MMR lookups in `add_player()` - Currently 400-550ms → Will be <5ms
2. Player info lookups in `get_embed()` - Currently 500-800ms → Will be <5ms
3. Abort count lookups - Need to add this to cache or create separate cache

## What Needs to Change

### 1. Add Helper Methods to LeaderboardService

**New methods:**
```python
def get_player_mmr_from_cache(
    self,
    discord_uid: int,
    race: str
) -> Optional[float]:
    """Get player's MMR for a race from cache."""
    
def get_player_info_from_cache(
    self,
    discord_uid: int
) -> Optional[Dict]:
    """Get player info (name, country) from cache."""
    
def get_player_all_mmrs_from_cache(
    self,
    discord_uid: int
) -> Dict[str, float]:
    """Get all MMRs for a player across all races."""
```

### 2. Replace DB Queries with Cache Lookups

#### In `matchmaking_service.py` - `add_player()` method:
**BEFORE (400-550ms):**
```python
for race in player.preferences.selected_races:
    mmr_data = await loop.run_in_executor(
        None,
        self.db_reader.get_player_mmr_1v1,
        player.discord_user_id,
        race
    )
```

**AFTER (<5ms):**
```python
from src.backend.services.app_context import leaderboard_service

for race in player.preferences.selected_races:
    mmr = leaderboard_service.get_player_mmr_from_cache(
        player.discord_user_id,
        race
    )
    if mmr is not None:
        # Use cached MMR
        if race in ["bw_terran", "bw_protoss", "bw_zerg"]:
            mmr_bw = mmr
        elif race in ["sc2_terran", "sc2_protoss", "sc2_zerg"]:
            mmr_sc2 = mmr
```

#### In `queue_command.py` - `get_embed()` method:
**BEFORE (500-800ms per player):**
```python
p1_info = db_reader.get_player_by_discord_uid(self.match_result.player_1_discord_id)
p2_info = db_reader.get_player_by_discord_uid(self.match_result.player_2_discord_id)
```

**AFTER (<5ms per player):**
```python
p1_info = leaderboard_service.get_player_info_from_cache(
    self.match_result.player_1_discord_id
)
p2_info = leaderboard_service.get_player_info_from_cache(
    self.match_result.player_2_discord_id
)

# Fallback to DB if not in cache (rare case for new players)
if p1_info is None:
    p1_info = db_reader.get_player_by_discord_uid(...)
if p2_info is None:
    p2_info = db_reader.get_player_by_discord_uid(...)
```

### 3. Ensure Cache is Always Fresh

**Current situation:**
- Cache refreshes every 60 seconds automatically via TTL
- Cache invalidates on MMR changes (already implemented)
- Background process refreshes rankings every 300 seconds

**What we need to add:**
- Force cache refresh when bot starts (to ensure it's populated)
- Add proactive cache warming before first use

**Implementation:**
```python
# In bot_setup.py or main.py startup
async def warmup_caches():
    """Warm up caches on bot startup."""
    print("[Startup] Warming up leaderboard cache...")
    
    # This will populate the cache if empty
    await leaderboard_service.get_leaderboard_data(
        process_pool=process_pool,
        page_size=1  # Just need to trigger cache load
    )
    
    print("[Startup] Cache warmed up!")
```

### 4. Handle Abort Counts

**Option 1: Add to leaderboard cache query**
Expand `get_leaderboard_1v1` to include abort counts:
```sql
SELECT m.*, p.country, p.player_name, ui.aborts_this_month
FROM mmrs_1v1 m
LEFT JOIN players p ON m.discord_uid = p.discord_uid
LEFT JOIN user_info ui ON m.discord_uid = ui.discord_uid
```

**Option 2: Separate abort count cache**
Create a simple dict cache:
```python
_abort_count_cache = {
    "data": {},  # {discord_uid: abort_count}
    "timestamp": 0,
    "ttl": 60
}
```

**Recommendation:** Option 1 - add to main query, it's a simple JOIN

## Performance Impact Estimates

| Operation | Current Time | New Time | Savings |
|-----------|--------------|----------|---------|
| MMR lookup (2 races) | 400-550ms | <5ms | **-400-545ms** |
| Player info lookup (2 players) | 1000-1600ms | <5ms | **-1000-1595ms** |
| Abort count lookup (2 players) | 700-1200ms | <5ms | **-695-1195ms** |
| **Total per match** | **2100-3350ms** | **<15ms** | **-2085-3335ms** |

### Total Impact on Match Flow

- Match embed generation: 1000-1500ms → **100-200ms** (-85% reduction!)
- Replay upload view updates (4 embeds): 4000-6000ms → **400-800ms** (-85%)
- Match confirmation: 2000-3500ms → **500-1000ms** (-65%)
- Match abort: 6000ms → **2000ms** (-65%)

**Total savings per match: 8-12 seconds!**

## Implementation Steps

### Phase 1: Add Cache Helper Methods (30 minutes)
1. Add `get_player_mmr_from_cache()` to LeaderboardService
2. Add `get_player_info_from_cache()` to LeaderboardService
3. Add `get_player_all_mmrs_from_cache()` to LeaderboardService
4. Add unit tests

### Phase 2: Replace MMR Lookups (15 minutes)
1. Update `matchmaking_service.py` `add_player()` to use cache
2. Add fallback to DB if cache miss
3. Test queue joining

### Phase 3: Replace Player Info Lookups (30 minutes)
1. Update `queue_command.py` `get_embed()` to use cache
2. Add fallback to DB if cache miss
3. Test match embed generation

### Phase 4: Add Abort Counts to Cache (45 minutes)
1. Expand `get_leaderboard_1v1` query to include abort counts
2. Update leaderboard cache structure
3. Add `get_abort_count_from_cache()` method
4. Update `get_embed()` to use cached abort counts

### Phase 5: Add Cache Warming (15 minutes)
1. Add `warmup_caches()` function to bot startup
2. Test cold start performance

### Phase 6: Testing & Validation (30 minutes)
1. Run full match cycle
2. Measure timing improvements
3. Verify cache invalidation works
4. Test cache miss scenarios

**Total implementation time: ~2.5 hours**
**Total performance gain: 8-12 seconds per match**

## Edge Cases to Handle

1. **New player not in cache yet**
   - Fallback to DB query
   - Cache will be updated on next refresh (max 60 seconds)

2. **MMR just changed (match completion)**
   - Cache invalidation already triggers on MMR changes
   - Leaderboard will refresh immediately

3. **Cache refresh in progress during query**
   - Polars DataFrame is immutable, so reads are safe
   - Worst case: read slightly stale data (max 60 seconds old)

4. **Bot startup before cache populated**
   - Warmup function ensures cache is ready before accepting commands
   - If somehow accessed before warmup, will trigger sync cache refresh

## Monitoring & Validation

Add performance logging to track cache effectiveness:

```python
# In cache helper methods
cache_hits = 0
cache_misses = 0

def get_player_mmr_from_cache(self, discord_uid, race):
    global cache_hits, cache_misses
    
    result = self._query_cache(discord_uid, race)
    if result is not None:
        cache_hits += 1
        print(f"[Cache HIT] MMR lookup for {discord_uid}/{race}")
    else:
        cache_misses += 1
        print(f"[Cache MISS] MMR lookup for {discord_uid}/{race}")
    
    return result

# Log cache stats periodically
def log_cache_stats():
    total = cache_hits + cache_misses
    hit_rate = (cache_hits / total * 100) if total > 0 else 0
    print(f"[Cache Stats] Hits: {cache_hits}, Misses: {cache_misses}, Hit Rate: {hit_rate:.1f}%")
```

Expected hit rate: **>95%** (only misses for brand new players)

## Next Steps

1. Implement Phase 1 (cache helper methods)
2. Test in isolation
3. Implement Phase 2 (MMR lookups)
4. Measure improvement
5. Continue with remaining phases

This approach is **much better** than creating batch queries because:
- ✅ No DB schema changes needed
- ✅ Cache is already maintained and fresh
- ✅ Minimal code changes
- ✅ Instant performance boost
- ✅ Works for ALL operations (not just specific queries)

