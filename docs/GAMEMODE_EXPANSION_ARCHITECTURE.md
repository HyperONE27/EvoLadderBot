# Game Mode Expansion: Architecture Analysis

## Executive Summary

This document provides a comprehensive analysis of expanding EvoLadderBot to support additional game modes beyond standard 1v1, including:

1. **Alternative 1v1 modes** (e.g., best-of-3, ban-pick, mirror-only) - Same flow direction and shape, different logic
2. **2v2 team modes** - Parallel flows but different shape (methods need more parameters or compressed data structures)
3. **FFA (Free-For-All) modes** - Completely different shape handling 8 single-player "teams"

Each mode presents different architectural challenges and requires different levels of database and code refactoring.

---

## Current Architecture Analysis

### Database Schema (1v1 Focus)

```sql
-- Current schema is deeply coupled to 1v1 structure
CREATE TABLE matches_1v1 (
    id                      SERIAL PRIMARY KEY,
    player_1_discord_uid    BIGINT NOT NULL,      -- Hard-coded to 2 players
    player_2_discord_uid    BIGINT NOT NULL,
    player_1_race           TEXT NOT NULL,         -- Individual race per player
    player_2_race           TEXT NOT NULL,
    player_1_mmr            INTEGER NOT NULL,      -- Individual MMR snapshot
    player_2_mmr            INTEGER NOT NULL,
    player_1_report         INTEGER,               -- Individual report
    player_2_report         INTEGER,
    match_result            INTEGER,               -- 0=draw, 1=p1 win, 2=p2 win, -1=abort, -2=conflict
    mmr_change              INTEGER,               -- Single scalar MMR change
    map_played              TEXT NOT NULL,
    server_used             TEXT NOT NULL,
    played_at               TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    player_1_replay_path    TEXT,                  -- Individual replay paths
    player_1_replay_time    TIMESTAMPTZ,
    player_2_replay_path    TEXT,
    player_2_replay_time    TIMESTAMPTZ,
    FOREIGN KEY (player_1_discord_uid) REFERENCES players(discord_uid),
    FOREIGN KEY (player_2_discord_uid) REFERENCES players(discord_uid)
);

CREATE TABLE mmrs_1v1 (
    id                      SERIAL PRIMARY KEY,
    discord_uid             BIGINT NOT NULL,
    player_name             TEXT NOT NULL,
    race                    TEXT NOT NULL,         -- Individual race MMR tracking
    mmr                     INTEGER NOT NULL,
    games_played            INTEGER DEFAULT 0,
    games_won               INTEGER DEFAULT 0,
    games_lost              INTEGER DEFAULT 0,
    games_drawn             INTEGER DEFAULT 0,
    last_played             TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (discord_uid) REFERENCES players(discord_uid),
    UNIQUE(discord_uid, race)                      -- One MMR per player per race
);
```

**Key Observations:**
- Schema is tightly coupled to exactly 2 players
- MMR tracking assumes individual player-race combinations
- Match results use simple numeric codes (0, 1, 2)
- Replay validation assumes 2-player replays
- No concept of teams, team composition, or multi-participant matches

### Core Service Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Current Flow (1v1)                        │
├─────────────────────────────────────────────────────────────┤
│  Matchmaker → Create Match (2 params) → Store in DB         │
│       ↓                                                       │
│  MatchResult (2 player fields)                               │
│       ↓                                                       │
│  MMRService.calculate_new_mmr(mmr1, mmr2, result)           │
│       ↓                                                       │
│  DataAccessService.update_player_mmr(uid, race, new_mmr)    │
│       ↓                                                       │
│  ReplayService.parse_replay (expects 2 players)              │
│       ↓                                                       │
│  MatchCompletionService.verify_replay (2 races, 2 reports)  │
└─────────────────────────────────────────────────────────────┘
```

**Core Type Definitions:**

```python
@dataclass
class MatchResult:
    match_id: int
    player_1_discord_id: int
    player_2_discord_id: int
    player_1_user_id: str
    player_2_user_id: str
    player_1_race: str
    player_2_race: str
    map_choice: str
    server_choice: str
    in_game_channel: str
    player_1_rank: Optional[str]
    player_2_rank: Optional[str]
```

---

## Option 1: Alternative 1v1 Modes

### Description
Alternative 1v1 modes maintain the **same architectural shape** as standard 1v1 but with different **logic and rules**. Examples:

- **Best-of-3/Best-of-5**: Multiple games, aggregate scoring
- **Ban-Pick**: Modified map/race selection process
- **Mirror-Only**: Both players must play same race
- **Ranked vs Unranked**: Different MMR pools or no MMR tracking
- **Arcade Modes**: Custom rules (e.g., no zerglings, worker rush only)

### Architectural Impact: **LOW** ⭐

### Database Changes: **MINIMAL**

**Strategy A: Add `game_mode` discriminator column**

```sql
-- Extend matches_1v1 table
ALTER TABLE matches_1v1 ADD COLUMN game_mode TEXT DEFAULT 'standard';
ALTER TABLE mmrs_1v1 ADD COLUMN game_mode TEXT DEFAULT 'standard';

