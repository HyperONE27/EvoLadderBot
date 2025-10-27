# Feature: Implement verification of replays uploaded by users

## Context

Currently, the replay upload flow stores replay metadata in the `replays` table after parsing, but no in-bot feedback confirms whether the uploaded replay actually matches the queued match. While we cannot prevent users from, say, accidentally picking the wrong map, we can enforce competitive integrity by verifying that players are indeed setting up their matches correctly.

We can do this by **surfacing validation results** directly in the `MatchFoundViewEmbed` shown to players after a replay upload. Data parsed from replays exists in Polars dataframes in memory, specifically the `_replays_df` DataFrame. We can compare this with the details assigned to the match in `_matches_1v1_df` and cross-verify that the game was actually played with the correct parameters.

If everything checks out, we can streamline the match reporting process by automatically reporting the winner. If not, players will have to fill out the match report. However, for the first phase of implementation, we will only add the verification results without automatically recording the result.

## Proposal

Add additional content at the bottom of ReplayDetailsEmbed in `replay_details_embed.py`.

It might look a little something like this:

```
**Replay Verification**
- Races match: ✅ Races played correspond to races played queued with.
- Map name matches: ✅ Map used corresponds to the map assigned.
- Timestamp matches: ✅ Match was initiated within ~20 minutes of match assignment.
- No observers: ✅ No unverified observers detected.
- Winner detection: ✅ Match details verified, automatically reporting the winner.

✅ No issues detected.
```

Or alternatively:

```
**Replay Verification**
- Races match: ❌ Races played DO NOT correspond to races played queued with.
  - Please ensure that both players select the races that they queued with.
- Map name matches: ❌ Map used DOES NOT correspond to the map assigned.
  - Please ensure that you use the provided map link and author information to select the correct map.
- Timestamp matches: ❌ Match was NOT initiated within ~20 minutes of match assignment.
  - Please ensure that you initiated your matches in a timely manner after assignment.
- No observers: ❌ Unauthorized observers detected.
  - Please ensure you do not have unauthorized observers in the lobby during games.
- Winner detection: ❌ Match details NOT verified, please report the winner manually.

⚠️ One or more match parameters were incorrect. The system will reflect the record.
```

We should automatically detect and report the winner IF AND ONLY IF all of the first four criteria are verified.

## Specifications

### Integration Points

1. **Modified Files:**
   - `src/bot/components/replay_details_embed.py` - Updated to accept optional `verification_results` parameter and display verification status
   - `src/backend/services/match_completion_service.py` - Added replay verification logic and auto-reporting
   - `src/bot/commands/queue_command.py` - Updated `store_replay_background` to orchestrate verification flow

2. **New Methods in MatchCompletionService:**
   - `start_replay_verification()` - Public entry point for starting verification
   - `_verify_replay_task()` - Background worker that performs verification and calls callback
   - `_verify_races()` - Checks if replay races match assigned races
   - `_verify_map()` - Checks if replay map matches assigned map (with fuzzy matching)
   - `_verify_timestamp()` - Checks if replay was created within 20 minutes of match assignment
   - `_verify_observers()` - Checks that no observers are present
   - `_determine_winner_report()` - Determines winner report value from replay result

3. **Data Flow:**
   - User uploads replay → `on_message` handler processes upload
   - Replay is parsed and stored → `store_replay_background` is called
   - Initial embed with "Verifying..." is sent to channel
   - `match_completion_service.start_replay_verification()` is called with callback
   - Background task performs all verification checks
   - If all checks pass, auto-reports match result for uploader
   - Callback updates embed with final verification results
   - If all checks pass, callback also updates uploader's MatchFoundView to show confirmed result


### Data Sources
- From `_replays_df`:
  - `map_name`, `player_1_race`, `player_2_race`, `replay_date`, `duration`, `result`, `observers`
- From `_matches_1v1_df`:
  - `map`, `played_at`, `player_1_race`, `player_2_race`

