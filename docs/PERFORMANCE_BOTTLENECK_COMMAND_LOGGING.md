# Performance Bottleneck: Command Logging

**Date**: October 20, 2025  
**Issue**: Command logging adds ~160ms to every command execution  
**Impact**: All commands are slower than necessary, setup feels glacially slow

---

## Problem Identification

### Observation from Logs

```
⚠️ Slow checkpoint: interaction.leaderboard.command_logged took 161.45ms
⚠️ Slow checkpoint: interaction.termsofservice.command_logged took 161.02ms
⚠️ Slow checkpoint: setup_command.guard_checks_complete took 160.22ms
```

**Every command** includes a synchronous database write to `command_calls` table that takes ~160ms.

### Why This Is Slow

1. **Network Latency**: Supabase is remote (likely US/EU), adding RTT
2. **Synchronous Execution**: Blocks command execution until write completes
3. **No Batching**: Each command = separate INSERT statement
4. **Non-Critical Path**: Command logging is analytics, not business logic

---

## Solution: Async Background Logging

### Strategy

Move command logging to **background tasks** so they don't block command execution.

### Implementation Options

#### Option 1: Asyncio Background Task (Immediate)

**Pros**:
- Simple to implement
- No additional dependencies
- Works with existing connection pool

**Cons**:
- Lost logs if bot crashes before write
- Still hits database immediately

**Code**:
```python
# In bot_setup.py

async def log_command_async(discord_uid: int, player_name: str, command: str):
    """Log command call asynchronously without blocking"""
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            db_writer.log_command_call,
            discord_uid,
            player_name,
            command
        )
    except Exception as e:
        # Log error but don't fail the command
        logger.error(f"Failed to log command {command}: {e}")

async def on_interaction(self, interaction: discord.Interaction):
    # ... existing code ...
    
    # Fire and forget - don't await
    asyncio.create_task(log_command_async(
        interaction.user.id,
        interaction.user.name,
        command_name
    ))
    
    # Continue immediately
    flow.checkpoint("command_logged")
```

**Expected Improvement**: ~160ms saved on every command

---

#### Option 2: Batched Queue System (Better)

**Pros**:
- Reduces database connections
- Better for high traffic
- More resilient to spikes

**Cons**:
- More complex
- Requires queue management

**Code**:
```python
# New file: src/backend/services/command_logger_service.py

import asyncio
from collections import deque
from typing import List, Tuple
from src.backend.db.db_reader_writer import DatabaseWriter

class CommandLoggerService:
    """Background service for batched command logging"""
    
    def __init__(self, batch_size: int = 10, flush_interval: float = 5.0):
        self.queue: deque[Tuple[int, str, str]] = deque()
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.db_writer = DatabaseWriter()
        self.running = False
        self.task = None
        
    def log_command(self, discord_uid: int, player_name: str, command: str):
        """Add command to queue (non-blocking)"""
        self.queue.append((discord_uid, player_name, command))
        
    async def start(self):
        """Start background flush task"""
        self.running = True
        self.task = asyncio.create_task(self._flush_loop())
        
    async def stop(self):
        """Stop and flush remaining"""
        self.running = False
        if self.task:
            await self.task
        await self._flush_queue()
        
    async def _flush_loop(self):
        """Periodically flush queue"""
        while self.running:
            await asyncio.sleep(self.flush_interval)
            if len(self.queue) >= self.batch_size:
                await self._flush_queue()
                
    async def _flush_queue(self):
        """Flush queued commands to database"""
        if not self.queue:
            return
            
        batch: List[Tuple] = []
        while self.queue and len(batch) < self.batch_size:
            batch.append(self.queue.popleft())
            
        if batch:
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(
                    None,
                    self._write_batch,
                    batch
                )
            except Exception as e:
                # Re-queue on failure
                self.queue.extendleft(reversed(batch))
                logger.error(f"Failed to flush command batch: {e}")
                
    def _write_batch(self, batch: List[Tuple]):
        """Write batch to database"""
        # Use bulk insert
        for discord_uid, player_name, command in batch:
            self.db_writer.log_command_call(discord_uid, player_name, command)

# Global instance
command_logger = CommandLoggerService()
```