-- Examples:
-- game_mode = 'standard', 'best_of_3', 'mirror_only', 'unranked', 'arcade_mode'

-- For best-of-3, you could either:
-- Option A: Store 3 separate match records with a shared `series_id`
ALTER TABLE matches_1v1 ADD COLUMN series_id INTEGER;

-- Option B: Store single match with JSON blob for sub-games
ALTER TABLE matches_1v1 ADD COLUMN series_data JSONB;
```

**Strategy B: Mode-specific MMR pools**

```sql
-- Current: mmrs_1v1 has UNIQUE(discord_uid, race)
-- Future: Add game_mode to the unique constraint

ALTER TABLE mmrs_1v1 DROP CONSTRAINT mmrs_1v1_discord_uid_race_key;
ALTER TABLE mmrs_1v1 ADD CONSTRAINT mmrs_1v1_discord_uid_race_mode_key 
    UNIQUE(discord_uid, race, game_mode);
```

### Code Changes: **CONFIGURATION-DRIVEN**

Most alternative 1v1 modes can be implemented through **configuration objects** rather than architectural changes:

```python
@dataclass
class GameModeConfig:
    mode_id: str  # 'standard', 'best_of_3', 'mirror_only', etc.
    display_name: str
    description: str
    
    # Matchmaking rules
    require_mirror_race: bool = False
    allow_cross_region: bool = True
    
    # Scoring rules
    is_series: bool = False
    games_in_series: int = 1
    
    # MMR rules
    tracks_mmr: bool = True
    separate_mmr_pool: bool = False
    mmr_multiplier: float = 1.0
    
    # Replay validation
    replay_required: bool = True
    custom_validation_rules: Optional[Dict[str, Any]] = None

# Usage
GAME_MODES = {
    'standard': GameModeConfig('standard', 'Standard 1v1', '...'),
    'best_of_3': GameModeConfig('best_of_3', 'Best of 3', '...', is_series=True, games_in_series=3),
    'mirror_only': GameModeConfig('mirror_only', 'Mirror Match', '...', require_mirror_race=True),
    'unranked': GameModeConfig('unranked', 'Unranked', '...', tracks_mmr=False),
}
```

### Service Changes

```python
class MatchmakingService:
    def attempt_match(self, game_mode: str = 'standard'):
        """Existing method with game_mode parameter"""
        config = GAME_MODES[game_mode]
        
        # Same matching logic, but apply config-driven filters
        if config.require_mirror_race:
            # Filter out non-matching races before pairing
            pass
        
        # Same database write, but pass game_mode
        match_id = await data_service.create_match({
            **existing_fields,
            'game_mode': game_mode
        })

class MMRService:
    def calculate_new_mmr(self, p1_mmr, p2_mmr, result, game_mode='standard'):
        """Existing method with optional game_mode parameter"""
        config = GAME_MODES[game_mode]
        
        # Standard calculation
        outcome = self._base_calculation(p1_mmr, p2_mmr, result)
        
        # Apply mode-specific multiplier
        if config.mmr_multiplier != 1.0:
            outcome = self._apply_multiplier(outcome, config.mmr_multiplier)
        
        return outcome
```

### Replay Validation

For most alt-1v1 modes, replay validation is **unchanged**. For series (best-of-3), you'd validate multiple replays:

```python
class ReplayService:
    async def validate_series_replays(
        self,
        match_id: int,
        replay_list: List[bytes],
        game_mode: str
    ) -> bool:
        """Validate all replays in a series"""
        config = GAME_MODES[game_mode]
        
        if not config.is_series:
            # Single replay validation (existing path)
            return await self.validate_single_replay(match_id, replay_list[0])
        
        # Validate series
        if len(replay_list) != config.games_in_series:
            return False
        
        for replay_bytes in replay_list:
            # Same validation logic, different loop count
            if not await self.validate_single_replay(match_id, replay_bytes):
                return False
        
        return True
```

### Migration Path

1. **Phase 1**: Add `game_mode` column to tables (default='standard')
2. **Phase 2**: Create `GameModeConfig` and load first alt-mode (e.g., unranked)
3. **Phase 3**: Add UI for selecting game mode in queue command
4. **Phase 4**: Extend leaderboard service to filter by game mode
5. **Phase 5**: Add mode-specific stats and analytics

**Estimated Effort:** 2-4 weeks for first alt-mode, 1 week per additional mode

---

## Option 2: 2v2 Team Modes

### Description
2v2 introduces **teams** as a fundamental unit. The flow is **parallel** to 1v1 but requires a **different shape**:

- 2 teams instead of 2 players
- Each team has 2 members
- Team MMR calculation (aggregate or independent)
- Team race composition
- 4 replay uploads (one per player)
- 4 match reports to reconcile

### Architectural Impact: **HIGH** ⭐⭐⭐

### Database Changes: **MAJOR REFACTORING**

**Strategy A: Denormalized approach (extend existing schema)**

```sql
-- Extend matches_1v1 → rename to matches
ALTER TABLE matches_1v1 RENAME TO matches;

