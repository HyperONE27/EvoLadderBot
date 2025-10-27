# Feature: Implement verification of replays uploaded by users

## Context

Currently, the replay upload flow stores replay metadata in the `replays` table after parsing, but no in-bot feedback confirms whether the uploaded replay actually matches the queued match. While we cannot prevent users from, say, accidentally picking the wrong map, we can enforce competitive integrity by verifying that players are indeed setting up their matches correctly.

We can do this by **surfacing validation results** directly in the `MatchFoundViewEmbed` shown to players after a replay upload. Data parsed from replays exists in Polars dataframes in memory, specifically the `_replays_df` DataFrame. We can compare this with the details assigned to the match in `_matches_1v1_df` and cross-verify that the game was actually played with the correct parameters.

## Proposal

Add additional content at the bottom of ReplayDetailsEmbed in `replay_details_embed.py`.

It might look a little something like this:

```
**Replay Verification**
- Races match: ✅ Races played correspond to races played queued with.
- Map name matches: ✅ Map used corresponds to the map assigned.
- Timestamp matches: ✅ Match was initiated within ~15 minutes of match assignment.
- Winner detection: ✅ Match details verified, automatically reporting the winner.
```

Or alternatively:

```
**Replay Verification**
- Races match: ❌ Races played DO NOT correspond to races played queued with.
- Map name matches: ❌ Map used DOES NOT correspond to the map assigned.
- Timestamp matches: ❌ Match was NOT initiated within ~15 minutes of match assignment.
- Winner detection: ❌ Match details NOT verified, please report the winner manually.
```

We should automatically detect and report the winner IF AND ONLY IF all of the first three criteria are verified.

## Specifications

### Integration Points



### Data Sources
- From `_replays_df`:
  - 
- From `_matches_1v1_df`:
  - `map`, `played_at`, `p1_race`


## Testing


## Constraints


## Summary


===

# Feature: Implement Verification of Replays Uploaded by Users

## Context
Currently, the replay upload flow stores replay metadata in the `replays` table after parsing, but no in-bot feedback confirms whether the uploaded replay actually matches the queued match. This leads to occasional mismatches (e.g., wrong map, swapped races, incorrect replay file) that require manual correction.

We want to close this loop by **surfacing validation results** directly in the `MatchFoundViewEmbed` shown to players after a replay upload.

The replay data (races, map, duration, replay_date, winner, etc.) is already available from the `replays` table. The `matches_1v1` table contains authoritative match metadata (`player_races`, `map`, `played_at`). The intent is to cross-verify these two sources and display a summarized validation report in Discord.

---

## Proposal
We will extend `MatchFoundViewEmbed` to include a new section titled **"Replay Analysis"**, which confirms the validity of the uploaded replay and optionally auto-selects the likely winner.

The following checks will be performed:
- **Races match:** Replay races correspond to players’ queued races.
- **Map name matches:** Replay map matches the assigned map.
- **Timestamp matches:** `(replay_date - duration)` is within ±15 minutes of the `played_at` timestamp in `matches_1v1`.
- **Winner detection:** If the replay parser identifies a winner and the two races are unique, we identify the corresponding player by race and preselect them in the result dropdown.

If all three checks succeed and the winner is unambiguous:
> “✅ {player_name} automatically selected as the winner — please confirm.”

Otherwise:
> “❌ Could not determine winner automatically — please select manually.”

We will **not** reject replays that fail these checks; we only surface them for transparency and possible admin review later.

---

## Specifications
### Integration Points
- **Bot UI:** `MatchFoundViewEmbed` in `/queue`
- **Backend:** Replay validation logic introduced in a new `replay_analysis_service.py`
- **Supporting services:** `match_completion_service.py`, `DataAccessService`, and `maps_service` for normalization.

### Data Sources
- From `replays` table:
  - `map_name`, `player_1_race`, `player_2_race`, `replay_date`, `duration`, `result`
- From `matches_1v1` table:
  - `map`, `played_at`, `p1_race`, `p2_race`

### Core Function
A new coroutine:
```python
async def analyze_replay(replay_info: dict, match_data: dict) -> dict:
    """Compares replay and match metadata and infers winner."""


```
I'll help you find the details of the replays and matches dataframes. Let me search the codebase for where these are defined.

[2 tools called]

Now let me get the full details from the DataAccessService where both dataframes are loaded:

[2 tools called]

Let me search for the schema file:

[1 tool called]

Let me check the docs for schema information:

[1 tool called]

Perfect! Now let me get the complete picture by reading the relevant sections of the DataAccessService:

[1 tool called]

Perfect! Now I have all the information I need. Let me compile the complete details for you:

## **Replays DataFrame Columns**

