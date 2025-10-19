# Performance Optimization & Idempotency Plan

**Date**: October 19, 2025  
**Priority**: HIGH - Bot responses are too slow  
**Root Cause**: PostgreSQL network latency + excessive queries

## Problem Analysis

### Current Performance Issues

**Symptoms:**
- Commands take 2-6 seconds to respond (vs <500ms with local SQLite)
- Users might click buttons multiple times due to slow feedback
- Risk of duplicate operations (idempotency issues)
- Poor user experience

**Root Causes:**
1. **Network Latency** - PostgreSQL on Supabase (vs local SQLite)
   - Each query: ~100-300ms round-trip
   - Setup command: 5-8 database calls = 500-2400ms just for database
   
2. **Excessive Queries** - No caching, everything hits database
   - Maps loaded from DB every time
   - Races loaded from DB every time
   - Regions/countries loaded from DB every time
   - Action logs written for every interaction
   
3. **Sequential Operations** - Not parallelized
   - Get player → Check MMR → Get preferences (3 sequential queries)
   - Should be: Get all data in parallel or single JOIN
   
4. **No Request Deduplication** - Users can spam buttons
   - No idempotency keys
   - No button disabling after click
   - Race conditions possible

---

## Solution 1: Static Data Caching

### Quick Win - Cache Everything That Doesn't Change

**What to Cache:**
- Maps (rarely change)
- Races (never change)
- Regions (rarely change)
- Countries (rarely change)

**Expected Impact:** 70-80% reduction in database queries

### Implementation

**File: `src/backend/services/cache_service.py`**
```python
from typing import Dict, List, Optional
from src.backend.db.db_reader_writer import DatabaseReader
import json
import os

class StaticDataCache:
    """In-memory cache for static data."""
    
    def __init__(self):
        self._maps: Optional[List[Dict]] = None
        self._races: Optional[List[Dict]] = None
        self._regions: Optional[List[Dict]] = None
        self._countries: Optional[List[Dict]] = None
        self._initialized = False
    
    async def initialize(self):
        """Load all static data once at startup."""
        if self._initialized:
            return
        
        print("[Cache] Initializing static data cache...")
        
        # Try loading from JSON files first (fastest)
        try:
            self._load_from_json()
            print("[Cache] Loaded from JSON files")
        except Exception as e:
            print(f"[Cache] JSON load failed, loading from database: {e}")
            self._load_from_database()
        
        self._initialized = True
        print(f"[Cache] Initialized: {len(self._maps)} maps, {len(self._races)} races, "
              f"{len(self._regions)} regions, {len(self._countries)} countries")
    
    def _load_from_json(self):
        """Load from JSON files in data/misc/"""
        with open('data/misc/maps.json', 'r') as f:
            self._maps = json.load(f)
        with open('data/misc/races.json', 'r') as f:
            self._races = json.load(f)
        with open('data/misc/regions.json', 'r') as f:
            self._regions = json.load(f)
        with open('data/misc/countries.json', 'r') as f:
            self._countries = json.load(f)
    
    def _load_from_database(self):
        """Fallback: Load from database."""
        reader = DatabaseReader()
        # Implement database loading if JSON files don't exist
        pass
    
    def get_maps(self) -> List[Dict]:
        """Get all maps."""
        if not self._initialized:
            raise RuntimeError("Cache not initialized. Call initialize() first.")
        return self._maps
    
    def get_map_by_code(self, code: str) -> Optional[Dict]:
        """Get map by code."""
        return next((m for m in self._maps if m['code'] == code), None)
    
    def get_races(self) -> List[Dict]:
        """Get all races."""
        return self._races
    
    def get_race_by_code(self, code: str) -> Optional[Dict]:
        """Get race by code."""
        return next((r for r in self._races if r['code'] == code), None)
    
    def get_regions(self) -> List[Dict]:
        """Get all regions."""
        return self._regions
    
    def get_region_by_code(self, code: str) -> Optional[Dict]:
        """Get region by code."""
        return next((r for r in self._regions if r['code'] == code), None)
    
    def get_countries(self) -> List[Dict]:
        """Get all countries."""
        return self._countries
    
    def get_country_by_code(self, code: str) -> Optional[Dict]:
        """Get country by code."""
        return next((c for c in self._countries if c['code'] == code), None)
    
    def reload(self):
        """Reload all data (for admin commands)."""
        self._initialized = False
        self.initialize()

# Global singleton
static_cache = StaticDataCache()
```

**Update `interface_main.py` to initialize cache at startup:**
```python
from src.backend.services.cache_service import static_cache

if __name__ == "__main__":
    # Initialize cache before bot starts
    asyncio.run(static_cache.initialize())
    
    # ... rest of bot startup
```

**Replace service calls:**
```python
# OLD (slow):
from src.backend.services.maps_service import MapsService
maps = MapsService().get_all_maps()  # Database query every time

# NEW (fast):
from src.backend.services.cache_service import static_cache
maps = static_cache.get_maps()  # In-memory, instant
```

---

## Solution 2: Query Optimization

### Combine Multiple Queries into Single JOINs

**Example: Player Profile**

**Before (3 queries):**
```python
player = reader.get_player_by_discord_uid(uid)  # Query 1
mmrs = reader.get_all_player_mmrs_1v1(uid)  # Query 2
preferences = reader.get_preferences_1v1(uid)  # Query 3
```

**After (1 query with JOIN):**
```python
def get_player_full_profile(self, discord_uid: int) -> Dict:
    """Get player with all related data in single query."""
    return self.adapter.execute_query("""
        SELECT 
            p.*,
            json_group_array(DISTINCT json_object(
                'race', m.race,
                'mmr', m.mmr,
                'games_played', m.games_played,
                'games_won', m.games_won
            )) as mmrs,
            pref.last_chosen_races,
            pref.last_chosen_vetoes
        FROM players p
        LEFT JOIN mmrs_1v1 m ON p.discord_uid = m.discord_uid
        LEFT JOIN preferences_1v1 pref ON p.discord_uid = pref.discord_uid
        WHERE p.discord_uid = :uid
        GROUP BY p.discord_uid
    """, {"uid": discord_uid})
```

