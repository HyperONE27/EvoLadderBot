# Leaderboard "Best Race Only" Filter Fix

## Problem

Players with recent games were missing from the leaderboard when the "Best Race Only" filter was applied.

### Root Cause

The filtering logic had an incorrect order of operations:

**BEFORE (Buggy)**:
1. Apply `best_race_only` filter → Pick highest MMR race per player (including unranked races)
2. Filter out `u_rank` players → Remove players whose best race is unranked

This caused players to disappear if:
- They play multiple races
- Their **highest MMR race** became unranked (inactive > 2 weeks)
- But they have **other ranked races** (played recently)

**Example Scenario**:
- Player has SC2 Terran at 1500 MMR (last played 3 weeks ago → unranked)
- Player has SC2 Protoss at 1400 MMR (last played yesterday → ranked)
- Bug: Player picked Terran (highest MMR), then removed for being unranked
- Result: Player completely missing from leaderboard despite recent activity

## Solution

Changed the order of operations to filter out unranked races **before** selecting the best race:

**AFTER (Fixed)**:
1. Filter out `u_rank` players → Remove all unranked races
2. Apply `best_race_only` filter → Pick highest MMR among **ranked** races

Now the same player:
- Unranked Terran is excluded first
- Best race selected from remaining: Protoss at 1400 MMR
- Result: Player correctly appears on leaderboard with their best **ranked** race

## Code Changes

### File: `src/backend/services/leaderboard_service.py`

**Lines 72-87** - Moved `u_rank` filter to execute before `best_race_only`:

```python
# FIRST: Always exclude unranked players (u_rank) from leaderboard display
# This MUST happen BEFORE best_race_only to ensure we pick the best RANKED race
# Unranked players are stored but only shown in /profile and /queue
df = df.filter(pl.col("rank") != "u_rank")

# SECOND: Apply best_race_only filter if enabled
# This MUST happen AFTER u_rank filtering to ensure we pick best RANKED race
# and BEFORE other filters to ensure correct rank distribution
if best_race_only:
    # Group by discord_uid and keep only the highest MMR entry (their best ranked race)
    # Sort first, then group and take first (highest MMR per player among ranked races)
    df = (df
        .sort(["mmr", "last_played"], descending=[True, True])
        .group_by("discord_uid", maintain_order=True)
        .first()
    )
```

**Lines 123-130** - Removed duplicate `u_rank` filter that was previously after best_race_only.

### File: `tests/characterize/test_leaderboard_filtering_logic.py`

**Lines 66-71** - Updated test fixture to set recent timestamps so test data is ranked:

```python
# Update all last_played timestamps to be recent (within 2 weeks) so players are ranked
from datetime import datetime, timezone
current_time = datetime.now(timezone.utc)
mmrs_data = mmrs_data.with_columns([
    pl.lit(current_time).alias("last_played")
])
```

**Line 83** - Removed obsolete `mark_leaderboard_cache_valid()` call.

## Verification

### Tests
All 6 characterization tests pass:
- ✅ `test_baseline_player_counts`
- ✅ `test_best_race_only_rank_distribution`
- ✅ `test_sum_of_filtered_best_race_ranks_equals_total`
- ✅ `test_invariant_adding_filters_never_increases_player_count`
- ✅ `test_invariant_best_race_only_returns_unique_players`
- ✅ `test_unranked_players_excluded_from_leaderboard`

### SQL Queries for Production Verification

To verify this issue exists in production and confirm the fix works, run these queries:

#### Query 1: Find affected players
```sql
WITH player_races AS (
  SELECT 
    discord_uid,
    player_name,
    race,
    mmr,
    games_played,
    last_played,
    CASE 
      WHEN games_played > 0 
           AND last_played >= (NOW() - INTERVAL '14 days')
      THEN true
      ELSE false
    END AS is_ranked,
    ROW_NUMBER() OVER (PARTITION BY discord_uid ORDER BY mmr DESC, last_played DESC) AS mmr_rank
  FROM mmrs_1v1
),
best_race AS (
  SELECT * FROM player_races WHERE mmr_rank = 1
),
has_ranked_race AS (
  SELECT DISTINCT discord_uid
  FROM player_races
  WHERE is_ranked = true
)
SELECT 
  br.discord_uid,
  br.player_name,
  br.race AS best_race,
  br.mmr AS best_mmr,
  br.is_ranked AS best_race_is_ranked,
  (
    SELECT STRING_AGG(
      race || ' (' || mmr || ' MMR, ' || 
      CASE WHEN is_ranked THEN 'RANKED' ELSE 'UNRANKED' END || ')',
      ', '
    )
    FROM player_races pr
    WHERE pr.discord_uid = br.discord_uid AND pr.mmr_rank > 1
  ) AS other_races
FROM best_race br
WHERE br.is_ranked = false
  AND br.discord_uid IN (SELECT discord_uid FROM has_ranked_race)
ORDER BY br.mmr DESC;
```

#### Query 2: Count affected players
```sql
WITH player_races AS (
  SELECT 
    discord_uid,
    race,
    mmr,
    games_played,
    last_played,
    CASE 
      WHEN games_played > 0 
           AND last_played >= (NOW() - INTERVAL '14 days')
      THEN 1 ELSE 0
    END AS is_ranked,
    ROW_NUMBER() OVER (PARTITION BY discord_uid ORDER BY mmr DESC, last_played DESC) AS mmr_rank
  FROM mmrs_1v1
)
SELECT 
  COUNT(*) AS affected_players
FROM player_races best
WHERE best.mmr_rank = 1 
  AND best.is_ranked = 0
  AND EXISTS (
    SELECT 1 FROM player_races other
    WHERE other.discord_uid = best.discord_uid
      AND other.is_ranked = 1
  );
```

## Impact

### Before Fix
- Players with multiple races could disappear from leaderboard if their highest MMR race became inactive
- User confusion: "I just played yesterday, why am I not on the leaderboard?"
- Inaccurate representation of active player population

### After Fix
- All players with at least one active ranked race appear on the leaderboard
- "Best Race Only" shows each player's best **active** race
- Accurate and complete leaderboard representation

## Deployment Notes

1. **No database migration required** - This is a pure logic fix
2. **No configuration changes needed**
3. **Backward compatible** - Does not change any APIs or data structures
4. **Immediate effect** - Works as soon as code is deployed
5. **Safe to rollback** - Can revert if issues arise (though none are expected)

## Related Files

- `src/backend/services/leaderboard_service.py` - Main fix
- `tests/characterize/test_leaderboard_filtering_logic.py` - Test updates
- `docs/architecture/` - May want to update filtering documentation

## Date
November 14, 2025

