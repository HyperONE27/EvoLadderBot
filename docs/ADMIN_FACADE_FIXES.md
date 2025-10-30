# Admin Service Facade Pattern Fixes

**Date:** October 29, 2025  
**Issue:** Admin commands bypassing DataAccessService facade to directly access database

---

## Summary

Fixed 2 critical facade pattern violations in AdminService where commands were directly accessing `DataAccessService._db_writer.adapter.execute_write()` instead of using the public API.

---

## Violations Fixed

### 1. `/admin resolve` - Match Conflict Resolution ✅ FIXED

**Location:** `src/backend/services/admin_service.py`, `resolve_match_conflict()` method

**Before (Lines 544-564):**
```python
# ❌ Direct DataFrame manipulation + direct DB access
if self.data_service._matches_1v1_df is not None:
    self.data_service._matches_1v1_df = self.data_service._matches_1v1_df.with_columns([
        pl.when(pl.col("id") == match_id)
          .then(pl.lit(new_result))
          .otherwise(pl.col("match_result"))
          .alias("match_result"),
        pl.when(pl.col("id") == match_id)
          .then(pl.lit('PROCESSING_COMPLETION'))
          .otherwise(pl.col("status"))
          .alias("status")
    ])

loop = asyncio.get_running_loop()
await loop.run_in_executor(
    None,
    self.data_service._db_writer.adapter.execute_write,  # ❌ VIOLATION
    "UPDATE matches_1v1 SET match_result = :result, status = 'PROCESSING_COMPLETION' WHERE id = :match_id",
    {'result': new_result, 'match_id': match_id}
)
```

**After:**
```python
# ✅ Use DataAccessService facade
await self.data_service.update_match(
    match_id=match_id,
    match_result=new_result,
    status='PROCESSING_COMPLETION'
)
print(f"[AdminService] Updated match {match_id} via DataAccessService: result={new_result}")
```

**Benefits:**
- ✅ Respects facade pattern
- ✅ Non-blocking async write queue
- ✅ Covered by WAL persistence
- ✅ Consistent with rest of codebase
- ✅ Easier to refactor internals

---

### 2. `/admin adjust_mmr` - MMR Adjustment ✅ FIXED

**Location:** `src/backend/services/admin_service.py`, `adjust_player_mmr()` method

**Before (Lines 632-650):**
```python
# ❌ Direct DataFrame manipulation + direct DB access
if self.data_service._mmrs_1v1_df is not None:
    self.data_service._mmrs_1v1_df = self.data_service._mmrs_1v1_df.with_columns([
        pl.when(
            (pl.col("discord_uid") == discord_uid) &
            (pl.col("race") == race)
        )
        .then(pl.lit(new_mmr))
        .otherwise(pl.col("mmr"))
        .alias("mmr")
    ])

loop = asyncio.get_running_loop()
await loop.run_in_executor(
    None,
    self.data_service._db_writer.adapter.execute_write,  # ❌ VIOLATION
    "UPDATE mmrs_1v1 SET mmr = :mmr WHERE discord_uid = :uid AND race = :race",
    {'mmr': new_mmr, 'uid': discord_uid, 'race': race}
)
```

**After:**
```python
# ✅ Use DataAccessService facade
await self.data_service.update_player_mmr(
    discord_uid=discord_uid,
    race=race,
    new_mmr=new_mmr,
    games_played=None,  # Don't update game stats
    games_won=None,
    games_lost=None,
    games_drawn=None
)
print(f"[AdminService] Updated MMR via DataAccessService: {discord_uid}/{race}: {current_mmr} -> {new_mmr}")
```

