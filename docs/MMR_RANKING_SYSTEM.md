# MMR Ranking System Implementation

## Overview

This document describes the implementation of the MMR-based ranking system for the EvoLadderBot. The ranking system assigns percentile-based ranks (S, A, B, C, D, E, F, U) to all player-race combinations based on their MMR.

## Rank Distribution

The ranking system uses the following percentile distribution:

| Rank | Percentile | Description |
|------|------------|-------------|
| S    | Top 1%     | Elite players |
| A    | 1-8%       | Advanced players (7%) |
| B    | 8-29%      | Above average (21%) |
| C    | 29-50%     | Average (21%) |
| D    | 50-71%     | Below average (21%) |
| E    | 71-92%     | Developing (21%) |
| F    | 92-100%    | Beginner (8%) |
| U    | N/A        | Unranked (no data) |

## Key Features

### Player-Race Combinations
Each player-race combination is treated as a separate entry for ranking purposes. For example:
- A player who plays Terran and Zerg will have two separate rankings
- Their Terran might be A-Rank while their Zerg is D-Rank
- Both entries appear on the leaderboard with their respective rank emotes

### In-Memory Storage
Rankings are calculated and stored in memory rather than in the database because:
- Rankings change every time the leaderboard is refreshed
- Memory storage provides fast access for leaderboard display
- No need for persistent storage since ranks are recalculated on cache refresh

### Automatic Refresh
Rankings are automatically refreshed whenever the leaderboard cache is refreshed (every 60 seconds). The refresh process:
1. Loads all player-race combinations from `mmrs_1v1` table
2. Sorts by MMR DESC, id DESC
3. Calculates percentile for each entry
4. Assigns rank based on percentile thresholds
5. Stores in memory for fast lookup

## Architecture

### Service Locator Pattern
The ranking system uses the service locator singleton pattern:
- Single `RankingService` instance created in `app_context.py`
- All components access the same instance
- Ensures consistent ranking data across the application

### Performance Optimizations
The leaderboard service uses optimized filtering and sorting:
- Multi-threaded operations for large datasets
- Efficient grouping operations for "Best Race Only" mode
- Zero-copy slicing for pagination
- Optimized for 5,000+ player datasets

### Integration Points

#### 1. RankingService (`src/backend/services/ranking_service.py`)
Core service that manages rank calculation and storage:
```python
from src.backend.services.app_context import ranking_service

# Refresh rankings (called automatically on cache refresh)
ranking_service.refresh_rankings()

# Get rank for a player-race combination
rank = ranking_service.get_rank(discord_uid, race)
```

#### 2. LeaderboardService (`src/backend/services/leaderboard_service.py`)
Integrates ranking into leaderboard data:
- Calls `refresh_rankings()` when cache is refreshed
- Adds rank information to each player entry
- Passes rank data to frontend for display

#### 3. LeaderboardCommand (`src/bot/commands/leaderboard_command.py`)
Displays rank emotes in the leaderboard:
```
- 1. {rank_emote} {race_emote} {flag_emote} {player_name} {mmr}
```

#### 4. Discord Utils (`src/bot/utils/discord_utils.py`)
Provides `get_rank_emote()` helper to fetch rank emotes from `emotes.json`

## Database Query

The ranking system uses a simple SQL query to load all MMR data:
```sql
SELECT discord_uid, race, mmr, id
FROM mmrs_1v1
ORDER BY mmr DESC, id DESC
```

This ensures:
- All player-race combinations are included
- Proper sorting for percentile calculation
- Consistent ordering with id as tiebreaker

## Display Format

Leaderboard entries now display with rank emotes:
```
- 1. 🏆 👨‍🚀 🇺🇸 Player1     1500
- 2. 💎 🐛 🇰🇷 Player2     1450
- 3. 🥇 🤖 🇯🇵 Player3     1400
```

Where:
- First emote is the rank (S/A/B/C/D/E/F/U)
- Second emote is the race
- Third emote is the country flag
- Player name is left-padded to 12 characters
- MMR is displayed as an integer

## Testing

To verify the ranking system is working:
1. Check leaderboard display includes rank emotes
2. Verify top 1% of players have S-Rank emote
3. Confirm each player-race combo has independent rank
4. Test that "Best Race Only" filter still works correctly

## Future Enhancements

Potential improvements:
- Add rank history tracking
- Display rank changes over time
- Implement rank-based matchmaking
- Add rank rewards/achievements
- Create rank distribution statistics page

