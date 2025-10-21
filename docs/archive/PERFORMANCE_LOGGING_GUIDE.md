# Performance Logging Guide

## Overview

The EvoLadderBot now has comprehensive performance logging that outputs detailed timing information directly to the terminal. This guide explains how to read and interpret the logs.

---

## Log Output Format

### Console Output

Performance logs appear in the terminal with the following format:

```
[LEVEL] [flow_name] duration_ms (status)
  • checkpoint1: time_ms
  • checkpoint2: time_ms
  • checkpoint3: time_ms
```

### Performance Levels

The system uses visual indicators for different performance levels:

| Level | Emoji | ASCII | Threshold | Meaning |
|-------|-------|-------|-----------|---------|
| FAST | ⚡ | `[>]` | < 500ms | Excellent performance |
| OK | 🟢 | `[+]` | 500-1000ms | Acceptable performance |
| SLOW | 🟡 | `[*]` | 1000-3000ms | Warning - needs attention |
| CRITICAL | 🔴 | `[!]` | > 3000ms | Error - exceeds Discord limit |

**Note**: On Windows consoles, ASCII fallbacks (`[>]`, `[+]`, `[*]`, `[!]`) are used automatically.

---

## Example Log Output

### Fast Operation (✅ Excellent)

```
[>] FAST [queue_command] 245.67ms (success)
  • guard_checks: 12.34ms
  • load_preferences: 45.67ms
  • create_view: 23.45ms
  • send_response: 164.21ms
```

**Analysis**: All steps are fast, total time well under threshold.

### OK Operation (⚠️ Acceptable)

```
[+] OK [leaderboard_command] 687.23ms (success)
  • guard_checks: 15.23ms
  • fetch_leaderboard_data: 534.56ms
  • update_button_states: 125.67ms
  • send_response: 11.77ms
```

**Analysis**: `fetch_leaderboard_data` is the bottleneck (534ms), but total time is acceptable.

### Slow Operation (🚨 Warning)

```
[W]  Slow checkpoint: profile_command.fetch_mmr_data took 987.34ms

[*] SLOW [profile_command] 1245.89ms (success)
  • guard_checks: 18.45ms
  • fetch_player_data: 125.67ms
  • fetch_mmr_data: 987.34ms
  • create_embed: 89.12ms
  • send_response: 25.31ms
```

**Analysis**: 
- Slow checkpoint warning shows `fetch_mmr_data` took 987ms
- Total time exceeds 1000ms threshold
- This query should be optimized (consider adding indexes or caching)

### Critical Operation (❌ Error)

```
[W]  Slow checkpoint: setup_command.send_modal took 2345.67ms

[!] CRITICAL [setup_command] 3456.78ms (success)
  • guard_checks: 23.45ms
  • fetch_existing_data: 567.89ms
  • send_modal: 2345.67ms
  • complete: 519.77ms
```

**Analysis**:
- CRITICAL level means response took >3 seconds
- Risks Discord interaction timeout
- Immediate action required to optimize

---

## Checkpoint Warnings

Individual checkpoints that take >100ms trigger immediate warnings:

```
[W]  Slow checkpoint: queue_command.load_preferences took 234.56ms
```

This allows you to identify bottlenecks in real-time without waiting for the full flow to complete.

---

## Logging Configuration

### Location

Logging is configured in `src/bot/main.py`:

```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
```

### Log Levels

- **INFO**: All flow completions and standard checkpoints
- **WARNING**: Slow checkpoints (>100ms) and slow operations (>threshold)
- **ERROR**: Critical operations (>3000ms)

### Filtering Logs

To see only performance logs:

```python
# In main.py
logging.getLogger('discord').setLevel(logging.ERROR)  # Hide Discord noise
logging.getLogger('src.backend.services.performance_service').setLevel(logging.INFO)
```

To enable debug logging for ALL operations:

```python
logging.getLogger('src.backend.services.performance_service').setLevel(logging.DEBUG)
```

---

## Startup Output

When the bot starts, you'll see performance monitoring configuration:

```
[INFO] Performance monitoring ACTIVE - All commands will be tracked
[INFO] Performance thresholds configured:
  - queue_command: 500ms
  - setup_command: 1000ms
  - profile_command: 300ms
  - leaderboard_command: 500ms
  - activate_command: 200ms
  - setcountry_command: 150ms
  - termsofservice_command: 100ms
```

---

## Interpreting Logs for Optimization

### 1. Identify the Slowest Command

Look for `[*] SLOW` or `[!] CRITICAL` indicators:

