# Discord Interaction Timeout Fix & Performance Optimization Plan

**Date**: October 19, 2025  
**Priority**: HIGH - Users are not receiving responses

## Problem Summary

Discord interactions expire after **3 seconds** if not acknowledged. Database operations (especially with PostgreSQL on Supabase) can take longer than this, causing:
- `discord.errors.NotFound: 404 Not Found (error code: 10062): Unknown interaction`
- Users don't get feedback even though operations succeed
- Poor user experience

## Solution: Two-Pronged Approach

### 1. Defer All Interactions Immediately (CRITICAL)
### 2. Optimize Slow Operations (PERFORMANCE)

---

## Part 1: Interaction Deferral Strategy

### Discord Interaction Lifecycle

```
User clicks button/runs command
    ↓
3 SECONDS TO RESPOND ⏰
    ↓
Option A: interaction.response.defer()        ← Buys 15 minutes
    ↓
Option B: interaction.response.send_message() ← Immediate response
    ↓
TIMEOUT if no response!
```

### Pattern 1: Defer + Followup (For Slow Operations)

```python
async def slow_command(interaction: discord.Interaction):
    # IMMEDIATELY defer - buys 15 minutes
    await interaction.response.defer(ephemeral=True)
    
    # Do slow work (database writes, API calls, etc.)
    result = await do_slow_database_work()
    
    # Send response via followup (NOT response.edit_message)
    await interaction.followup.send(embed=result_embed, ephemeral=True)
```

### Pattern 2: Immediate Response + Edit (For Fast Operations)

```python
async def fast_command(interaction: discord.Interaction):
    # Send immediate placeholder
    await interaction.response.send_message("Processing...", ephemeral=True)
    
    # Do quick work
    result = await do_quick_work()
    
    # Edit the message
    await interaction.edit_original_response(content="Done!", embed=result_embed)
```

### Pattern 3: Defer for Button Callbacks

```python
async def button_callback(interaction: discord.Interaction):
    # CRITICAL: Defer FIRST for button callbacks that do DB writes
    await interaction.response.defer()
    
    # Do work
    await process_button_action()
    
    # Edit original message via followup
    await interaction.edit_original_response(embed=success_embed)
```

---

## Part 2: Performance Optimizations

### Quick Wins (Immediate Impact)

1. **Reduce Database Roundtrips**
   - Current: Multiple SELECT queries in sequence
   - Fix: Combine queries with JOINs
   - Impact: 50-70% reduction in query count

2. **Batch Updates**
   - Current: Separate INSERT for player + action log + preferences
   - Fix: Use transactions or batch writes
   - Impact: 30-40% faster writes

