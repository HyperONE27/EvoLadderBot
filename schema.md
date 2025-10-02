My current plan for the SQL database schema is:


```sql
CREATE TABLE players (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_uid             INTEGER NOT NULL,
    player_name             TEXT,
    battletag               TEXT,
    alt_player_name_1       TEXT,
    alt_player_name_2       TEXT,
    country                 TEXT,
    region                  TEXT,
    accepted_tos            BOOLEAN DEFAULT FALSE,
    accepted_tos_date       TIMESTAMP,
    completed_setup         BOOLEAN DEFAULT FALSE,
    completed_setup_date    TIMESTAMP,
    activation_code         TEXT,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

/*
In addition to a simple tracker for when a player last updates their profile
*/

CREATE TABLE player_action_logs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_uid             INTEGER NOT NULL,
    player_name             TEXT NOT NULL,
    setting_name            TEXT NOT NULL,
    old_value               TEXT,
    new_value               TEXT,
    changed_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changed_by              TEXT DEFAULT 'player'                     -- options include "player", "admin", "system"
)

/*
Most players only play 1-2 races.
Therefore, we avoid having several columns for each race, which would create many persistent empty cells.
Instead, we create a row for each race that someone players.
We check to see if a player has queued on a particular race before, and create the new row if they have not.

Three tables for each gamemode, as shown below: MMRs, matches, and preferences.
The preferences table is, of course, much smaller than the others.
This is because it has fewer columns, and each player will only have 1 corresponding row.

All MMR decay logic is implemented in a centralized reader/writer service.
This ensures that:
- Decay adjustments are applied consistently across all queries.
- Schema sprawl is avoided (no need to store redundant "decayed" values).
- Future rule changes require updates in only one location.

By design, the schema holds only the essential fields:
- The base MMR (source of truth).
- The last activity timestamp. 

Any derived or decayed values are calculated through the backend abstraction.
*/

CREATE TABLE mmrs_1v1 (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_uid             INTEGER NOT NULL,
    player_name             TEXT NOT NULL,
    race                    TEXT NOT NULL,
    mmr                     INTEGER NOT NULL,
    games_played            INTEGER DEFAULT 0,
    games_won               INTEGER DEFAULT 0,
    games_lost              INTEGER DEFAULT 0,
    games_drawn             INTEGER DEFAULT 0,
    last_played             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE matches_1v1 (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    player_1_discord_uid    INTEGER NOT NULL,
    player_1_player_name    TEXT NOT NULL,
    player_2_discord_uid    INTEGER NOT NULL,
    player_2_player_name    TEXT NOT NULL,
    winner_discord_uid      INTEGER,
    winner_player_name      TEXT,
    map_played              TEXT NOT NULL,
    server_used             TEXT NOT NULL,
    played_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE preferences_1v1 (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_uid             INTEGER NOT NULL,
    player_name             TEXT NOT NULL,
    last_chosen_races       TEXT,   -- e.g., ["bw_terran", "sc2_zerg"]; i.e., JSON array
    last_chosen_vetoes      TEXT    -- e.g., ["Arkanoid", "Khione", "Pylon"]; i.e., JSON array
);

/*
MMR tables foar additional game modes (e.g., 3v3, FFA) will follow this same structure.

As an example:
*/

CREATE TABLE mmrs_2v2 (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    player_1_discord_uid    INTEGER NOT NULL,
    player_2_discord_uid    INTEGER NOT NULL,       -- NULL for solo queue, filled in for party queue
    player_1_name           TEXT NOT NULL,
    player_2_name           TEXT,                   -- NULL for solo queue, filled in for party queue
    player_1_race           TEXT NOT NULL,
    player_2_race           TEXT,                   -- NULL for solo queue, filled in for party queue
    mmr                     INTEGER NOT NULL,       -- goes up/down as a group
    last_played             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE matches_2v2 (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    player_1_discord_uid    INTEGER NOT NULL,       -- member of team 1
    player_1_name           TEXT NOT NULL,
    player_2_discord_uid    INTEGER NOT NULL,       -- member of team 1
    player_2_name           TEXT NOT NULL,
    player_3_discord_uid    INTEGER NOT NULL,       -- member of team 2
    player_3_name           TEXT NOT NULL,
    player_4_discord_uid    INTEGER NOT NULL,       -- member of team 2
    player_4_name           TEXT NOT NULL,
    winner_discord_uid      INTEGER,                -- e.g., ["player_1_discord_uid", "player_2_discord_uid"]
    winner_player_name      TEXT,                   -- e.g., ["player_3_player_name", "player_4_player_name"]
    map_played              TEXT NOT NULL,
    server_used             TEXT NOT NULL,
    played_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE preferences_2v2 (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    player_1_discord_uid    INTEGER NOT NULL,
    player_2_discord_uid    INTEGER NOT NULL,       -- NULL for solo queue, filled in for party queue
    player_1_name           TEXT NOT NULL,
    player_2_name           TEXT,                   -- NULL for solo queue, filled in for party queue
    player_1_race           TEXT NOT NULL,
    player_2_race           TEXT,                   -- NULL for solo queue, filled in for party queue
    last_chosen_races       TEXT,   -- e.g., ["bw_terran", "sc2_zerg"]
    last_chosen_vetoes      TEXT    -- e.g., ["Arkanoid", "Khione", "Pylon"]
);