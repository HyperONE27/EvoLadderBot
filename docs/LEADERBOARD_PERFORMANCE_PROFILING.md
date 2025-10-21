# Leaderboard Performance Profiling

## Overview

Added detailed performance instrumentation to diagnose slowdowns when filtering or toggling "Best Race Only" in the leaderboard.

## Instrumentation Points

### Backend Service (`leaderboard_service.py`)

#### `get_leaderboard_data()` - Main Data Fetch
```
[Leaderboard Perf] Cache fetch: X.XXms
[Leaderboard Perf] Apply filters: X.XXms
[Leaderboard Perf] Best race filter: X.XXms  (only when enabled)
[Leaderboard Perf] Sort by MMR: X.XXms
[Leaderboard Perf] Slice page: X.XXms
[Leaderboard Perf] to_dicts(): X.XXms
[Leaderboard Perf] TOTAL: X.XXms
```

**What Each Step Does:**
1. **Cache fetch** - Get DataFrame from global cache (< 1ms for hits)
2. **Apply filters** - Country/race filtering using Polars `is_in()` and `filter()`
3. **Best race filter** - Groupby `player_id` and keep highest MMR (only when toggled)
4. **Sort by MMR** - Sort filtered results by MMR descending
5. **Slice page** - Zero-copy slice to get 40 rows for current page
6. **to_dicts()** - Convert Polars DataFrame to Python list of dicts

#### `get_leaderboard_data_formatted()` - Format for Display
```
[Format Players] Formatted N players in X.XXms
```

**What It Does:**
- Iterates through 40 players
- Adds rank numbers
- Rounds MMR values
- Calls `format_race_name()` for each player

### Frontend Command (`leaderboard_command.py`)

#### `get_embed()` - Discord Embed Generation
```
[Embed Perf] Data validation: X.XXms
[Embed Perf] Embed creation: X.XXms
[Embed Perf] Get filter info: X.XXms
[Embed Perf] Format players: X.XXms
[Embed Perf] Calculate rank width: X.XXms
[Embed Perf] Generate chunks - Total: X.XXms
[Embed Perf]   -> Emote fetching: X.XXms
[Embed Perf]   -> Text formatting: X.XXms
[Embed Perf] Add all fields: X.XXms
[Embed Perf] Footer and color: X.XXms
[Embed Perf] TOTAL EMBED: X.XXms
```

**What Each Step Does:**
1. **Data validation** - Basic null checks
2. **Embed creation** - Create Discord Embed object
3. **Get filter info** - Get filter display text from service
4. **Format players** - Calls backend service to format player data
5. **Calculate rank width** - Determine padding for alignment
6. **Generate chunks** - Split 40 players into 8 chunks of 5
   - **Emote fetching** - Get rank/race/flag emotes for each player
   - **Text formatting** - Build formatted strings with backticks
7. **Add all fields** - Add all chunks as Discord embed fields
8. **Footer and color** - Add pagination footer and embed color

## Expected Performance Targets

### Fast Path (Cache Hit, No Best Race)
- Cache fetch: **< 1ms**
- Apply filters: **< 5ms** (even with many countries/races)
- Sort by MMR: **< 2ms**
- Slice page: **< 1ms**
- to_dicts(): **< 10ms** (40 rows)
- **Total backend: < 20ms**

### Slower Path (Best Race Enabled)
- Cache fetch: **< 1ms**
- Apply filters: **< 5ms**
- Best race filter: **10-50ms** (groupby operation)
- Sort by MMR: **< 2ms**
- Slice page: **< 1ms**
- to_dicts(): **< 10ms**
- **Total backend: 15-70ms**

### Embed Generation
- Format players: **< 5ms**
- Emote fetching: **< 10ms** (40 players)
- Text formatting: **< 5ms**
- Add fields: **< 10ms**
- **Total embed: < 40ms**

### Total User-Perceived Latency
- **Fast path: 60-100ms** (backend + embed + Discord API)
- **Best race: 100-150ms** (includes groupby operation)

## Known Bottlenecks

### 1. `to_dicts()` - Polars to Python Conversion
**Issue**: Converting 40 rows from Polars to Python dicts can be slow (10-50ms).

**Why**: Polars is columnar and zero-copy, but Python dicts are row-oriented and require data copying.

**Potential Fix**: Keep data in Polars format longer, convert only what's needed for display.

### 2. `best_race_only` Groupby
**Issue**: Groupby operation on full dataset (before filtering to page) can be slow.

**Why**: Has to sort entire dataset and group by `player_id`.

**Potential Fix**: 
- Apply groupby before filtering (less data to process)
- Cache best_race results separately
- Use Polars lazy evaluation with `group_by().agg()` instead of `.first()`

### 3. Emote Fetching (40 players × 3 emotes = 120 lookups)
**Issue**: Even cached emote lookups add up.

**Why**: 120 dictionary lookups per page view.

**Potential Fix**: Batch emote fetching, or embed emotes directly in player data during formatting.

### 4. Race Name Formatting (40 calls per page)
**Issue**: `format_race_name()` called for every player in `get_leaderboard_data_formatted()`.

**Why**: Dictionary lookup + string formatting for each player.

**Potential Fix**: Do this once during cache creation, store formatted name in DataFrame.

## How to Use This Data

### 1. Run the Bot and View Leaderboard
```bash
python -m src.bot.main
# Then use /leaderboard in Discord
```

### 2. Watch Console Output
You'll see detailed timing for each step:
```
[Leaderboard Perf] Cache fetch: 0.52ms
[Leaderboard Perf] Apply filters: 3.21ms
[Leaderboard Perf] Sort by MMR: 1.15ms
[Leaderboard Perf] Slice page: 0.08ms
[Leaderboard Perf] to_dicts(): 12.34ms
[Leaderboard Perf] TOTAL: 17.30ms
```

### 3. Test Different Scenarios
- **No filters** - Baseline performance
- **Many countries selected** - Test filter performance
- **Many races selected** - Test filter performance
- **Best race toggle** - Test groupby performance
- **Page navigation** - Test slicing performance

### 4. Identify Bottleneck
Look for the step taking the most time. If one step is > 50ms, that's your bottleneck.

## Next Steps for Optimization

Based on profiling results, we can:

1. **If `to_dicts()` is slow (> 20ms)**:
   - Keep data in Polars longer
   - Use `.to_dicts()` selectively
   - Consider `.to_dict()` (columnar) if possible

2. **If `best_race_only` groupby is slow (> 50ms)**:
   - Pre-compute and cache best race results
   - Use lazy evaluation
   - Optimize groupby strategy

3. **If emote fetching is slow (> 20ms)**:
   - Batch emote lookups
   - Embed emotes in DataFrame during cache creation

4. **If race name formatting is slow (> 10ms)**:
   - Pre-format race names during cache creation
   - Store in DataFrame as additional column

## Removing Instrumentation

Once performance is optimized, search for `[Leaderboard Perf]`, `[Format Players]`, and `[Embed Perf]` to remove all timing logs.

