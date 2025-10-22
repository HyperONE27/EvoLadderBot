```sql
-- =============================================
-- CORE TABLES (SQLite-compatible with PostgreSQL benefits)
-- =============================================

CREATE TABLE players (
    id                      SERIAL PRIMARY KEY,
    discord_uid             BIGINT NOT NULL UNIQUE,
    discord_username        TEXT NOT NULL,
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
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    remaining_aborts        INTEGER DEFAULT 3
);

CREATE TABLE player_action_logs (
    id                      SERIAL PRIMARY KEY,
    discord_uid             BIGINT NOT NULL,
    player_name             TEXT NOT NULL,
    setting_name            TEXT NOT NULL,
    old_value               TEXT,
    new_value               TEXT,
    changed_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changed_by              TEXT DEFAULT 'player' NOT NULL,
    FOREIGN KEY (discord_uid) REFERENCES players(discord_uid)
);

CREATE TABLE command_calls (
    id                      SERIAL PRIMARY KEY,
    discord_uid             BIGINT NOT NULL,
    player_name             TEXT NOT NULL,
    command                 TEXT NOT NULL,
    called_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (discord_uid) REFERENCES players(discord_uid)
);

CREATE TABLE replays (
    id                      SERIAL PRIMARY KEY,
    replay_path             TEXT NOT NULL UNIQUE,
    replay_hash             TEXT NOT NULL,
    replay_date             TIMESTAMP NOT NULL,
    player_1_name           TEXT NOT NULL,
    player_2_name           TEXT NOT NULL,
    player_1_race           TEXT NOT NULL,
    player_2_race           TEXT NOT NULL,
    result                  INTEGER NOT NULL,
    player_1_handle         TEXT NOT NULL,
    observers               TEXT NOT NULL,
    map_name                TEXT NOT NULL,
    duration                INTEGER NOT NULL,
    uploaded_at             TIMESTAMP NOT NULL
);

CREATE TABLE mmrs_1v1 (
    id                      SERIAL PRIMARY KEY,
    discord_uid             BIGINT NOT NULL,
    player_name             TEXT NOT NULL,
    race                    TEXT NOT NULL,
    mmr                     INTEGER NOT NULL,
    games_played            INTEGER DEFAULT 0,
    games_won               INTEGER DEFAULT 0,
    games_lost              INTEGER DEFAULT 0,
    games_drawn             INTEGER DEFAULT 0,
    last_played             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (discord_uid) REFERENCES players(discord_uid),
    UNIQUE(discord_uid, race)
);

CREATE TABLE matches_1v1 (
    id                      SERIAL PRIMARY KEY,
    player_1_discord_uid    BIGINT NOT NULL,
    player_2_discord_uid    BIGINT NOT NULL,
    player_1_race           TEXT NOT NULL,
    player_2_race           TEXT NOT NULL,
    player_1_mmr            INTEGER NOT NULL,
    player_2_mmr            INTEGER NOT NULL,
    player_1_report         INTEGER,
    player_2_report         INTEGER,
    match_result            INTEGER,
    mmr_change              INTEGER,
    map_played              TEXT NOT NULL,
    server_used             TEXT NOT NULL,
    played_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    player_1_replay_path    TEXT,
    player_1_replay_time    TIMESTAMP,
    player_2_replay_path    TEXT,
    player_2_replay_time    TIMESTAMP,
    FOREIGN KEY (player_1_discord_uid) REFERENCES players(discord_uid),
    FOREIGN KEY (player_2_discord_uid) REFERENCES players(discord_uid)
);

CREATE TABLE preferences_1v1 (
    id                      SERIAL PRIMARY KEY,
    discord_uid             BIGINT NOT NULL UNIQUE,
    last_chosen_races       TEXT,
    last_chosen_vetoes      TEXT,
    FOREIGN KEY (discord_uid) REFERENCES players(discord_uid)
);

-- =============================================
-- "SET IT AND FORGET IT" ANALYTICS FEATURES
-- =============================================

-- These indexes make common queries fast automatically
-- No maintenance required - PostgreSQL handles everything

-- Player lookups (most common operation)
CREATE INDEX idx_players_discord_uid ON players(discord_uid);
CREATE INDEX idx_players_username ON players(discord_username);

-- MMR queries (leaderboards, player stats)
CREATE INDEX idx_mmrs_1v1_discord_uid ON mmrs_1v1(discord_uid);
CREATE INDEX idx_mmrs_1v1_mmr ON mmrs_1v1(mmr);
CREATE INDEX idx_mmrs_mmr_lastplayed_id_desc ON mmrs_1v1 (mmr DESC, last_played DESC, id DESC);

-- Match history (player profiles, recent matches)
CREATE INDEX idx_matches_1v1_player1 ON matches_1v1(player_1_discord_uid);
CREATE INDEX idx_matches_1v1_player2 ON matches_1v1(player_2_discord_uid);
CREATE INDEX idx_matches_1v1_played_at ON matches_1v1(played_at);

-- Replay lookups (duplicate detection, file management)
CREATE INDEX idx_replays_hash ON replays(replay_hash);
CREATE INDEX idx_replays_date ON replays(replay_date);

-- Command analytics (usage patterns, debugging)
CREATE INDEX idx_command_calls_discord_uid ON command_calls(discord_uid);
CREATE INDEX idx_command_calls_called_at ON command_calls(called_at);
CREATE INDEX idx_command_calls_command ON command_calls(command);
```