**Usage**:
```python
# In bot_setup.py

async def setup_hook(self):
    await command_logger.start()
    
async def close(self):
    await command_logger.stop()
    await super().close()

async def on_interaction(self, interaction: discord.Interaction):
    # Non-blocking queue add (microseconds)
    command_logger.log_command(
        interaction.user.id,
        interaction.user.name,
        command_name
    )
    flow.checkpoint("command_logged")  # Now instant
```

**Expected Improvement**: ~160ms saved + reduced database load

---

#### Option 3: Remove Command Logging (Nuclear)

**Question**: Do you actually need command logging?

**If No**:
- Remove `command_calls` table
- Remove all `log_command_call` calls
- **Instant 160ms improvement**

**If Yes (for analytics)**:
- Keep it but make it async (Option 1 or 2)

---

## Other Quick Wins

### 1. Cache Player Records More Aggressively

Current TTL: 5 minutes

**Issue**: Guard checks still hit database frequently

**Solution**: Increase TTL to 15 minutes for active users
```python
# In cache_service.py
class PlayerRecordCache:
    def __init__(self, ttl_seconds: int = 900):  # 15 minutes
        # ...
```

### 2. Prefetch Setup Data

**Issue**: Setup fetches existing data serially

**Solution**: Parallel queries
```python
# In setup_command.py
async def fetch_setup_data(discord_uid):
    loop = asyncio.get_running_loop()
    
    # Fetch in parallel
    player_task = loop.run_in_executor(None, db_reader.get_player_by_discord_uid, discord_uid)
    mmrs_task = loop.run_in_executor(None, db_reader.get_all_mmrs_1v1_for_player, discord_uid)
    
    player, mmrs = await asyncio.gather(player_task, mmrs_task)
    return player, mmrs
```

### 3. Lazy Load Non-Critical Data

**Issue**: Leaderboard fetches all data upfront

**Solution**: Paginate and load on-demand
```python
# Initial load: Top 10 only
# Load more when user clicks "Next Page"
```

---

## Recommended Action Plan

### Phase 1: Immediate (5 minutes)

✅ **Implement Option 1: Async Command Logging**
- Move `log_command_call` to background task
- Expected: 160ms improvement per command

### Phase 2: Short-term (30 minutes)

✅ **Increase Player Cache TTL**
- Change from 5 minutes to 15 minutes
- Expected: Fewer guard check database hits

✅ **Parallel Setup Data Fetching**
- Use `asyncio.gather` for parallel queries
- Expected: 50-100ms improvement on setup

### Phase 3: Medium-term (2 hours)

✅ **Implement Option 2: Batched Queue System**
- Replace Option 1 with proper queue
- Expected: Better handling of traffic spikes

### Phase 4: Long-term (Consider)

⚠️ **Evaluate if you need command logging**
- If analytics aren't critical, remove it
- If needed, consider external analytics service

---

## Expected Performance After Phase 1

### Current

```
leaderboard_command: 742ms (160ms command_logged + 582ms actual work)
termsofservice_command: 161ms (159ms command_logged + 2ms actual work)
setup_command: 1000ms+ (320ms command_logged + guard + fetch + 680ms work)
```

### After Phase 1

```
leaderboard_command: 582ms (0ms command_logged + 582ms actual work)
termsofservice_command: 2ms (0ms command_logged + 2ms actual work)
setup_command: 840ms (0ms command_logged + 840ms work)
```

### After Phase 1 + 2 + 3

```
leaderboard_command: 450ms (cached guard + optimized queries)
termsofservice_command: 2ms
setup_command: 600ms (parallel queries + cached guard)
```

---

## Implementation

Ready to implement? I can:

1. ✅ Add async command logging (Option 1) right now
2. ✅ Increase cache TTL
3. ✅ Add parallel query fetching for setup

This will make your bot feel **significantly faster**, especially for setup.

**Want me to proceed?**

