# Singleton Services Security Audit

Audit of all singleton services for race conditions and shared mutable state.

## ✅ SAFE - Intentionally Shared State

### 1. `matchmaker` (MatchmakingService)
- **Shared State**: `self.players` (queue), `self.recent_activity`
- **Status**: ✅ **CORRECT** - Queue MUST be shared across all users
- **Reasoning**: Matchmaking requires a global queue where all players join
- **Thread Safety**: Uses `asyncio.Lock()` to prevent race conditions

### 2. `ranking_service` (RankingService)  
- **Shared State**: `self._rankings` (dictionary of MMR ranks)
- **Status**: ✅ **CORRECT** - Ranks are global, read-only after calculation
- **Reasoning**: All users see the same rankings
- **Thread Safety**: Refreshed atomically, then read-only

### 3. Global Caches
- `_leaderboard_cache` - ✅ Shared DataFrame, read-only between refreshes
- `_non_common_countries_cache` - ✅ Static data, never changes per-user

## ✅ SAFE - Stateless Services

### 4. `countries_service`, `regions_service`, `races_service`, `maps_service`
- **State**: Only loads static JSON config
- **Status**: ✅ **SAFE** - No mutable per-user state

### 5. `mmr_service`, `validation_service`
- **State**: Pure functions, no state
- **Status**: ✅ **SAFE** - Completely stateless

### 6. `command_guard_service`
- **State**: Only references `user_info_service`
- **Status**: ✅ **SAFE** - No mutable state

### 7. `storage_service`
- **State**: Only config settings
- **Status**: ✅ **SAFE** - No mutable state

## ✅ SAFE - Database Services

### 8. `db_reader`, `db_writer`
- **State**: Connection pools (managed by adapter)
- **Status**: ✅ **SAFE** - Database connections are thread-safe

### 9. `user_info_service`
- **State**: Database queries only
- **Status**: ✅ **SAFE** - No caching, always reads from DB

### 10. `replay_service`
- **State**: None, just database operations
- **Status**: ✅ **SAFE** - Stateless

### 11. `match_completion_service`
- **State**: Database operations only
- **Status**: ✅ **SAFE** - No mutable shared state

## ❌ FIXED - Previously Unsafe

### 12. `leaderboard_service` - **FIXED**
- **Was**: Stored per-user filter state (`current_page`, `country_filter`, etc.)
- **Problem**: User A's filters affected User B
- **Fix**: Made stateless, filters passed as parameters
- **Status**: ✅ **NOW SAFE**

## Summary

- **Total Services Audited**: 12 + DB layer
- **Unsafe Services Found**: 1 (leaderboard - now fixed)
- **Intentionally Shared**: 2 (matchmaker queue, ranking cache)
- **Stateless/Safe**: 10

## Recommendations

1. ✅ **Leaderboard**: Fixed - state moved to View instances
2. ✅ **Matchmaker**: Correct as-is - queue must be shared
3. ✅ **All others**: No changes needed

## Testing Checklist

- [ ] Two users can use leaderboard simultaneously with different filters
- [ ] Matchmaking queue works correctly with multiple users
- [ ] Rankings display consistently for all users
- [ ] No user can affect another user's UI state

## Future Guidelines

**When creating new singleton services:**
1. Ask: "Should this state be shared across ALL users?"
2. If NO → Don't store it in the service, pass as parameters
3. If YES → Document why and add thread safety (locks)
4. Always prefer stateless when possible