-- Add team fields
ALTER TABLE matches ADD COLUMN game_type TEXT DEFAULT '1v1';  -- '1v1', '2v2'

-- For 2v2, add player 3 and 4
ALTER TABLE matches ADD COLUMN player_3_discord_uid BIGINT;
ALTER TABLE matches ADD COLUMN player_4_discord_uid BIGINT;
ALTER TABLE matches ADD COLUMN player_3_race TEXT;
ALTER TABLE matches ADD COLUMN player_4_race TEXT;
ALTER TABLE matches ADD COLUMN player_3_mmr INTEGER;
ALTER TABLE matches ADD COLUMN player_4_mmr INTEGER;
ALTER TABLE matches ADD COLUMN player_3_report INTEGER;
ALTER TABLE matches ADD COLUMN player_4_report INTEGER;
ALTER TABLE matches ADD COLUMN player_3_replay_path TEXT;
ALTER TABLE matches ADD COLUMN player_3_replay_time TIMESTAMPTZ;
ALTER TABLE matches ADD COLUMN player_4_replay_path TEXT;
ALTER TABLE matches ADD COLUMN player_4_replay_time TIMESTAMPTZ;

-- Team result: 1 = team1 wins (p1+p2), 2 = team2 wins (p3+p4)
-- match_result INTEGER already exists

-- Add team MMR tracking
ALTER TABLE matches ADD COLUMN team_1_mmr INTEGER;  -- Aggregate team MMR
ALTER TABLE matches ADD COLUMN team_2_mmr INTEGER;
ALTER TABLE matches ADD COLUMN team_mmr_change INTEGER;