3. **Cache Static Data**
   - Maps, races, regions, countries (don't change often)
   - Load once at startup, keep in memory
   - Impact: Eliminate 100+ queries per command

4. **Use Connection Pooling Properly**
   - Already using Supabase pooler (port 6543)
   - Ensure connections are reused, not recreated
   - Impact: 20-30% faster connection establishment

5. **Lazy Loading**
   - Don't fetch leaderboard data until needed
   - Don't load full player history for simple checks
   - Impact: 40-50% faster for simple operations

---

## Implementation Plan

### Phase 1: Critical Fixes (Commands with DB Writes) - 1 hour

**Files to Update:**
1. `src/bot/interface/commands/setup_command.py` - **CRITICAL**
   - `confirm_callback` - Multiple DB writes
   - `restart_callback` - DB writes
   
2. `src/bot/interface/commands/setcountry_command.py`
   - Country update - DB write
   
3. `src/bot/interface/commands/activate_command.py`
   - Activation - DB write
   
4. `src/bot/interface/commands/termsofservice_command.py`
   - TOS acceptance - DB write

5. `src/bot/interface/commands/queue_command.py`
   - Queue join/leave - Preferences write

**Pattern to Apply:**
```python
# OLD (causes timeout):
async def callback(interaction):
    # ... do slow DB work ...
    await interaction.response.edit_message(embed=result)

# NEW (works):
async def callback(interaction):
    await interaction.response.defer()  # ← ADD THIS FIRST!
    # ... do slow DB work ...
    await interaction.edit_original_response(embed=result)  # ← CHANGE THIS
```

### Phase 2: Read-Only Commands (Faster, but still defer) - 30 min

**Files to Update:**
1. `src/bot/interface/commands/leaderboard_command.py`
   - Large queries - should defer
   
2. `src/bot/interface/commands/profile_command.py`
   - Multiple queries - should defer

### Phase 3: Performance Optimizations - 2-3 hours

1. **Create Static Data Cache**
   ```python
   # src/backend/services/cache_service.py
   class StaticDataCache:
       def __init__(self):
           self.maps = None
           self.races = None
           self.regions = None
           self.countries = None
       
       async def initialize(self):
           # Load all static data once at startup
           pass
   ```

2. **Optimize DatabaseReader Queries**
   - Combine `get_player_by_discord_uid` + `get_player_mmr_1v1` into single JOIN
   - Add indices to PostgreSQL for common queries
   - Use LIMIT on queries that don't need full results

3. **Reduce Action Logging**
   - Only log significant actions (not every button click)
   - Batch logs and write async

4. **Connection Pooling Verification**
   - Ensure adapters reuse connections
   - Add connection pool stats logging

---

## Testing Strategy

### Local Testing (SQLite)
```bash
# 1. Test each command with timing
python -m pytest tests/bot/test_discord_commands.py -v --durations=10

# 2. Manual testing with Discord bot
# Measure time from click to response
```

### Production Testing (PostgreSQL)
```bash
# 1. Deploy to Railway
# 2. Monitor logs for timing
grep "completed" railway_logs.txt | awk '{print $NF}'

# 3. Test each command
- /setup
- /queue
- /setcountry
- /profile
- /leaderboard
```

---

## Success Metrics

### Before (Current State)
- ❌ Setup command: ~4-6 seconds (TIMEOUT)
- ❌ Queue command: ~2-4 seconds (RISKY)
- ❌ Profile command: ~1-3 seconds (RISKY)
- ❌ Error rate: ~80% for setup, ~20% for others

### After (Target State)
- ✅ All commands: Acknowledged in <100ms (deferral)
- ✅ Setup command: Complete in <2 seconds
- ✅ Queue command: Complete in <500ms
- ✅ Profile command: Complete in <1 second
- ✅ Error rate: 0% interaction timeouts

---

## Priority Order

1. **IMMEDIATE** (Phase 1): Defer all button callbacks in setup/activate/queue
2. **HIGH** (Phase 1): Defer command handlers that do DB writes
3. **MEDIUM** (Phase 2): Defer read-heavy commands
4. **LOW** (Phase 3): Performance optimizations (cache, batch, optimize queries)

---

## Files to Modify (Comprehensive List)

### Commands
- ✅ `src/bot/interface/commands/setup_command.py` (CRITICAL)
- ✅ `src/bot/interface/commands/activate_command.py`
- ✅ `src/bot/interface/commands/setcountry_command.py`
- ✅ `src/bot/interface/commands/termsofservice_command.py`
- ✅ `src/bot/interface/commands/queue_command.py`
- ⚠️ `src/bot/interface/commands/leaderboard_command.py` (read-only, less critical)
- ⚠️ `src/bot/interface/commands/profile_command.py` (read-only, less critical)

### Components (Buttons/Views)
- ✅ `src/bot/interface/components/confirm_restart_cancel_buttons.py` (CRITICAL)
- ✅ `src/bot/interface/components/setup_buttons.py`
- ⚠️ `src/bot/interface/components/queue_buttons.py`

### Services (Performance)
- 🔄 Create `src/backend/services/cache_service.py` (new)
- 🔄 Optimize `src/backend/db/db_reader_writer.py` (batch queries)

---

## Rollout Strategy

1. **Test locally with SQLite** (fast, safe)
2. **Deploy to Railway** (one commit)
3. **Monitor logs** for 30 minutes
4. **Test all commands** in production
5. **Performance optimization** (separate PR)

---

## Notes

- Interaction deferral is **always safe** - worst case, user sees a loading state
- Performance optimizations are **separate** - don't block critical fix
- Cache invalidation will be needed later (low priority)
- Consider adding timing logs to track improvements

---

## Commands Reference

### Current Implementation (Broken)
```python
async def callback(interaction):
    result = await slow_operation()  # Takes 4 seconds
    await interaction.response.edit_message(embed=result)  # TIMEOUT!
```

### Fixed Implementation
```python
async def callback(interaction):
    await interaction.response.defer()  # Acknowledge immediately
    result = await slow_operation()  # Takes 4 seconds - OK now!
    await interaction.edit_original_response(embed=result)  # Works!
```

### Optimization (Future)
```python
async def callback(interaction):
    await interaction.response.defer()
    # Optimized: Combined queries, cached data, batch writes
    result = await fast_operation()  # Takes 500ms
    await interaction.edit_original_response(embed=result)
```