Based on the database schema and how it's loaded in `DataAccessService`, the **replays** dataframe has the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `id` | Int64 | Primary key, auto-incremented |
| `replay_path` | Utf8 | Path/URL to the replay file (unique) |
| `replay_hash` | Utf8 | Blake2b hash of replay bytes (80-bit) |
| `replay_date` | Utf8 | Timestamp when replay was played |
| `player_1_name` | Utf8 | Name of player 1 |
| `player_2_name` | Utf8 | Name of player 2 |
| `player_1_race` | Utf8 | Race of player 1 (sc2_terran, sc2_zerg, sc2_protoss, bw_terran, bw_zerg, bw_protoss) |
| `player_2_race` | Utf8 | Race of player 2 |
| `result` | Int64 | Match result (0=draw, 1=player 1 won, 2=player 2 won) |
| `player_1_handle` | Utf8 | Gamer tag/handle of player 1 |
| `player_2_handle` | Utf8 | Gamer tag/handle of player 2 |
| `observers` | Utf8 | JSON string of observer list |
| `map_name` | Utf8 | Name of the map played |
| `duration` | Int64 | Duration of replay in seconds |
| `uploaded_at` | Utf8 | Timestamp when replay was uploaded |

**Location loaded:** `DataAccessService._replays_df` - loads the **last 1000 replays** ordered by ID descending

---

## **Matches 1v1 DataFrame Columns**

The **matches_1v1** dataframe has the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `id` | Int64 | Primary key, match ID |
| `player_1_discord_uid` | Int64 | Discord user ID of player 1 |
| `player_2_discord_uid` | Int64 | Discord user ID of player 2 |
| `player_1_race` | Utf8 | Race of player 1 |
| `player_2_race` | Utf8 | Race of player 2 |
| `map_played` | Utf8 | Map name for the match |
| `server_choice` | Utf8 | Server used (e.g., US, EU, KR) |
| `player_1_mmr` | Int64 | Player 1's MMR at match time |
| `player_2_mmr` | Int64 | Player 2's MMR at match time |
| `mmr_change` | Float64 | MMR change amount (positive = player 1 gained, negative = player 2 gained) |
| `played_at` | Utf8 | Timestamp when match was played |
| `player_1_report` | Int64 | Player 1's match result report (nullable) |
| `player_2_report` | Int64 | Player 2's match result report (nullable) |
| `match_result` | Int64 | Final match result (-1=aborted, 1=player 1 won, 2=player 2 won, null/0=in progress) |
| `player_1_replay_path` | Utf8 | Path/URL to player 1's replay (nullable) |
| `player_2_replay_path` | Utf8 | Path/URL to player 2's replay (nullable) |
| `player_1_replay_time` | Utf8 | Timestamp when player 1 uploaded replay (nullable) |
| `player_2_replay_time` | Utf8 | Timestamp when player 2 uploaded replay (nullable) |
| `status` | Utf8 | Match status: `IN_PROGRESS`, `PROCESSING_COMPLETION`, `COMPLETE`, `ABORTED`, or `CONFLICT` |

**Location loaded:** `DataAccessService._matches_1v1_df` - loads the **last 1000 matches** ordered by `played_at` descending

**Status inference logic:** If status column is missing from database:
- `ABORTED` if `match_result == -1`
- `COMPLETE` if `match_result` is not null and not 0 or -1
- `IN_PROGRESS` otherwise
```

```
[1 tool called]

Let me read the full loading section more completely:

[1 tool called]

Perfect! Now I have all the information. Let me compile the size limits for all Polars DataFrames:

## **Polars DataFrame Size Limits**

Here are the row count and memory limits for all DataFrames loaded in `DataAccessService`:

| DataFrame | Row Limit | Loading Strategy | Notes |
|-----------|-----------|------------------|-------|
| **`_players_df`** | **UNLIMITED** (all players) | `get_all_players()` - loads entire table | No explicit limit; grows with player base |
| **`_mmrs_1v1_df`** | **10,000 rows** | `get_leaderboard_1v1()` with limit=10,000 | Top 10,000 entries by MMR for leaderboard operations |
| **`_preferences_1v1_df`** | **UNLIMITED** (all users) | `SELECT * FROM preferences_1v1` | No limit; should be ≤ players count (one per player max) |
| **`_matches_1v1_df`** | **1,000 rows** | Recent matches ordered by `played_at DESC LIMIT 1000` | Last 1,000 matches only; configured for memory efficiency |
| **`_replays_df`** | **1,000 rows** | Recent replays ordered by `id DESC LIMIT 1000` | Last 1,000 replays only |

---

## **Memory Footprint Estimates**

**Approximate memory usage per row:**

- **Players**: ~200 bytes/row → ~200KB per 1,000 players
- **MMRs 1v1**: ~150 bytes/row → ~1.5MB for 10,000 rows
- **Preferences 1v1**: ~100 bytes/row → ~100KB per 1,000 users
- **Matches 1v1**: ~500 bytes/row → ~500KB for 1,000 matches
- **Replays**: ~1KB/row → ~1MB for 1,000 replays

**Total estimated memory**: **~4-5MB** for all hot tables (assuming ~5K players)

---

## **Key Design Notes**

1. **Unlimited loads**: Players and preferences are loaded entirely because they're essential for lookups and typically manageable in size
2. **Capped loads**: Matches and replays are limited to **last 1,000** each to prevent unbounded memory growth
3. **Leaderboard optimization**: MMRs are capped at **10,000** rows (top tier players) for leaderboard queries
4. **Comment in code** (line 227): *"Load recent matches only (last 1000) to keep memory usage reasonable"*
5. **Comment in code** (line 277): *"Load recent replays only (last 1000)"*
```