### Calculations
- Races match: Both races should be unique and the count of each race in the replay should match the count of each race in the assigned match details.
- Map name matches: Simple string comparison.
- Timestamp matches: The replay date reflects roughly the time at which the replay file as created (corresponding to the time the player leaves the game). This can be different for the two opponents, but we're not too concerned about this. Anyway, simply subtract the duration of the game from the timestamp the file was created to get the timestamp the game started at.
  - The precision window is as large as 20 minutes to allow for a little bit of inefficiency in finding matches in-game, as well as for people who decide to screw around in the replay after the match result is determined.
- No observers: check the observers field.
- Winner detection: check that all of the above pass, then find the race of the player who won, find the player in the assigned match data who has that races, and mark them as the winner. (We should mutate the view/corresponding UI elements when we do this, too.)
  - We avoid directly matching the name of the player who won in the replay to the names of the players assigned in the match, because players can have incongruent IDs, but their races should match.

## Testing
Write this JSON into the test file:

```json
[{"idx":13,"id":14,"player_1_discord_uid":"218147282875318274","player_2_discord_uid":"473117604488151043","player_1_race":"bw_zerg","player_2_race":"sc2_protoss","player_1_mmr":1610,"player_2_mmr":1500,"player_1_report":2,"player_2_report":2,"match_result":2,"mmr_change":-25,"map_played":"Tokamak LE","server_used":"USE","played_at":"2025-10-24 06:42:00+00","player_1_replay_path":"https://ibigtopmfsmarkujjfen.supabase.co/storage/v1/object/public/replays/14/3812a4e1c1ea9c34ddda_1761288313.SC2Replay","player_1_replay_time":"2025-10-24 06:45:14+00","player_2_replay_path":"https://ibigtopmfsmarkujjfen.supabase.co/storage/v1/object/public/replays/14/13fc2de194b91eabaee5_1761288312.SC2Replay","player_2_replay_time":"2025-10-24 06:45:13+00"}]
```

This corresponds to the row of the `matches_1v1` SQL table that we will load into a minimal `_matches_1v1_df`.

We also have test replays in `/tests/test_data/test_replay_files`:
- `HyperONEgunnerTokamak.SC2Replay`
- `DarkReBellioNIsles.SC2Replay`
- `threepointPSIArcGoldenWall.SC2Replay`

Parse them and store the relevant output in a minimal `_replays_df`.

The first of these should match in all of the above criteria, the second and third should fail in all of them.

## Constraints

## Critical Data Integrity Fixes

### Issue 1: Short Map Names in Database
**Problem:** The matchmaking service was storing short map names (e.g., "Tokamak") instead of full official names (e.g., "Tokamak LE") in the database.

**Fix Applied:** Modified `src/backend/services/matchmaking_service.py` to convert short names to full names before storing:
```python
map_short_name = random.choice(available_maps)
# Convert short name to full map name for storage
map_full_name = self.maps_service.get_map_name(map_short_name)
# Store map_full_name in database instead of map_short_name
```

### Issue 2: Fuzzy Map Matching (Security Risk)
**Problem:** Initial implementation used fuzzy matching (remove " LE" suffixes, check containment) which could allow validation of cheat map names. Example: "Fake Tokamak" would match "Tokamak LE" due to containment logic.

**Fix Applied:** Reverted to strict, exact matching in `src/backend/services/match_completion_service.py`:
```python
# Case-insensitive exact comparison (full map names must match exactly)
return match_map.lower() == replay_map.lower()
```

### Test Data Alignment
Updated test data in `tests/test_replay_verification.py` to use full map names ("Tokamak LE" instead of "Tokamak").

### Backwards Compatibility Note
- Matches created before this fix will have short names in the database. These will correctly fail map verification until the database is migrated to full names.
- This is the intended behavior - enforcing strict compliance going forward.
- `data/misc/maps.json` remains the single source of truth for official map names.

## Summary