-- For 1v1, player_3/4 fields are NULL
-- For 2v2, all 4 player fields are populated
```

**Pros:**
- Minimal table restructuring
- Can query both 1v1 and 2v2 from same table
- No foreign key complications

**Cons:**
- Lots of NULL columns for 1v1 matches
- Hard to extend to 3v3 or FFA later
- Code has to handle nullable fields everywhere
- Index fragmentation

**Strategy B: Normalized approach (new tables)**

```sql
-- Create teams table
CREATE TABLE teams (
    id                  SERIAL PRIMARY KEY,
    team_name           TEXT,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Create team_members junction table
CREATE TABLE team_members (
    id                  SERIAL PRIMARY KEY,
    team_id             INTEGER NOT NULL,
    discord_uid         BIGINT NOT NULL,
    race                TEXT NOT NULL,
    joined_at           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES teams(id),
    FOREIGN KEY (discord_uid) REFERENCES players(discord_uid)
);

-- Create new matches table (mode-agnostic)
CREATE TABLE matches (
    id                  SERIAL PRIMARY KEY,
    game_type           TEXT NOT NULL,  -- '1v1', '2v2', 'ffa'
    game_mode           TEXT DEFAULT 'standard',
    map_played          TEXT NOT NULL,
    server_used         TEXT NOT NULL,
    match_result        INTEGER,
    played_at           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Create match_participants table
CREATE TABLE match_participants (
    id                  SERIAL PRIMARY KEY,
    match_id            INTEGER NOT NULL,
    discord_uid         BIGINT NOT NULL,
    team_number         INTEGER NOT NULL,  -- 1, 2, 3, ... (for FFA: each player is a team)
    race                TEXT NOT NULL,
    mmr_at_start        INTEGER NOT NULL,
    mmr_change          INTEGER,
    report_value        INTEGER,
    replay_path         TEXT,
    replay_time         TIMESTAMPTZ,
    FOREIGN KEY (match_id) REFERENCES matches(id),
    FOREIGN KEY (discord_uid) REFERENCES players(discord_uid)
);

-- Team MMR tracking
CREATE TABLE mmrs_teams (
    id                  SERIAL PRIMARY KEY,
    team_id             INTEGER NOT NULL,
    game_type           TEXT NOT NULL,  -- '2v2', '3v3', etc.
    mmr                 INTEGER NOT NULL,
    games_played        INTEGER DEFAULT 0,
    games_won           INTEGER DEFAULT 0,
    games_lost          INTEGER DEFAULT 0,
    last_played         TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES teams(id),
    UNIQUE(team_id, game_type)
);
```

**Pros:**
- Clean, extensible design
- No NULL pollution
- Naturally extends to 3v3, 4v4, FFA
- Proper normalization

**Cons:**
- Requires significant refactoring of existing code
- More JOINs for queries
- Must migrate all existing 1v1 data
- Backward compatibility complexity

### Code Changes: **MAJOR REFACTORING**

#### Approach 2A: Extend existing signatures (denormalized)

```python
# Current (1v1)
def create_match_1v1(
    player_1_discord_uid: int,
    player_2_discord_uid: int,
    player_1_race: str,
    player_2_race: str,
    player_1_mmr: int,
    player_2_mmr: int,
    map_played: str,
    server_used: str,
    mmr_change: int
) -> int:
    # Insert into matches table
    pass

# Future (2v2) - Denormalized approach
def create_match(
    game_type: str,  # '1v1' or '2v2'
    player_1_discord_uid: int,
    player_2_discord_uid: int,
    player_1_race: str,
    player_2_race: str,
    player_1_mmr: int,
    player_2_mmr: int,
    map_played: str,
    server_used: str,
    mmr_change: int,
    # Optional 2v2 fields
    player_3_discord_uid: Optional[int] = None,
    player_4_discord_uid: Optional[int] = None,
    player_3_race: Optional[str] = None,
    player_4_race: Optional[str] = None,
    player_3_mmr: Optional[int] = None,
    player_4_mmr: Optional[int] = None,
    team_1_mmr: Optional[int] = None,
    team_2_mmr: Optional[int] = None,
    team_mmr_change: Optional[int] = None
) -> int:
    # Massive if-else branching based on game_type
    if game_type == '1v1':
        # Insert only 1v1 fields
        pass
    elif game_type == '2v2':
        # Insert all fields
        pass
```

**Problems:**
- Function signature explosion
- Lots of Optional types everywhere
- Branching logic in every method
- Hard to maintain

#### Approach 2B: Compressed data structures (denormalized)

```python
from typing import List, Dict

# Compress player data into arrays/dicts
def create_match(
    game_type: str,
    teams: List[List[Dict[str, Any]]],  # [[team1_p1, team1_p2], [team2_p1, team2_p2]]
    map_played: str,
    server_used: str,
    mmr_changes: List[int]  # [team1_change, team2_change]
) -> int:
    """
    teams structure:
    [
        [  # Team 1
            {'discord_uid': 123, 'race': 'bw_terran', 'mmr': 1500},
            {'discord_uid': 456, 'race': 'sc2_zerg', 'mmr': 1600}
        ],
        [  # Team 2
            {'discord_uid': 789, 'race': 'bw_protoss', 'mmr': 1550},
            {'discord_uid': 101, 'race': 'sc2_terran', 'mmr': 1450}
        ]
    ]
    """
    if game_type == '1v1':
        # Extract single players from teams
        p1 = teams[0][0]
        p2 = teams[1][0]
        # Write to player_1/player_2 columns
        pass
    elif game_type == '2v2':
        # Extract all 4 players
        p1, p2 = teams[0][0], teams[0][1]
        p3, p4 = teams[1][0], teams[1][1]
        # Write to all 4 player columns
        pass
```

**Better, but still messy:**
- Cleaner signatures
- Still requires denormalized table with NULLs
- Still has branching logic in implementation

#### Approach 2C: Normalized table architecture (recommended)

```python
@dataclass
class MatchParticipant:
    discord_uid: int
    team_number: int
    race: str
    mmr_at_start: int
    mmr_change: Optional[int] = None
    report_value: Optional[int] = None
    replay_path: Optional[str] = None

def create_match(
    game_type: str,
    game_mode: str,
    participants: List[MatchParticipant],
    map_played: str,
    server_used: str
) -> int:
    """
    participants = [
        MatchParticipant(discord_uid=123, team_number=1, race='bw_terran', mmr_at_start=1500),
        MatchParticipant(discord_uid=456, team_number=1, race='sc2_zerg', mmr_at_start=1600),
        MatchParticipant(discord_uid=789, team_number=2, race='bw_protoss', mmr_at_start=1550),
        MatchParticipant(discord_uid=101, team_number=2, race='sc2_terran', mmr_at_start=1450),
    ]
    """
    # Insert into matches table
    match_id = self._insert_match(game_type, game_mode, map_played, server_used)
    
    # Insert all participants
    for participant in participants:
        self._insert_participant(match_id, participant)
    
    return match_id
```

**Advantages:**
- No branching logic
- Same code path for 1v1, 2v2, FFA
- Type-safe
- Extensible

### MMR Service Changes

```python
class MMRService:
    # Current (1v1)
    def calculate_new_mmr(
        self,
        player_one_mmr: int,
        player_two_mmr: int,
        result: int
    ) -> MatchMMROutcome:
        # Standard Elo calculation
        pass
    
    # Future (2v2)
    def calculate_team_mmr_changes(
        self,
        team1_mmrs: List[int],
        team2_mmrs: List[int],
        result: int,
        mmr_distribution: str = 'average'  # 'average', 'weighted', 'independent'
    ) -> List[int]:
        """
        Calculate MMR changes for team-based matches.
        
        Args:
            team1_mmrs: List of MMRs for team 1 players
            team2_mmrs: List of MMRs for team 2 players
            result: 1 = team1 wins, 2 = team2 wins, 0 = draw
            mmr_distribution: How to distribute MMR
                - 'average': Use average team MMR for Elo calculation
                - 'weighted': Weight by individual contributions (requires performance data)
                - 'independent': Each player gains/loses same amount
        
        Returns:
            List of MMR changes for [team1_p1, team1_p2, team2_p1, team2_p2]
        """
        if mmr_distribution == 'average':
            # Calculate average MMR for each team
            avg_team1 = sum(team1_mmrs) / len(team1_mmrs)
            avg_team2 = sum(team2_mmrs) / len(team2_mmrs)
            
            # Use standard Elo on team averages
            outcome = self.calculate_new_mmr(avg_team1, avg_team2, result)
            
            # Distribute change equally to all team members
            team1_change = (outcome.player_one_mmr - avg_team1)
            team2_change = (outcome.player_two_mmr - avg_team2)
            
            return [team1_change] * len(team1_mmrs) + [team2_change] * len(team2_mmrs)
        
        elif mmr_distribution == 'independent':
            # Each player's MMR changes independently based on opponents
            # More complex, requires pairwise calculations
            pass
```

### Replay Parsing Changes

```python
# Current: Expects exactly 2 players
def parse_replay_data_blocking(replay_bytes: bytes) -> dict:
    replay = sc2reader.load_replay(io.BytesIO(replay_bytes), load_level=4)
    
    if len(replay.players) != 2:
        return {"error": f"Expected 2 players, but replay has {len(replay.players)} players"}
    
    # Extract player1 and player2
    pass

# Future: Support 2v2 (4 players)
def parse_replay_data_blocking(replay_bytes: bytes, game_type: str = '1v1') -> dict:
    replay = sc2reader.load_replay(io.BytesIO(replay_bytes), load_level=4)
    
    expected_players = {
        '1v1': 2,
        '2v2': 4,
        'ffa': 8
    }
    
    if len(replay.players) != expected_players[game_type]:
        return {"error": f"Expected {expected_players[game_type]} players, but replay has {len(replay.players)} players"}
    
    # Extract all players
    players_data = []
    for player in replay.players:
        players_data.append({
            'name': player.name,
            'race': fix_race(player.play_race),
            'team': player.team,  # sc2reader provides team number
            'handle': player.toon_handle,
            'result': player.result  # 'Win', 'Loss', 'Tie'
        })
    
    # Determine team winner
    team_results = {}
    for player in players_data:
        team = player['team']
        if player['result'] == 'Win':
            team_results[team] = 'Win'
    
    winning_team = None
    for team, result in team_results.items():
        if result == 'Win':
            winning_team = team
            break
    
    return {
        'game_type': game_type,
        'players': players_data,
        'winning_team': winning_team,
        # ... other replay data
    }
```

### Match Completion Changes

```python
class MatchCompletionService:
    async def check_match_completion(self, match_id: int):
        """Modified to handle multiple participants"""
        match_data = self.data_service.get_match(match_id)
        
        if match_data['game_type'] == '1v1':
            # Existing logic: check 2 reports
            p1_report = match_data.get('player_1_report')
            p2_report = match_data.get('player_2_report')
            
            if p1_report and p2_report:
                await self._finalize_match(match_id)
        
        elif match_data['game_type'] == '2v2':
            # New logic: check 4 reports
            participants = self.data_service.get_match_participants(match_id)
            
            # All 4 players must report
            reports = [p.get('report_value') for p in participants]
            
            if all(r is not None for r in reports):
                # Check for team consensus
                team1_reports = [reports[0], reports[1]]
                team2_reports = [reports[2], reports[3]]
                
                # If all 4 agree, finalize
                if len(set(reports)) == 1:
                    await self._finalize_match(match_id)
                
                # If team members disagree, mark conflict
                elif team1_reports[0] != team1_reports[1] or team2_reports[0] != team2_reports[1]:
                    await self._mark_conflict(match_id)
```

### Migration Path

1. **Phase 1**: Design decision (denormalized vs normalized)
2. **Phase 2**: Create new tables or extend existing
3. **Phase 3**: Migrate all existing 1v1 data to new schema
4. **Phase 4**: Refactor `create_match` to use new structure
5. **Phase 5**: Refactor MMR service for team calculations
6. **Phase 6**: Update replay parsing for 4-player replays
7. **Phase 7**: Update UI/embeds to show 4 players
8. **Phase 8**: Update match completion logic for 4 reports
9. **Phase 9**: Add team matchmaking (pairing 2-player parties)
10. **Phase 10**: Testing and rollout

**Estimated Effort:** 3-6 months (normalized approach), 2-3 months (denormalized approach)

**Recommendation:** Use **normalized approach (Strategy B)** for long-term extensibility, even though it requires more upfront work.

---

## Option 3: FFA (Free-For-All) Mode

### Description
FFA mode has **8 individual players** competing in a single match. Each player is effectively a "team of 1". This requires:

- 8-player matchmaking
- 8 different MMR updates (multi-way Elo)
- 8 replay uploads
- 8 match reports
- Placement-based scoring (1st, 2nd, ..., 8th)
- Completely different shape from 1v1

### Architectural Impact: **VERY HIGH** ⭐⭐⭐⭐⭐

### Database Changes: **REQUIRES NORMALIZED SCHEMA**

FFA is **only feasible** with the normalized approach from Option 2B. The denormalized approach would require:

```sql
ALTER TABLE matches ADD COLUMN player_5_discord_uid BIGINT;
ALTER TABLE matches ADD COLUMN player_6_discord_uid BIGINT;
ALTER TABLE matches ADD COLUMN player_7_discord_uid BIGINT;
ALTER TABLE matches ADD COLUMN player_8_discord_uid BIGINT;
-- ... 32 more columns for races, mmrs, reports, replays, etc.
```

This is **not viable**. You **must** use the normalized `match_participants` approach:

```sql
-- With normalized schema, FFA "just works"
INSERT INTO matches (game_type, game_mode, map_played, server_used)
VALUES ('ffa', 'standard', 'Lost Temple', 'US-West');

-- Insert 8 participants
INSERT INTO match_participants (match_id, discord_uid, team_number, race, mmr_at_start)
VALUES
    (1, 123, 1, 'bw_terran', 1500),
    (1, 456, 2, 'bw_zerg', 1520),
    (1, 789, 3, 'bw_protoss', 1480),
    (1, 101, 4, 'sc2_terran', 1550),
    (1, 102, 5, 'sc2_zerg', 1490),
    (1, 103, 6, 'sc2_protoss', 1510),
    (1, 104, 7, 'bw_terran', 1530),
    (1, 105, 8, 'bw_zerg', 1470);
```

### Match Result Representation

For FFA, `match_result` cannot be a simple 0/1/2. You need placement data:

```sql
-- Option 1: Store placement in match_participants
ALTER TABLE match_participants ADD COLUMN placement INTEGER;

-- Option 2: Store placement mapping in matches table as JSON
ALTER TABLE matches ADD COLUMN placements JSONB;
-- Example: {"1": 123, "2": 456, "3": 789, ...} (placement -> discord_uid)
```

### MMR Service Changes: **MULTI-WAY ELO**

Standard Elo is designed for 1v1. For FFA, you need a **multi-competitor rating system**. Common approaches:

#### Approach A: Pairwise Elo (conservative)

```python
def calculate_ffa_mmr_changes(
    self,
    player_mmrs: List[int],
    placements: List[int]  # [1, 2, 3, 4, 5, 6, 7, 8]
) -> List[int]:
    """
    Calculate MMR changes for FFA using pairwise Elo.
    
    For each pair of players, treat it as a 1v1 match based on placement.
    Average the MMR changes from all pairwise comparisons.
    """
    n = len(player_mmrs)
    changes = [0] * n
    
    for i in range(n):
        for j in range(i + 1, n):
            # Player i vs Player j
            # If player i placed higher than player j, they "won"
            if placements[i] < placements[j]:
                result = 1  # i wins
            elif placements[i] > placements[j]:
                result = 2  # j wins
            else:
                result = 0  # tie
            
            # Calculate Elo for this pair
            outcome = self.calculate_new_mmr(player_mmrs[i], player_mmrs[j], result)
            
            # Accumulate changes
            changes[i] += (outcome.player_one_mmr - player_mmrs[i])
            changes[j] += (outcome.player_two_mmr - player_mmrs[j])
    
    # Average changes (each player had n-1 comparisons)
    changes = [change / (n - 1) for change in changes]
    
    # Scale down to prevent inflation (optional)
    changes = [change * 0.5 for change in changes]
    
    return [int(round(c)) for c in changes]
```

#### Approach B: Multi-competitor Elo (advanced)

Use a proper multi-competitor rating system like **TrueSkill**, **Glicko-2**, or **Elo-MMR**. These are more complex but provide better rating accuracy for multi-player scenarios.

```python
# Would require external library
from trueskill import Rating, rate

def calculate_ffa_mmr_changes_trueskill(
    self,
    player_mmrs: List[int],
    placements: List[int]
) -> List[int]:
    """Use TrueSkill for more accurate FFA ratings"""
    # Convert MMRs to TrueSkill ratings
    ratings = [Rating(mu=mmr/10) for mmr in player_mmrs]
    
    # Create ranking groups (lower placement = higher rank)
    ranking = sorted(enumerate(placements), key=lambda x: x[1])
    teams = [[ratings[i]] for i, _ in ranking]
    
    # Calculate new ratings
    new_ratings = rate(teams)
    
    # Convert back to MMR changes
    changes = []
    for i, old_rating in enumerate(ratings):
        new_rating = new_ratings[placements.index(i+1)][0]
        change = (new_rating.mu - old_rating.mu) * 10
        changes.append(int(round(change)))
    
    return changes
```

### Matchmaking Changes

```python
class Matchmaker:
    async def attempt_ffa_match(self):
        """Find 8 players for FFA match"""
        if len(self.players) < 8:
            return None
        
        # Sort by MMR
        sorted_players = sorted(self.players, key=lambda p: p.bw_mmr or p.sc2_mmr)
        
        # Take a window of 8 players with similar MMR
        # Use sliding window to find best MMR grouping
        best_group = None
        min_mmr_spread = float('inf')
        
        for i in range(len(sorted_players) - 7):
            group = sorted_players[i:i+8]
            mmrs = [p.bw_mmr or p.sc2_mmr for p in group]
            spread = max(mmrs) - min(mmrs)
            
            if spread < min_mmr_spread:
                min_mmr_spread = spread
                best_group = group
        
        # Check if spread is acceptable
        if min_mmr_spread > 300:  # Threshold
            return None
        
        # Create FFA match
        participants = [
            MatchParticipant(
                discord_uid=p.discord_user_id,
                team_number=i+1,  # Each player is their own "team"
                race=p.get_race_for_match(is_bw_match),
                mmr_at_start=p.get_effective_mmr(is_bw_match)
            )
            for i, p in enumerate(best_group)
        ]
        
        match_id = await data_service.create_match(
            game_type='ffa',
            game_mode='standard',
            participants=participants,
            map_played=map_choice,
            server_used=server_choice
        )
        
        return match_id
```

### Replay Validation

```python
def parse_replay_data_blocking(replay_bytes: bytes, game_type: str = '1v1') -> dict:
    replay = sc2reader.load_replay(io.BytesIO(replay_bytes), load_level=4)
    
    if game_type == 'ffa':
        if len(replay.players) != 8:
            return {"error": f"Expected 8 players for FFA, found {len(replay.players)}"}
        
        # Extract placements
        placements = {}
        for player in replay.players:
            # sc2reader may not have placement data directly
            # You might need to infer from timestamps or game events
            # This is a limitation of replay parsing
            pass
        
        return {
            'game_type': 'ffa',
            'players': [
                {
                    'name': p.name,
                    'race': fix_race(p.play_race),
                    'placement': infer_placement(p)
                }
                for p in replay.players
            ]
        }
```

**WARNING:** SC2Replay files may not contain explicit placement data for FFA. You might need players to manually report placements.

### Match Completion Changes

```python
async def check_match_completion(self, match_id: int):
    match_data = self.data_service.get_match(match_id)
    
    if match_data['game_type'] == 'ffa':
        participants = self.data_service.get_match_participants(match_id)
        
        # All 8 players must report their placement
        reports = [p.get('report_value') for p in participants]
        
        if all(r is not None for r in reports):
            # Validate: All placements from 1-8 must be used exactly once
            if set(reports) == {1, 2, 3, 4, 5, 6, 7, 8}:
                await self._finalize_ffa_match(match_id)
            else:
                # Conflicting placements, requires admin resolution
                await self._mark_conflict(match_id)
```

### UI Changes

FFA requires **completely different embeds**:

```python
class FFAMatchEmbed:
    def get_embed(self) -> discord.Embed:
        embed = discord.Embed(title="FFA Match Found!")
        
        # Show all 8 players in a compact format
        players_text = "\n".join([
            f"{i+1}. <@{p['discord_uid']}> ({p['race']}) - {p['mmr']} MMR"
            for i, p in enumerate(self.participants)
        ])
        
        embed.add_field(name="Players", value=players_text)
        embed.add_field(name="Map", value=self.map_choice)
        embed.add_field(name="Server", value=self.server_choice)
        
        # Players report placements instead of win/loss
        embed.add_field(
            name="Report Placement",
            value="Use the dropdown to report your final placement (1st-8th)",
            inline=False
        )
        
        return embed

class FFAMatchView(discord.ui.View):
    @discord.ui.select(
        placeholder="Report your placement",
        options=[
            discord.SelectOption(label=f"{i}st/nd/rd/th Place", value=str(i))
            for i in range(1, 9)
        ]
    )
    async def report_placement(self, interaction, select):
        placement = int(select.values[0])
        # Submit placement report
        await self.match_completion_service.report_ffa_placement(
            self.match_id,
            interaction.user.id,
            placement
        )
```

### Migration Path

1. **Phase 1**: Complete normalized schema migration (Option 2)
2. **Phase 2**: Implement multi-way MMR calculation (TrueSkill or pairwise Elo)
3. **Phase 3**: Add placement reporting to match_participants table
4. **Phase 4**: Update replay parsing (if possible)
5. **Phase 5**: Create FFA matchmaking logic (8-player groups)
6. **Phase 6**: Design FFA embeds and UI
7. **Phase 7**: Update match completion for placement validation
8. **Phase 8**: Admin tools for resolving FFA conflicts
9. **Phase 9**: Testing with 8 players
10. **Phase 10**: Rollout

**Estimated Effort:** 6-12 months (requires completing 2v2 first)

**Challenges:**
- Finding 8 players with similar MMR simultaneously
- 8-way conflict resolution is complex
- Replay parsing may not extract placements
- Manual placement reporting is prone to cheating/errors

---

## Recommendations by Priority

### Short-Term (0-6 months)

**Implement Alternative 1v1 Modes First**

Start with:
1. **Unranked 1v1** (easiest, just disable MMR tracking)
2. **Best-of-3** (slightly harder, requires series tracking)
3. **Mirror-Only** (moderate, requires matchmaking filter)

This gives you:
- Immediate feature expansion
- Low architectural risk
- Configuration-driven design patterns
- Testing ground for game mode selection UI

**Estimated Effort:** 1 month for unranked, 2 weeks per additional alt-mode

### Medium-Term (6-12 months)

**Refactor to Normalized Schema for 2v2**

1. Design normalized schema (`matches`, `match_participants`, `teams`)
2. Migrate all existing 1v1 data
3. Refactor core services to use new schema
4. Implement team MMR calculations
5. Build 2v2 matchmaking (party system)
6. Update replay parsing for 4-player matches
7. Build team-based embeds and UI

This gives you:
- Extensible foundation for future modes
- Support for team-based gameplay
- Better data normalization
- Foundation for FFA

**Estimated Effort:** 6-9 months

### Long-Term (12+ months)

**Add FFA Mode**

Only after 2v2 is stable and normalized schema is proven:

1. Implement multi-way Elo or TrueSkill
2. Add placement reporting
3. Build 8-player matchmaking
4. Design FFA UI/embeds
5. Extensive testing

**Estimated Effort:** 6+ months

---

## Schema Comparison: Denormalized vs Normalized

| Aspect | Denormalized (Extend matches_1v1) | Normalized (New Tables) |
|--------|-----------------------------------|-------------------------|
| **1v1 Support** | ✅ Native | ✅ Via match_participants |
| **2v2 Support** | ⚠️ Adds 16+ columns | ✅ Clean, no column explosion |
| **FFA Support** | ❌ Not viable | ✅ Scales naturally |
| **NULL Pollution** | ❌ High (50%+ NULLs) | ✅ None |
| **Query Complexity** | ✅ Simple (single table) | ⚠️ Requires JOINs |
| **Index Efficiency** | ⚠️ Fragmented | ✅ Optimized |
| **Migration Cost** | ✅ Low | ❌ High |
| **Extensibility** | ❌ Poor | ✅ Excellent |
| **Code Complexity** | ⚠️ High branching | ✅ Unified logic |
| **Maintenance** | ❌ Hard | ✅ Easy |

**Verdict:** **Normalized approach is strongly recommended** for any plan to support 2v2 or FFA.

---

## API Design Comparison

### Current (1v1 Only)

```python
# Tightly coupled to 2 players
match_id = db_writer.create_match_1v1(
    player_1_discord_uid=123,
    player_2_discord_uid=456,
    player_1_race='bw_terran',
    player_2_race='sc2_zerg',
    player_1_mmr=1500,
    player_2_mmr=1600,
    map_played='Lost Temple',
    server_used='US-West',
    mmr_change=15
)
```

### Future (Mode-Agnostic)

```python
# Flexible, supports any game type
match_id = db_writer.create_match(
    game_type='2v2',
    game_mode='standard',
    participants=[
        MatchParticipant(discord_uid=123, team_number=1, race='bw_terran', mmr_at_start=1500),
        MatchParticipant(discord_uid=456, team_number=1, race='sc2_zerg', mmr_at_start=1600),
        MatchParticipant(discord_uid=789, team_number=2, race='bw_protoss', mmr_at_start=1550),
        MatchParticipant(discord_uid=101, team_number=2, race='sc2_terran', mmr_at_start=1450),
    ],
    map_played='Lost Temple',
    server_used='US-West'
)
```

---

## Risk Assessment

| Game Mode | Technical Risk | User Experience Risk | Maintenance Burden |
|-----------|----------------|----------------------|--------------------|
| **Alt 1v1 Modes** | 🟢 Low | 🟢 Low | 🟢 Low |
| **2v2 (Denormalized)** | 🟡 Medium | 🟡 Medium | 🔴 High |
| **2v2 (Normalized)** | 🟡 Medium | 🟡 Medium | 🟢 Low |
| **FFA (without normalization)** | 🔴 Impossible | 🔴 High | 🔴 Extreme |
| **FFA (with normalization)** | 🔴 High | 🔴 High | 🟡 Medium |

---

## Conclusion

**Recommended Roadmap:**

1. **Phase 1 (Months 1-2)**: Implement alternative 1v1 modes (unranked, best-of-3)
   - Low risk, high value
   - Tests game mode selection UI
   - Configuration-driven architecture

2. **Phase 2 (Months 3-8)**: Refactor to normalized schema + implement 2v2
   - High upfront cost, but necessary for extensibility
   - Enables future FFA and other modes
   - Cleaner codebase long-term

3. **Phase 3 (Months 9-15)**: Add FFA mode
   - Only viable after normalized schema
   - Requires advanced MMR calculations
   - High complexity, moderate demand

**Key Decision Point:**

If you plan to **only support alternative 1v1 modes**, stick with the current schema and use configuration-driven design.

If you plan to **ever support 2v2 or FFA**, invest in the normalized schema now. The migration cost will only increase over time.

---

## Additional Resources

- [Elo Rating System for Multi-Player Games](https://medium.com/data-science/developing-an-elo-based-data-driven-ranking-system-for-2v2-multiplayer-games-7689f7d42a53)
- [TrueSkill Rating System (Microsoft Research)](https://www.microsoft.com/en-us/research/project/trueskill-ranking-system/)
- [Database Normalization Best Practices](https://en.wikipedia.org/wiki/Database_normalization)
- [sc2reader Documentation](https://sc2reader.readthedocs.io/en/latest/)

