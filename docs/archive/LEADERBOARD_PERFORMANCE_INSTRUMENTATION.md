# Leaderboard Performance Instrumentation

## Overview

The leaderboard command is now fully instrumented with detailed performance tracking to identify bottlenecks. Every step of the process is measured and logged.

## Instrumentation Breakdown

### Main Flow (`leaderboard_command`)

1. **guard_checks_complete** - Player validation and ToS check
2. **create_view_complete** - Creating LeaderboardView instance
3. **fetch_leaderboard_data_complete** - Fetching data from cache/database
4. **update_button_states_complete** - Updating pagination button states
5. **embed_generation_complete** - **Generating the Discord embed (suspect)**
6. **discord_api_call_complete** - **Sending to Discord API (suspect)**

### Embed Generation (`get_embed`)

Inside `embed_generation_complete`, we track:

1. **Data validation** - Checking if data is None
2. **Embed creation** - Creating the discord.Embed object
3. **Get filter info** - Fetching filter information from service
4. **Add filter fields** - Adding race/country filter fields to embed
5. **Format players** - Getting formatted player data from service
6. **Calculate rank width** - Determining padding width for ranks
7. **Generate chunks** - Processing all players (broken down into):
   - **Emote fetching** - Calling `_get_rank_emote()`, `_get_race_emote()`, `_get_flag_emote()` for each player
   - **Text formatting** - String formatting and concatenation
8. **Add fields to embed** - Adding all player fields to the embed object
9. **Add footer** - Adding pagination footer

## Expected Output

When running the bot, you'll see detailed performance logs like:

```
[Embed Perf] Data validation: 0.02ms
[Embed Perf] Embed creation: 0.15ms
[Embed Perf] Get filter info: 0.32ms
[Embed Perf] Add filter fields: 0.08ms
[Embed Perf] Format players: 0.45ms
[Embed Perf] Calculate rank width: 0.03ms
[Embed Perf] Generate chunks - Total: 45.23ms
[Embed Perf]   -> Emote fetching: 38.12ms  <-- LIKELY CULPRIT
[Embed Perf]   -> Text formatting: 7.11ms
[Embed Perf] Add fields to embed: 12.45ms
[Embed Perf] Add footer: 0.23ms
[Embed Perf] TOTAL EMBED GENERATION: 58.96ms

[PERF] leaderboard_command.embed_generation_complete: 59.02ms
[PERF] leaderboard_command.discord_api_call_complete: 325.45ms  <-- LIKELY CULPRIT
```

## What To Look For

### Potential Bottlenecks

1. **Emote Fetching (Most Likely)**
   - If emote fetching is taking 30-100ms, the issue is in `discord_utils.get_*_emote()` functions
   - These functions might be doing repeated imports or expensive lookups
   - **Fix**: Cache emote mappings at module level

2. **Discord API Call (Most Likely)**
   - If `discord_api_call_complete` is taking 300-2000ms, the issue is Discord's API response time
   - This could be due to:
     - Large embed size (many fields, long text)
     - Discord rate limiting
     - Network latency
   - **Fix**: Reduce embed complexity, combine fields, or optimize payload size

3. **Add Fields to Embed**
   - If this is taking 50+ms, Discord's embed.add_field() might be slow
   - **Fix**: Pre-build field list and add all at once if possible

4. **Generate Chunks**
   - If this is taking 100+ms beyond emote fetching, the issue is string concatenation
   - **Fix**: Use list comprehension + join instead of += for strings

## Optimization Strategy

Based on the logs, here's the priority:

### If Emote Fetching is Slow (30-100ms)
```python
# Current (slow - imports on each call):
def _get_rank_emote(self, race_code: str) -> str:
    from src.bot.utils.discord_utils import get_rank_emote
    return get_rank_emote(race_code)

# Optimized (cache at module level):
from src.bot.utils.discord_utils import get_rank_emote, get_race_emote, get_flag_emote

def _get_rank_emote(self, race_code: str) -> str:
    return get_rank_emote(race_code)
```

### If Discord API Call is Slow (300-2000ms)
- **Reduce embed complexity**: Fewer fields, less text per field
- **Simplify emotes**: Use Unicode emojis instead of custom Discord emotes
- **Batch processing**: Pre-render text outside of embed creation
- **Check embed size**: Discord has a 6000 character limit for embeds

### If String Concatenation is Slow (50+ms)
```python
# Current (slow):
field_text = ""
for player in chunk:
    field_text += f"line {i}\n"

# Optimized:
lines = []
for player in chunk:
    lines.append(f"line {i}")
field_text = "\n".join(lines)
```

## Next Steps

1. **Run the bot** and view the `/leaderboard` command
2. **Check the logs** for the detailed breakdown
3. **Identify the bottleneck** - which step is taking the most time?
4. **Apply targeted fixes** based on the specific bottleneck

## Cleanup

Once the bottleneck is identified and fixed, remove the performance logging:
- Remove all `checkpoint_*` variables
- Remove all `print(f"[Embed Perf]...")` statements
- Keep only the high-level `flow.checkpoint()` calls in `leaderboard_command()`

