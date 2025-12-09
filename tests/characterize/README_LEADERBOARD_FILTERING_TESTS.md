# Leaderboard Filtering Logic - Characterization & Regression Tests

## Overview

This test suite documents and enforces the correct behavior of the leaderboard filtering system, particularly the critical interaction between the "Best Race Only" filter and other filters (rank, country, race).

## Background: The Order-of-Operations Bug

During development, we discovered a subtle but critical bug in the filtering logic. When users applied both "Best Race Only" and a rank filter (e.g., "A-Rank"), the system was incorrectly applying filters in the wrong order:

**Incorrect Order (Bug)**:
1. Apply rank filter to all 1081 player-race combinations → Get all A-rank player-races
2. Apply "best race only" to that subset → Get one entry per player from the A-rank subset
3. Result: Distribution mirrored the overall population (flat distribution)

**Correct Order (Fix)**:
1. Apply "best race only" to get 256 unique players (one race each)
2. Apply rank filter to this smaller pool → Get A-rank players from the best-race pool
3. Result: Top-heavy distribution (most players' best races are in higher ranks)

The bug was revealed by a mathematical observation: When filtering by rank with "best race only" active, the sum of all rank counts (S+A+B+C+D+E+F) equaled 825, not the expected 256. This 825 + 256 = 1081, which is exactly the total number of player-races with ≥1 game played—a smoking gun that the filters were operating on the wrong pool.

## Test Suite Structure

### 1. Characterization Tests
These tests document the **correct** behavior after the fix:
- `test_baseline_player_counts`: Verifies the baseline counts (all races vs. best race only)
- `test_best_race_only_rank_distribution`: Captures the expected rank distribution with best_race_only

### 2. Regression Tests
These tests will **fail** if the bug is reintroduced:
- `test_sum_of_filtered_best_race_ranks_equals_total`: The mathematical test that revealed the bug
  - Asserts: Sum of rank-filtered counts = Total best-race count
  - If this fails, the order-of-operations bug has returned

### 3. Invariant Tests
These tests enforce high-level system properties:
- `test_invariant_adding_filters_never_increases_player_count`: Filters must be reductive
- `test_invariant_best_race_only_returns_unique_players`: No duplicate players in best-race mode

### 4. Additional Tests
- `test_unranked_players_excluded_from_leaderboard`: Verifies u_rank exclusion logic

## Running the Tests

### Prerequisites
These tests require:
1. A live database connection with real production data
2. The `DataAccessService` to be properly initialized
3. Database credentials configured in environment variables

### Execution

**With a live database connection**:
```bash
python -m pytest tests/characterize/test_leaderboard_filtering_logic.py -v -s
```

**Note**: These tests are currently set up to run against live data to ensure they accurately characterize real-world behavior. If you need to run them in CI/CD without database access, you'll need to:
1. Export a snapshot of the MMR data to a fixture file
2. Modify the fixture to load from that snapshot instead of the database

## Expected Test Output

When all tests pass, you should see:
```
test_baseline_player_counts PASSED
test_best_race_only_rank_distribution PASSED
test_sum_of_filtered_best_race_ranks_equals_total PASSED
test_invariant_adding_filters_never_increases_player_count PASSED
test_invariant_best_race_only_returns_unique_players PASSED
test_unranked_players_excluded_from_leaderboard PASSED
```

The regression test (`test_sum_of_filtered_best_race_ranks_equals_total`) is the **critical** one—if it fails, the bug has been reintroduced.

## Code Location

The fix is implemented in:
- **File**: `src/backend/services/leaderboard_service.py`
- **Function**: `_get_filtered_leaderboard_dataframe()`
- **Key Change**: The `best_race_only` filter is now applied **FIRST** (lines 88-99), before any other filters

```python
# FIRST: Apply best_race_only filter if enabled
# This MUST happen BEFORE other filters to ensure correct rank distribution
if best_race_only:
    df = (df
        .sort(["mmr", "last_played"], descending=[True, True])
        .group_by("discord_uid", maintain_order=True)
        .first()
    )

# THEN: Apply other filters (country, race, rank)
filter_conditions = []
if rank_filter:
    filter_conditions.append(pl.col("rank") == rank_filter)
# ... etc
```

## Maintenance

- **When to run**: After any changes to leaderboard filtering logic
- **When to update**: If the leaderboard filtering requirements change
- **Red flag**: If `test_sum_of_filtered_best_race_ranks_equals_total` fails, investigate immediately

## Future Improvements

To make these tests runnable in CI/CD without database access:
1. Create a `tests/fixtures/leaderboard_snapshot.json` with representative data
2. Update the fixture to load from this snapshot
3. Ensure the snapshot includes enough diversity (multiple players, races, ranks, countries)

