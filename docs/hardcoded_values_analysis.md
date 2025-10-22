# Hardcoded Values Analysis

This document outlines hardcoded lists of values found in the repository that could be refactored into constants or moved to a configuration file for better maintainability and clarity.

## High Priority

These are values that are fundamental to the application's logic or UI and are strong candidates for refactoring.

| File | Line | Hardcoded Value | Recommendation |
| --- | --- | --- | --- |
| `src/backend/services/ranking_service.py` | 55 | `["d_rank", "c_rank", "e_rank", "b_rank", "a_rank", "f_rank", "s_rank"]` | This is already a constant (`DISTRIBUTION_ORDER`), which is good. No change needed, but it's a good example. |
| `src/bot/commands/queue_command.py` | 519 | `[":one:", ":two:", ":three:", ":four:"]` | Move to `config.py` as `NUMBER_EMOTES`. This makes it easier to change UI elements. |
| `src/backend/db/create_table.py` | 192, 236, 237 | `["bw_terran", ...], ["sc2_terran", ...]` | Centralize race lists in `config.py` (e.g., `BW_RACES`, `SC2_RACES`, `ALL_RACES`). |
| `src/backend/db/create_table.py` | 269 | `["Arkanoid", "Khione", ...]` | Centralize the default map list in `config.py` as `DEFAULT_MAP_POOL`. |
| `src/backend/services/countries_service.py` | 44, 65 | `["XX", "ZZ"]` | Define as a constant in `config.py`, e.g., `IGNORED_COUNTRY_CODES = ["XX", "ZZ"]`. |
| `src/bot/utils/discord_utils.py` | 177 | `["XX", "ZZ"]` | Use the `IGNORED_COUNTRY_CODES` constant from `config.py`. |
| `src/bot/commands/queue_command.py` | 844 | `["aborted", "conflict", ...]` | Create a `MatchResult` Enum or a set of constants in `config.py` for match statuses. |
| `src/bot/commands/prune_command.py` | 105, 107 | `["oldest message", ...], ["jump to message", ...]` | Move these keyword lists to `config.py` to make them easier to configure. |
| `scripts/generate_realistic_mock_data.py` | 109 | `["Pro", "Ace", ...]` | Move to a constants file or a configuration that the script can read. |

## Medium Priority

These values could be refactored for better clarity and to avoid potential typos, but are less critical than the high-priority items.

| File | Line | Hardcoded Value | Recommendation |
| --- | --- | --- | --- |
| `src/backend/services/leaderboard_service.py` | 207, 218 | `["mmr", "last_played"]` | Define column names as constants (e.g., `MMR_COLUMN = "mmr"`) to avoid typos. |
| `src/backend/services/data_access_service.py` | 753-775 | `["player_1_discord_uid", ...]` | Similar to the above, define DataFrame column names as constants. |

## Low Priority

These values are mostly found in test files. Refactoring them is not a high priority, but it's good practice to be aware of them.

| File | Line | Hardcoded Value | Recommendation |
| --- | --- | --- | --- |
| `tests/backend/services/test_matchmaking_service.py` | 397 | `["US East", "US West", "Europe", "Asia"]` | For tests, this is generally acceptable. If this list were used in application code, it should be in `config.py`. |
| Various `tests/` files | - | `["bw_terran", "sc2_zerg"]`, etc. | These are specific to test cases and are acceptable as hardcoded values within the tests. |
| `tests/run_tests.py` | 10 | `["-m", "not slow", "-q"]` | This is already a constant (`DEFAULT_PYTEST_ARGS`), which is good practice. |
