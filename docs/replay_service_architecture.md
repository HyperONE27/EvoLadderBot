# ReplayService Architecture

## Overview

The replay parsing system is split into two distinct parts to handle both CPU-bound and I/O-bound operations efficiently.

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    Discord Bot (Main Process)                    │
│                                                                  │
│  User uploads replay                                             │
│         ↓                                                        │
│  on_message() downloads replay_bytes                             │
│         ↓                                                        │
│  ┌──────────────────────────────────────────────────┐            │
│  │  CPU-BOUND WORK (offloaded to worker)            │            │
│  │  ─────────────────────────────────────────────   │            │
│  │  loop.run_in_executor(                           │            │
│  │    bot.process_pool,                             │────────────┼──> Worker Process
│  │    parse_replay_data_blocking,                   │            │    (Separate OS process)
│  │    replay_bytes                                  │            │         ↓
│  │  )                                               │            │    Parse with sc2reader
│  │  → Returns: dict with parsed data                │<───────────┼─── Returns: dict
│  └──────────────────────────────────────────────────┘            │
│         ↓                                                        │
│  ┌──────────────────────────────────────────────────┐            │
│  │  I/O-BOUND WORK (fast, runs in main process)     │            │
│  │  ────────────────────────────────────────────    │            │
│  │  ReplayService.store_upload_from_parsed_dict(    │            │
│  │    match_id,                                     │            │
│  │    uploader_id,                                  │            │
│  │    replay_bytes,                                 │            │
│  │    parsed_dict                                   │            │
│  │  )                                               │            │
│  │  → Saves file to disk (~5ms)                     │            │
│  │  → Inserts into database (~10ms)                 │            │
│  └──────────────────────────────────────────────────┘            │
│         ↓                                                        │
│  Send success message to Discord                                 │
└──────────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### 1. `parse_replay_data_blocking()` - CPU-Bound Worker Function

**Location**: Module-level function in `replay_service.py`

**Purpose**: Performs intensive replay parsing using sc2reader

**Characteristics**:
- ❌ **NOT** part of ReplayService class
- ✅ Runs in separate worker process
- ✅ Can utilize multiple CPU cores
- ✅ Doesn't block the event loop
- ⏱️ Takes ~100-200ms per replay

**What it does**:
```python
replay_bytes → [Worker Process] → {
    "replay_hash": "abc123...",
    "player_1_name": "Dark",
    "player_2_name": "ReBellioN",
    "map_name": "Neo Isles of Siren",
    "duration": 1344,
    # ... all other parsed fields
}
```

**Why standalone**: Must be pickleable (serializable) to send to worker process. Class methods are difficult to pickle.

### 2. `ReplayService` - I/O-Bound Orchestrator

**Location**: Class in `replay_service.py`

**Purpose**: Fast I/O operations that DON'T involve parsing

**Characteristics**:
- ✅ Runs in main process (safe - operations are fast)
- ✅ Handles file storage
- ✅ Handles database operations
- ✅ Simple string/byte operations
- ⏱️ Takes ~15-20ms total

**What it does**:

#### Active Methods (Production Use)

1. **`is_sc2_replay(filename)`** - Check file extension
   - Used by: `on_message()` to detect replay files
   - Performance: <1ms
   
2. **`save_replay(replay_bytes)`** - Write file to disk
   - Generates hash-based filename
   - Saves to `data/replays/`
   - Performance: ~5-10ms
   
3. **`store_upload_from_parsed_dict(...)`** - **PRIMARY METHOD**
   - Accepts pre-parsed dictionary
   - Saves file
   - Inserts into database
   - Updates match records
   - Performance: ~15-20ms total

#### Legacy Methods (Testing/Debugging Only)

1. **`parse_replay()`** - ⚠️ LEGACY - Blocks event loop
   - Use for: Local testing, debugging
   - Don't use for: Production bot
   
2. **`store_upload()`** - ⚠️ LEGACY - Calls blocking parse
   - Use for: Local testing, debugging
   - Don't use for: Production bot

#### Helper Methods (Private, Used Internally)

- `_calculate_replay_hash()` - Compute blake2b hash
- `_generate_filename()` - Create timestamped filename
- All the old `_load_replay()`, `_get_player_info()`, etc. are kept for the legacy methods but duplicated in the worker function

## Why This Split?

### The Problem with the Old Way

