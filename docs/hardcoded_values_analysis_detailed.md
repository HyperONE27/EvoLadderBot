# In-Depth Analysis of Hardcoded Values

This document provides a detailed analysis of hardcoded values in the repository. Each item is evaluated based on its impact, feasibility of refactoring, likelihood of future changes, and instances of duplication.

---

## High Priority: Core Application Logic & Configuration

These values are critical to the application's behavior and should be externalized to `src/bot/config.py` or a dedicated `src/backend/core/constants.py` module.

### 1. Race & Map Definitions

-   **Files:**
    -   `src/backend/db/create_table.py` (lines 192, 236, 237, 269)
    -   Numerous files in `tests/`
-   **Values:**
    -   `races = ["bw_terran", "bw_protoss", "bw_zerg", "sc2_terran", "sc2_protoss", "sc2_zerg"]`
    -   `map_names = ["Arkanoid", "Khione", "Pylon", "Neo", ...]`
-   **Analysis:**
    -   **Impact:** Very High. This is core domain data. Hardcoding it makes adding or removing races/maps a widespread code change. Centralizing it provides a single source of truth.
    -   **Feasibility:** High. Create lists like `SUPPORTED_RACES` and `DEFAULT_MAP_POOL` in `config.py` and import them where needed.
    -   **Likelihood of Change:** High. Map pools change seasonally, and new races or game modes could be added in the future.
    -   **Duplication:** High. These lists are duplicated across application code and multiple test files.

### 2. Match Result Statuses

-   **File:** `src/bot/commands/queue_command.py` (line 844)
-   **Value:** `["aborted", "conflict", "player1_win", "player2_win", "draw"]`
-   **Analysis:**
    -   **Impact:** High. These are critical state identifiers. Using strings is prone to typos. An Enum would provide type safety and auto-completion.
    -   **Feasibility:** High. Define a `MatchStatus(Enum)` class in a constants module.
    -   **Likelihood of Change:** Low. These statuses are fundamental, but using an Enum is still best practice.
    -   **Duplication:** Currently low, but these values are likely to be used elsewhere (e.g., in analytics, match history).

### 3. Special Country Codes

-   **Files:**
    -   `src/backend/services/countries_service.py` (lines 44, 65)
    -   `src/bot/utils/discord_utils.py` (line 177)
-   **Value:** `["XX", "ZZ"]`
-   **Analysis:**
    -   **Impact:** Medium. This is a "magic value". Giving it a constant name like `IGNORED_COUNTRY_CODES` improves code readability and intent.
    -   **Feasibility:** Very High. A simple one-line addition to `config.py`.
    -   **Likelihood of Change:** Low. But if another code needed to be ignored, a centralized list is better.
    -   **Duplication:** Yes, found in two separate locations. A prime candidate for centralization.

---

## Medium Priority: UI Elements & Minor Logic

These values affect user-facing elements or non-critical logic. Refactoring them improves maintainability.

### 1. UI Emotes

-   **File:** `src/bot/commands/queue_command.py` (line 519)
-   **Value:** `[":one:", ":two:", ":three:", ":four:"]`
-   **Analysis:**
    -   **Impact:** Medium. Centralizing UI elements makes it easier to maintain a consistent look and feel.
    -   **Feasibility:** High. Move to a `UI_CONSTANTS` section or dictionary in `config.py`.
    -   **Likelihood of Change:** Medium. You might want to switch to different emoji styles or add more numbers in the future.
    -   **Duplication:** Low.

### 2. Pruning Keywords

-   **File:** `src/bot/commands/prune_command.py` (lines 105, 107)
-   **Values:** `["oldest message", ...]` and `["jump to message", ...]`
-   **Analysis:**
    -   **Impact:** Low. These are specific to one command's logic.
    -   **Feasibility:** High. Can be defined as constants at the top of the file or moved to config if they need to be configurable by an admin in the future.
    -   **Likelihood of Change:** Low. Unlikely to change unless Discord's embed structure changes.
    -   **Duplication:** Low.

---

## Low Priority: DataFrame Column Names & Test Data

These values are mostly internal or used in non-production code.

### 1. DataFrame Column Names

-   **Files:**
    -   `src/backend/services/leaderboard_service.py` (lines 207, 218)
    -   `src/backend/services/data_access_service.py` (multiple lines)
-   **Value:** `["mmr", "last_played"]`, `["player_1_discord_uid", ...]`
-   **Analysis:**
    -   **Impact:** Medium. Using string literals for column names is a common source of bugs (typos). Defining them as constants (e.g., `COL_MMR = "mmr"`) mitigates this risk.
    -   **Feasibility:** Medium. It requires adding a constants file and updating all references, which can be tedious but is straightforward.
    -   **Likelihood of Change:** Low. Database schemas are usually stable.
    -   **Duplication:** High. The same column names are used in multiple queries and operations.

### 2. Test-Specific Data

-   **Files:** All files within `tests/`
-   **Values:** Various lists of races, maps, servers, etc.
-   **Analysis:**
    -   **Impact:** Low. Hardcoded values in tests are often necessary to ensure predictable outcomes for specific scenarios.
    -   **Feasibility:** Low. Abstracting these would likely complicate tests for little benefit.
    -   **Likelihood of Change:** High, as new test cases are added.
    -   **Recommendation:** It is acceptable to keep these as is. If the application code starts using constants from `config.py`, the tests should be updated to use them as well for consistency.