**Benefits:**
- ✅ Respects facade pattern
- ✅ Non-blocking async write queue
- ✅ Covered by WAL persistence
- ✅ Game stats preserved (admin adjustments don't affect W/L records)
- ✅ Consistent with rest of codebase

---

## Final Audit Status

| Command | Status | Facade Compliance |
|---------|--------|-------------------|
| `/admin snapshot` | ✅ | Read-only, compliant |
| `/admin conflicts` | ✅ | Read-only, compliant |
| `/admin player` | ✅ | Read-only, compliant |
| `/admin match` | ✅ | Read-only, compliant |
| `/admin resolve` | ✅ **FIXED** | Now uses facade |
| `/admin adjust_mmr` | ✅ **FIXED** | Now uses facade |
| `/admin remove_queue` | ✅ | Uses QueueService |
| `/admin reset_aborts` | ✅ | Uses facade |
| `/admin clear_queue` | ✅ | Uses QueueService |
| Admin action logging | ✅ | Uses facade |

**Result: 10/10 commands now properly use abstractions** ✅

---

## Architectural Principles Enforced

### ✅ Facade Pattern Compliance

**Rule:** All database writes must go through DataAccessService public API.

**Why:**
1. **Single Responsibility**: DataAccessService owns all data persistence logic
2. **Encapsulation**: Internal implementation (DataFrame + DB sync) can change without breaking clients
3. **Consistency**: All writes follow the same pattern (memory + async queue + DB)
4. **WAL Support**: Async writes can be persisted through crashes
5. **Performance**: Non-blocking writes don't block admin commands

### ✅ Read vs Write Access Patterns

**Acceptable:**
- ✅ Reading `_write_queue.qsize()` for monitoring
- ✅ Reading `_*_df` DataFrames for inspection
- ✅ Using public API methods

**Not Acceptable:**
- ❌ Writing to `_*_df` directly AND bypassing facade for DB writes
- ❌ Accessing `_db_writer.adapter.execute_write()` directly
- ❌ Running synchronous blocking DB operations in admin commands

### ✅ AdminService Role

**AdminService is the "System Inspector" - privileged but still follows rules:**

1. **Read Private for Inspection**: Can read private state for diagnostics
2. **Write Through Facade**: Must use public API for modifications
3. **Pattern**: `read private, write public`

---

## Testing Recommendations

### Manual Testing

Test both fixed commands:

```
# Test conflict resolution
1. Create a match with conflicting reports
2. Run: /admin conflicts
3. Select conflict and resolve it
4. Verify match_result updated in DB
5. Verify MMR calculated correctly
6. Verify admin action logged

# Test MMR adjustment
1. Check player's current MMR
2. Run: /admin adjust_mmr discord_id:X race:bw_terran new_mmr:2000 reason:"test"
3. Verify MMR updated in memory
4. Verify MMR updated in DB
5. Verify games_played/won/lost unchanged
6. Verify leaderboard cache invalidated
7. Verify admin action logged
```

### Integration Testing

Verify non-blocking behavior:

```python
# Admin command should return immediately
# DB write happens asynchronously in background
# Check write queue depth increases then decreases
```

---

## Files Modified

1. ✅ `src/backend/services/admin_service.py`
   - Fixed `resolve_match_conflict()` method (lines 544-550)
   - Fixed `adjust_player_mmr()` method (lines 618-629)
   - Both now use DataAccessService public API

2. ✅ No other files needed changes (facade methods already existed)

---

## Performance Impact

### Before:
- Admin commands blocked on synchronous DB writes
- Used `asyncio.run_in_executor()` to prevent blocking event loop
- Still slower than necessary

### After:
- Admin commands return instantly
- DB writes queued asynchronously
- DataAccessService background worker handles persistence
- Better user experience

---

## Maintainability Impact

### Before:
- 3 different patterns for DB writes in AdminService:
  1. Through facade (reset_aborts, log_admin_action)
  2. Direct SQL (resolve_conflict, adjust_mmr)
  3. Through other services (remove_queue)
- Inconsistent and confusing
- Refactoring DataAccessService internals would break AdminService

### After:
- 2 consistent patterns:
  1. Through DataAccessService facade (all DB operations)
  2. Through specialized services (QueueService)
- Clear separation of concerns
- Can refactor DataAccessService internals safely

---

## Conclusion

All admin commands now properly respect the facade pattern and use appropriate abstractions. The codebase is now consistent, maintainable, and follows proper architectural principles.

**No more facade violations.** ✅

---

**End of Report**

