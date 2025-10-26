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