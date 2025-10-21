# Discord API Performance Monitoring

## Overview

Added comprehensive timing instrumentation to measure Discord API lag during leaderboard filter operations. This helps distinguish between our code performance and Discord's API response times.

## Instrumentation Added

### 1. Filter Operations (`update_view` method)

When users interact with filters (country/race dropdowns, best race toggle, pagination), we now measure:

```
[Filter Perf] Data fetch: X.XXms
[Filter Perf] View creation: X.XXms  
[Filter Perf] Button updates: X.XXms
[Filter Perf] Embed generation: X.XXms
[Filter Perf] Discord API call: X.XXms  ← KEY METRIC
[Filter Perf] TOTAL FILTER OPERATION: X.XXms
```

**Alert Levels:**
- `⚠️  SLOW Discord API: >100ms` - Significant lag
- `🟡 Moderate Discord API: 50-100ms` - Noticeable lag
- `<50ms` - Normal performance

### 2. Initial Command (`leaderboard_command`)

For the initial `/leaderboard` command:

```
[Initial Command] Discord API call: X.XXms
```

**Alert Levels:**
- `⚠️  SLOW Discord API (initial): >100ms`
- `🟡 Moderate Discord API (initial): 50-100ms`

## What This Measures

### Filter Operations Breakdown

1. **Data fetch** - Backend service call (should be < 20ms with our optimizations)
2. **View creation** - Creating new LeaderboardView instance (should be < 5ms)
3. **Button updates** - Updating button states and pagination (should be < 5ms)
4. **Embed generation** - Creating Discord embed (should be < 10ms with emote optimization)
5. **Discord API call** - `interaction.response.edit_message()` (this is what we're measuring!)

### Expected Performance

#### Normal Conditions
- **Data fetch**: 1-20ms
- **View creation**: 1-5ms
- **Button updates**: 1-5ms
- **Embed generation**: 3-10ms
- **Discord API call**: 20-50ms
- **Total**: 30-90ms

#### With Discord API Issues
- **Our code**: 10-40ms (unchanged)
- **Discord API call**: 100-500ms+ (the bottleneck)
- **Total**: 150-600ms+

## How to Use This Data

### 1. Run the Bot and Test Filters
```bash
python -m src.bot.main
# Use /leaderboard in Discord
# Try different filters, toggles, pagination
```

### 2. Watch Console Output
You'll see detailed timing for each filter operation:

```
[Filter Perf] Data fetch: 2.15ms
[Filter Perf] View creation: 1.23ms
[Filter Perf] Button updates: 0.45ms
[Filter Perf] Embed generation: 3.67ms
[Filter Perf] Discord API call: 45.23ms
[Filter Perf] TOTAL FILTER OPERATION: 52.73ms
```

### 3. Identify the Bottleneck

**If Discord API is slow (>100ms):**
- The lag is on Discord's side
- Network latency, Discord server load, or rate limiting
- Our optimizations won't help much
- Consider reducing embed complexity or frequency

**If our code is slow (>50ms total before Discord API):**
- Backend service needs optimization
- Embed generation needs work
- Our emote optimization didn't work

**If everything is fast (<50ms total):**
- The perceived lag might be Discord client-side rendering
- Or network latency between user and Discord

## Common Scenarios

### Scenario 1: Fast Filter Operations
```
[Filter Perf] Data fetch: 1.23ms
[Filter Perf] View creation: 0.89ms
[Filter Perf] Button updates: 0.34ms
[Filter Perf] Embed generation: 2.45ms
[Filter Perf] Discord API call: 25.67ms
[Filter Perf] TOTAL FILTER OPERATION: 30.58ms
```
**Interpretation**: Everything is working well. Total time is reasonable.

### Scenario 2: Discord API Lag
```
[Filter Perf] Data fetch: 1.45ms
[Filter Perf] View creation: 0.92ms
[Filter Perf] Button updates: 0.38ms
[Filter Perf] Embed generation: 2.67ms
[Filter Perf] Discord API call: 234.56ms
⚠️  SLOW Discord API: 234.56ms
[Filter Perf] TOTAL FILTER OPERATION: 239.98ms
```
**Interpretation**: Discord API is slow. Our code is fast (5.42ms), but Discord took 234ms to respond.

### Scenario 3: Our Code is Slow
```
[Filter Perf] Data fetch: 45.23ms
[Filter Perf] View creation: 12.34ms
[Filter Perf] Button updates: 3.45ms
[Filter Perf] Embed generation: 67.89ms
[Filter Perf] Discord API call: 28.90ms
[Filter Perf] TOTAL FILTER OPERATION: 157.81ms
```
**Interpretation**: Our code is the bottleneck (128.91ms), not Discord API.

## Optimization Strategies

### If Discord API is Slow
1. **Reduce embed complexity** - Fewer fields, simpler formatting
2. **Batch operations** - Don't update on every filter change
3. **Debounce filters** - Wait for user to stop selecting before updating
4. **Use ephemeral responses** - Faster than editing messages
5. **Consider pagination** - Smaller embeds = faster API calls

### If Our Code is Slow
1. **Backend optimization** - Already done with emote batching
2. **Embed generation** - Simplify formatting logic
3. **View creation** - Cache view components
4. **Data fetching** - Use process pool for heavy operations

### If Everything is Fast but Still Feels Slow
1. **User perception** - Add loading indicators
2. **Network latency** - User's connection to Discord
3. **Discord client** - Client-side rendering lag
4. **Rate limiting** - Too many API calls too quickly

## Monitoring Dashboard

### Key Metrics to Track
- **Discord API call time** - Primary bottleneck indicator
- **Total filter operation time** - User-perceived latency
- **Our code vs Discord API ratio** - Where to focus optimization

### Alert Thresholds
- **Discord API > 100ms**: Investigate Discord status
- **Discord API > 200ms**: Consider reducing embed complexity
- **Our code > 50ms**: Optimize backend/embed generation
- **Total > 200ms**: User experience degradation

## Files Modified

1. `src/bot/commands/leaderboard_command.py`
   - Added timing to `update_view()` method
   - Added timing to initial command
   - Added alert levels for slow API calls

## Removing Instrumentation

Once performance is optimized, search for:
- `[Filter Perf]` - Filter operation timing
- `[Initial Command]` - Initial command timing
- `⚠️  SLOW Discord API` - Alert messages

Remove all timing code to clean up console output.

## Conclusion

This instrumentation will help us determine if the leaderboard lag is:
1. **Our code** (backend/embed generation) - We can optimize
2. **Discord API** (network/server) - We can work around it
3. **User perception** (client rendering) - We can improve UX

The data will guide our optimization efforts in the right direction! 🎯