**Impact:** 3x faster for profile queries

---

## Solution 3: Idempotency & Rate Limiting

### Prevent Duplicate Operations

**Problem:** User clicks "Confirm" multiple times due to slow response

**Solution 1: Disable Buttons After Click**
```python
class ConfirmButton(discord.ui.Button):
    async def callback(self, interaction: discord.Interaction):
        # Disable ALL buttons immediately
        for item in self.view.children:
            item.disabled = True
        
        # Update message to show disabled state
        await interaction.response.edit_message(view=self.view)
        
        # Now do the slow operation
        await self.callback_func(interaction)
```

**Solution 2: Idempotency Keys**
```python
# In DatabaseWriter
def create_match_1v1_idempotent(
    self,
    idempotency_key: str,  # e.g., f"match_{p1_uid}_{p2_uid}_{timestamp}"
    **match_data
) -> int:
    """Create match with idempotency check."""
    
    # Check if already created
    existing = self.adapter.execute_query(
        "SELECT id FROM matches_1v1 WHERE idempotency_key = :key",
        {"key": idempotency_key}
    )
    
    if existing:
        return existing[0]["id"]
    
    # Create new
    return self.adapter.execute_insert("""
        INSERT INTO matches_1v1 (idempotency_key, ...)
        VALUES (:idempotency_key, ...)
    """, {"idempotency_key": idempotency_key, ...})
```

**Solution 3: Add Idempotency Column to Database**
```sql
-- Add to critical tables
ALTER TABLE matches_1v1 ADD COLUMN idempotency_key TEXT UNIQUE;
ALTER TABLE player_action_logs ADD COLUMN idempotency_key TEXT UNIQUE;

CREATE INDEX idx_matches_idempotency ON matches_1v1(idempotency_key);
```

---

## Solution 4: Reduce Action Logging

**Current:** Every button click logs an action → slow DB write

**Optimization:**
```python
# Only log significant actions
LOGGABLE_ACTIONS = {
    'completed player setup',
    'accepted terms of service',
    'changed country',
    'joined queue',
    'reported match result'
}

def log_user_action(user_info, action_type, details=""):
    # Skip logging for minor actions
    if action_type not in LOGGABLE_ACTIONS:
        return
    
    # Log to database
    db_writer.log_player_action(...)
```

---

## Solution 5: Connection Pooling

**Verify Supabase connection is using pooler:**
```python
# In .env - Make sure using port 6543 (pooler) not 5432 (direct)
DATABASE_URL=postgresql://postgres.xxx:PASSWORD@aws-0-xxx.pooler.supabase.com:6543/postgres
```

**Add connection pool stats:**
```python
# In postgresql_adapter.py
def get_pool_stats(self):
    """Get connection pool statistics."""
    result = self.adapter.execute_query("SELECT * FROM pg_stat_activity")
    print(f"Active connections: {len(result)}")
```

---

## Implementation Priority

### Phase 1: Quick Wins (1-2 hours) - IMMEDIATE
1. ✅ Defer all interactions (DONE)
2. 🔄 Disable buttons after click (prevents double-clicks)
3. 🔄 Static data cache (70% fewer queries)
4. 🔄 Reduce action logging (fewer writes)

### Phase 2: Query Optimization (2-3 hours) - HIGH
1. Combine player profile queries
2. Batch MMR updates
3. Add database indices
4. Use JOINs instead of multiple queries

### Phase 3: Idempotency (1-2 hours) - MEDIUM
1. Add idempotency keys to critical operations
2. Add database columns
3. Update match creation/reporting

---

## Performance Targets

### Before Optimization
- Setup command: 4-6 seconds
- Queue command: 2-4 seconds
- Profile command: 1-3 seconds
- Database queries per command: 5-10

### After Phase 1 (Quick Wins)
- Setup command: 2-3 seconds (50% faster)
- Queue command: 1-2 seconds (50% faster)
- Profile command: 0.5-1 second (50% faster)
- Database queries per command: 1-3 (70% reduction)

### After Phase 2 (Full Optimization)
- Setup command: 1-2 seconds (75% faster)
- Queue command: 0.5-1 second (75% faster)
- Profile command: 0.3-0.5 seconds (83% faster)
- Database queries per command: 1-2 (80% reduction)

---

## Monitoring

**Add timing logs:**
```python
import time

async def command_with_timing(interaction):
    start = time.time()
    
    await interaction.response.defer()
    # ... do work ...
    
    elapsed = time.time() - start
    print(f"[PERF] Command took {elapsed:.2f}s")
```

**Track metrics:**
- Average response time per command
- Number of database queries per command
- Cache hit rate
- Button double-click rate

---

## Quick Implementation - Disable Buttons

**Immediate fix to prevent double-clicks:**

```python
# In confirm_restart_cancel_buttons.py
class ConfirmButton(discord.ui.Button):
    async def callback(self, interaction: discord.Interaction):
        # Disable all buttons FIRST
        for item in self.view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        # Show "Processing..." state
        await interaction.response.edit_message(view=self.view)
        
        # Now defer for long operation
        await interaction.response.defer()
        
        # Do actual work
        await self.callback_func(interaction)
```

---

**Bottom Line:** 
- Static cache = 70% fewer queries = 50-70% faster
- Button disabling = prevents double-clicks
- Idempotency keys = safe against race conditions
- Phase 1 can be done in 1-2 hours for immediate improvement

