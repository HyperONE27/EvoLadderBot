My current plan for the SQL database schema is:


```sql
CREATE TABLE users (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT
    discord_uid             INTEGER
    player_name             TEXT NOT NULL
    alt_player_name_1       TEXT
    alt_player_name_2       TEXT
    battletag               TEXT
    country                 TEXT
    region                  TEXT
    accepted_tos            BOOLEAN DEFAULT FALSE
    accepted_tos_date       TIMESTAMP
    completed_setup         BOOLEAN DEFAULT FALSE
    completed_setup_date    TIMESTAMP
    created_at              TIMESTAMP
    updated_at              TIMESTAMP
);

CREATE TABLE user_action_logs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT
    discord_uid             INTEGER
    player_name             TEXT NOT NULL
    setting_name            TEXT NOT NULL
    old_value               TEXT
    new_value               TEXT
    changed_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    changed_by              TEXT DEFAULT 'user'                     -- options include "user", "admin", "system"
)

CREATE TABLE mmr_ratings_1v1 (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT
    discord_uid             INTEGER
    player_name             TEXT NOT NULL
    last_chosen_vetoes      TEXT
    bw_terran_mmr           INT
    bw_terran_last_played   TIMESTAMP
    bw_zerg_mmr             INT
    bw_zerg_last_played     TIMESTAMP
    bw_protoss_mmr          INT
    bw_protoss_last_played  TIMESTAMP
    sc2_terran_mmr          INT
    sc2_terran_last_played  TIMESTAMP
    sc2_zerg_mmr            INT
    sc2_zerg_last_played    TIMESTAMP
    sc2_protoss_mmr         INT
    sc2_protoss_last_played TIMESTAMP
);

CREATE TABLE mmr_ratings_2v2 (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT
    discord_uid             INTEGER
    player_name             TEXT NOT NULL
    last_chosen_vetoes      TEXT
    bw_terran_mmr           INT
    bw_terran_last_played   TIMESTAMP
    bw_zerg_mmr             INT
    bw_zerg_last_played     TIMESTAMP
    bw_protoss_mmr          INT
    bw_protoss_last_played  TIMESTAMP
    sc2_terran_mmr          INT
    sc2_terran_last_played  TIMESTAMP
    sc2_zerg_mmr            INT
    sc2_zerg_last_played    TIMESTAMP
    sc2_protoss_mmr         INT
    sc2_protoss_last_played TIMESTAMP
);

/*
MMR tables for additional game modes (e.g., 3v3, FFA) will follow this same structure.

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
```