```
[*] SLOW [setup_command] 1523.45ms (success)
```

### 2. Find the Bottleneck Checkpoint

Look at checkpoint breakdown to find the slow step:

```
  • guard_checks: 15.23ms          ✓ Fast
  • fetch_existing_data: 1234.56ms  ✗ BOTTLENECK
  • send_modal: 273.66ms            ✓ OK
```

### 3. Check for Slow Checkpoint Warnings

These appear inline as operations execute:

```
[W]  Slow checkpoint: leaderboard_command.fetch_leaderboard_data took 876.54ms
```

### 4. Prioritize Fixes

Focus on:
1. **Critical operations** (>3000ms) - Risk timeout
2. **Frequent slow operations** - Impact many users
3. **Checkpoint warnings** (>100ms) - Specific bottlenecks

---

## Common Performance Issues

### Database Queries

**Symptom:**
```
[W]  Slow checkpoint: profile_command.fetch_mmr_data took 987.34ms
```

**Solutions:**
- Add database indexes
- Use connection pooling (already implemented)
- Cache frequently accessed data
- Optimize query (reduce JOINs, select only needed columns)

### View/Embed Creation

**Symptom:**
```
[W]  Slow checkpoint: leaderboard_command.update_button_states took 456.78ms
```

**Solutions:**
- Pre-compute button states
- Simplify view logic
- Cache dropdown options
- Reduce number of UI components

### External API Calls

**Symptom:**
```
[W]  Slow checkpoint: queue_command.send_response took 345.67ms
```

**Solutions:**
- Use timeouts for Discord API calls
- Implement retries with exponential backoff
- Consider async operations
- Cache Discord-related data

---

## Production Monitoring

### Daily Review

Check logs daily for:
- Any `[!] CRITICAL` operations
- Increasing frequency of `[*] SLOW` warnings
- New checkpoint warnings
- Commands trending slower over time

### Performance Regression Detection

Compare current times with historical baseline:

```python
# Week 1: [>] FAST [queue_command] 245ms
# Week 2: [>] FAST [queue_command] 289ms
# Week 3: [+] OK [queue_command] 567ms     ← Regression detected!
# Week 4: [*] SLOW [queue_command] 1234ms  ← Critical regression!
```

### Alerting

Set up alerts for:
- Any command >3000ms (Discord timeout risk)
- Commands >2x their threshold
- Sustained increase in average times

---

## Real-Time Monitoring During Development

When running the bot locally, you'll see live performance logs:

```
$ python src/bot/main.py

[INFO] Performance monitoring ACTIVE - All commands will be tracked
[INFO] Bot online as EvoLadderBot

[User runs /queue]
[>] FAST [queue_command] 234.56ms (success)
  • guard_checks: 12.34ms
  • load_preferences: 45.67ms
  • create_view: 89.12ms
  • send_response: 87.43ms

[User runs /profile]
[>] FAST [profile_command] 178.90ms (success)
  • guard_checks: 11.23ms
  • fetch_player_data: 56.78ms
  • fetch_mmr_data: 67.89ms
  • create_embed: 34.56ms
  • send_response: 8.44ms
```

---

## Troubleshooting

### No Logs Appearing

**Check logging level:**
```python
# src/bot/main.py
logging.basicConfig(level=logging.INFO)  # Not DEBUG or higher
```

**Verify imports:**
```python
from src.backend.services.performance_service import FlowTracker
```

### Unicode/Emoji Errors

The system automatically detects Windows console encoding and uses ASCII fallbacks:
- ⚡ → `[>]`
- 🟢 → `[+]`
- 🟡 → `[*]`
- 🔴 → `[!]`
- ⚠️ → `[W]`

### Too Much Output

Filter by log level:
```python
# Only show slow/critical operations
logging.getLogger('src.backend.services.performance_service').setLevel(logging.WARNING)
```

---

## Best Practices

1. **Always complete flows**: Call `flow.complete("success")` or `flow.complete("error")`
2. **Use meaningful checkpoint names**: `guard_checks`, not `step1`
3. **Add checkpoints before/after expensive operations**
4. **Check logs after adding new features**
5. **Set realistic thresholds** for each command
6. **Monitor trends over time**, not just absolute values

---

## Summary

Performance logging is now active and will show:
- ✅ **Real-time timing** for all commands
- ✅ **Checkpoint breakdowns** showing bottlenecks
- ✅ **Automatic warnings** for slow operations
- ✅ **Visual indicators** for performance levels
- ✅ **Threshold alerts** for SLA violations

All logs appear in the terminal automatically - no additional configuration needed!

