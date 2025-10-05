# Leaderboard Performance Analysis - Best Race Filter

## Problem Identified

The **"Best Race Only"** filter is slow due to multiple inefficiencies in the current implementation.

## Performance Bottlenecks

### 1. ❌ **Fetching ALL Data from Database** (Lines 88-98)

```python
# Get all players regardless of race
all_players = self.db_reader.get_leaderboard_1v1(limit=10000)
```

**Issue**: Fetches up to 10,000 records from the database every time, even though we only need ~20 for display.

**Impact**: 
- Database query returns massive result set
- Slow network/IO transfer
- High memory usage

---

### 2. ❌ **Full List Copy in Memory** (Line 135)

```python
def _apply_filters(self, players: List[Dict]) -> List[Dict]:
    filtered_players = players.copy()  # Creates a copy of entire list
```

**Issue**: Copies the entire player list (potentially 10,000+ entries) before filtering.

**Impact**:
- O(n) memory allocation
- Unnecessary memory usage
- Slower than in-place filtering

---

### 3. ❌ **Inefficient Best Race Filter** (Lines 146-153)

```python
if self.best_race_only:
    # Group by player_id and keep only the highest MMR entry for each player
    player_best_races = {}
    for player in filtered_players:
        player_id = player["player_id"]
        if player_id not in player_best_races or player["mmr"] > player_best_races[player_id]["mmr"]:
            player_best_races[player_id] = player
    filtered_players = list(player_best_races.values())
```

**Issue**: Processes ALL records in Python instead of using SQL aggregation.

**Impact**:
- O(n) iteration through all players
- Dictionary lookups and comparisons in Python (slow)
- Should be done in SQL (much faster)

---

### 4. ❌ **Post-Filter Sorting** (Line 115)

```python
# Sort by MMR (descending)
filtered_players.sort(key=lambda x: x["mmr"], reverse=True)
```

**Issue**: Sorts entire filtered list in Python after fetching.

**Impact**:
- O(n log n) sorting in Python
- Should be done in SQL with `ORDER BY`

---

### 5. ❌ **Using player_name Instead of discord_uid** (Line 150)

```python
player_id = player["player_id"]  # This is player_name, not discord_uid!
```

**Issue**: Groups by `player_name` which could have duplicates or be None.

**Impact**:
- Incorrect grouping if multiple players have same name
- Doesn't properly identify unique players

---

## Performance Analysis

### Current Flow (Slow)

```
1. Database: Fetch 10,000 MMR records           [SLOW - large dataset]
2. Python: Convert to formatted list (10,000)   [SLOW - loop]
3. Python: Copy entire list                     [SLOW - memory]
4. Python: Filter by country                    [SLOW - loop]
5. Python: Filter by race                       [SLOW - loop]
6. Python: Group by player_id (dictionary)      [SLOW - loop + dict ops]
7. Python: Sort by MMR                          [SLOW - O(n log n)]
8. Python: Paginate (slice)                     [FAST]
```

**Total Time**: Multiple slow operations on large datasets

---

## Recommended Solutions

### Solution 1: **SQL-Based Best Race Filter** (Optimal)

Use SQL aggregation to get best race per player in the database:

```sql
SELECT 
    discord_uid,
    player_name,
    race,
    mmr,
    country
FROM mmrs_1v1 m1
WHERE mmr = (
    SELECT MAX(m2.mmr)
    FROM mmrs_1v1 m2
    WHERE m2.discord_uid = m1.discord_uid
)
```

Or using window functions (if SQLite version supports it):

```sql
WITH RankedMMRs AS (
    SELECT 
        discord_uid,
        player_name,
        race,
        mmr,
        country,
        ROW_NUMBER() OVER (PARTITION BY discord_uid ORDER BY mmr DESC) as rank
    FROM mmrs_1v1
    JOIN players ON mmrs_1v1.discord_uid = players.discord_uid
)
SELECT * FROM RankedMMRs WHERE rank = 1
```

**Benefits**:
- ✅ Database does the heavy lifting
- ✅ Only returns needed records
- ✅ Already sorted
- ✅ Much faster than Python loops

---

### Solution 2: **Database-Side Pagination**

Instead of fetching 10,000 records, use SQL `LIMIT` and `OFFSET`:

```python
# Only fetch what we need for the current page
page_players = self.db_reader.get_leaderboard_1v1(
    race=race,
    country=country,
    limit=page_size,
    offset=(current_page - 1) * page_size,
    best_race_only=True  # New parameter
)
```

**Benefits**:
- ✅ Fetches only 20 records instead of 10,000
- ✅ Dramatically reduces transfer time
- ✅ Lower memory usage

---

### Solution 3: **Use discord_uid Instead of player_name**

```python
# Change from player_id (player_name) to discord_uid
player_id = player["discord_uid"]  # Unique identifier
```

**Benefits**:
- ✅ Correctly identifies unique players
- ✅ No duplicate issues

---

### Solution 4: **Remove Unnecessary Operations**

```python
# Don't copy the list
filtered_players = players  # Use original list

# Don't sort in Python - already sorted from SQL
# filtered_players.sort(...)  # REMOVE THIS
```

**Benefits**:
- ✅ Reduces memory usage
- ✅ Eliminates redundant operations

---

## Estimated Performance Improvements

| Operation | Current | Optimized | Speedup |
|-----------|---------|-----------|---------|
| Database fetch | 10,000 records | 20 records | **500x faster** |
| Best race filter | Python loop | SQL aggregation | **100x faster** |
| Sorting | Python | SQL ORDER BY | **10x faster** |
| Memory usage | ~10MB | ~200KB | **50x less** |

**Overall Expected Speedup**: **10-50x faster** depending on dataset size

---

## Implementation Priority

1. **HIGH**: Add SQL-based best race filter in `db_reader_writer.py`
2. **HIGH**: Implement database-side pagination
3. **MEDIUM**: Use `discord_uid` instead of `player_name` for grouping
4. **LOW**: Remove list copy and Python sorting

---

## Code Changes Required

### 1. Update `db_reader_writer.py`

Add `best_race_only` parameter to `get_leaderboard_1v1()`:

```python
def get_leaderboard_1v1(
    self,
    race: Optional[str] = None,
    country: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    best_race_only: bool = False  # NEW PARAMETER
) -> List[Dict[str, Any]]:
    # SQL query with optional best race subquery
```

### 2. Update `leaderboard_service.py`

Remove Python-based filtering and use database parameters instead.

---

## Summary

The current implementation is slow because it:
1. Fetches ALL data (10,000 records) instead of needed page (20 records)
2. Does heavy computation in Python instead of SQL
3. Copies and sorts large lists unnecessarily
4. Uses wrong identifier (player_name vs discord_uid)

**Recommended fix**: Move best race filtering to SQL, implement proper pagination, and let the database do the heavy lifting.