```python
# OLD (Everything in ReplayService)
class ReplayService:
    def store_upload(self, replay_bytes):
        replay = sc2reader.load_replay(replay_bytes)  # 🐌 BLOCKS 100-200ms
        # ... extract data ...
        self.save_file()      # Fast
        self.save_to_db()     # Fast
```

**Issue**: The entire bot freezes for 100-200ms during parsing.

### The Solution with the New Way

```python
# NEW (Split responsibilities)

# Step 1: CPU work in worker (doesn't block)
parsed = await loop.run_in_executor(
    pool, 
    parse_replay_data_blocking,  # 🚀 Runs in parallel
    replay_bytes
)

# Step 2: I/O work in main process (fast, safe to block)
result = replay_service.store_upload_from_parsed_dict(
    match_id,
    uploader_id,
    replay_bytes,
    parsed  # Already parsed!
)
```

**Benefit**: Bot only "blocks" for ~15ms instead of 100-200ms, and can handle multiple parses concurrently.

## What Each Component Does

| Component | Type | Location | Purpose | Duration |
|-----------|------|----------|---------|----------|
| `parse_replay_data_blocking()` | Function | Module-level | CPU-intensive parsing | 100-200ms |
| `ReplayService.is_sc2_replay()` | Method | Class | Check file extension | <1ms |
| `ReplayService.save_replay()` | Method | Class | Write file to disk | 5-10ms |
| `ReplayService.store_upload_from_parsed_dict()` | Method | Class | Save & database ops | 15-20ms |
| `ReplayService.parse_replay()` | Method | Class | **LEGACY** - blocks | 100-200ms |
| `ReplayService.store_upload()` | Method | Class | **LEGACY** - blocks | 100-200ms |

## Production Workflow

```python
# In queue_command.py - on_message() handler

# 1. Detect replay file
if replay_service.is_sc2_replay(attachment.filename):
    
    # 2. Download bytes
    replay_bytes = await attachment.read()
    
    # 3. Parse in worker (non-blocking)
    loop = asyncio.get_running_loop()
    parsed_dict = await loop.run_in_executor(
        bot.process_pool,
        parse_replay_data_blocking,
        replay_bytes
    )
    # Bot can handle other requests while waiting ↑
    
    # 4. Store results (fast, runs immediately)
    result = replay_service.store_upload_from_parsed_dict(
        match_id,
        uploader_id,
        replay_bytes,
        parsed_dict
    )
    
    # 5. Send confirmation to Discord
    await message.channel.send(embed=success_embed)
```

## When to Use Each Method

### Use `parse_replay_data_blocking()` when:
- ✅ In production Discord bot
- ✅ Parsing uploaded replay files
- ✅ Need non-blocking behavior
- ✅ Need concurrent parsing

### Use `ReplayService.store_upload_from_parsed_dict()` when:
- ✅ In production Discord bot
- ✅ You have pre-parsed data from worker
- ✅ Need to save file and update database

### Use `ReplayService.parse_replay()` when:
- ✅ Writing unit tests
- ✅ Debugging locally
- ✅ Command-line scripts
- ❌ NOT in production bot

### Use `ReplayService.store_upload()` when:
- ✅ Writing simple tests that need everything
- ✅ Quick local debugging
- ❌ NOT in production bot

## Future Optimization Opportunities

### Option 1: Remove Duplication

All the helper methods (`_get_player_info`, `_fix_race`, `_get_winner`, etc.) are now duplicated:
- Once in `parse_replay_data_blocking()` (for workers)
- Once as `ReplayService` methods (for legacy)

**Could remove**: If we fully deprecate `parse_replay()` and `store_upload()`, we could delete all the class helper methods.

**Pros**: Cleaner, less code duplication
**Cons**: Can't use those methods for testing/debugging

### Option 2: Keep for Testing

Keep the legacy methods around as-is for convenience in tests and local debugging.

**Pros**: Easier to write quick tests
**Cons**: Code duplication, potential confusion

## Recommended Action

For now: **Keep both** but mark legacy methods clearly (already done).

Later: If you find you never use the legacy methods, delete them and all associated helpers in a future cleanup pass.

## Summary

**`parse_replay_data_blocking()`** = CPU-heavy parsing in workers  
**`ReplayService`** = Fast I/O operations in main process  

This separation ensures the bot remains responsive while handling the heavy lifting in parallel worker processes.

