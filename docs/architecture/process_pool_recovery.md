# Process Pool Recovery System

## Overview

The bot uses a `ProcessPoolExecutor` for CPU-bound tasks like replay parsing and leaderboard processing. Worker processes can crash due to various reasons (memory issues, segfaults, etc.), which causes the entire pool to become unusable.

This document describes the automatic monitoring and recovery system that ensures the process pool remains healthy.

## Problem

When a worker process crashes:
- The pool enters a `BrokenProcessPool` state
- All subsequent tasks fail with `BrokenProcessPool` exceptions
- The bot becomes unable to process replays or refresh leaderboards
- Manual restart is required to recover

**Test Results:**
```
[Test 2] Worker crash detected: BrokenProcessPool
[Test 3] Pool may be damaged: BrokenProcessPool: 
         A child process terminated abruptly, the process pool is not usable anymore
```

## Solution

### 1. Health Check Mechanism

The bot performs periodic health checks every 30 seconds:

```python
async def _check_and_restart_process_pool(self) -> bool:
    """Check if the process pool is healthy and restart it if needed."""
    if not self.process_pool:
        logger.error("[Process Pool] Process pool is None, attempting restart...")
        return await self._restart_process_pool()
    
    # Test pool health with a simple task
    try:
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self.process_pool, lambda: True)
        await asyncio.wait_for(future, timeout=5.0)
        return True
    except (asyncio.TimeoutError, Exception) as e:
        logger.error(f"[Process Pool] Health check failed: {e}")
        return await self._restart_process_pool()
```

**Health Check Process:**
1. Submit a simple test task to the pool
2. Wait up to 5 seconds for response
3. If successful → pool is healthy
4. If timeout/error → trigger restart

### 2. Automatic Restart

When a pool is detected as unhealthy, it's automatically restarted:

```python
async def _restart_process_pool(self) -> bool:
    """Restart the process pool."""
    async with self._process_pool_lock:
        try:
            # Shutdown old pool
            if self.process_pool:
                print("[Process Pool] Shutting down crashed pool...")
                self.process_pool.shutdown(wait=False, cancel_futures=True)
            
            # Create new pool
            print(f"[Process Pool] Creating new pool with {WORKER_PROCESSES} worker(s)...")
            self.process_pool = ProcessPoolExecutor(max_workers=WORKER_PROCESSES)
            print("[Process Pool] ✅ Process pool restarted successfully")
            return True
        except Exception as e:
            logger.error(f"[Process Pool] ❌ Failed to restart process pool: {e}")
            return False
```

**Restart Process:**
1. Acquire lock to prevent concurrent restarts
2. Shutdown crashed pool (non-blocking, cancel pending tasks)
3. Create fresh `ProcessPoolExecutor` instance
4. Replace the old pool reference
5. Log success/failure

### 3. Background Monitor Task

A dedicated background task runs continuously:

```python
async def _monitor_process_pool_task(self):
    """Background task that monitors the process pool health."""
    await self.wait_until_ready()
    print("[Process Pool Monitor] Starting process pool health monitoring...")
    
    while not self.is_closed():
        try:
            await asyncio.sleep(30)  # Check every 30 seconds
            
            is_healthy = await self._check_and_restart_process_pool()
            if is_healthy:
                print("[Process Pool Monitor] ✅ Health check passed")
            else:
                logger.error("[Process Pool Monitor] ❌ Health check failed after restart")
        except Exception as e:
            logger.error(f"[Process Pool Monitor] Error in monitoring task: {e}")
```

**Monitoring Schedule:**
- Health check every 30 seconds
- Automatic restart on failure
- Continuous operation until bot shutdown

### 4. Reactive Recovery

In addition to periodic checks, the leaderboard cache refresh task triggers recovery when it detects process pool errors:

```python
except Exception as e:
    logger.error(f"[Background Task] Error refreshing leaderboard cache: {e}")
    
    # If error involves the process pool, trigger a health check
    if "process" in str(e).lower() or "pool" in str(e).lower():
        logger.info("[Background Task] Process pool error detected, triggering health check...")
        await self._check_and_restart_process_pool()
```

This provides **immediate recovery** when a crash occurs during active use.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    EvoLadderBot                      │
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │   Process Pool Monitor Task (30s interval)   │  │
│  │                                              │  │
│  │  • Health check via simple test task        │  │
│  │  • Automatic restart on failure             │  │
│  │  • Continuous monitoring                    │  │
│  └───────────────┬──────────────────────────────┘  │
│                  │                                  │
│                  ↓                                  │
│  ┌──────────────────────────────────────────────┐  │
│  │   _check_and_restart_process_pool()          │  │
│  │                                              │  │
│  │  • Submit test task with 5s timeout         │  │
│  │  • Catch BrokenProcessPool exceptions       │  │
│  │  • Trigger restart on failure               │  │
│  └───────────────┬──────────────────────────────┘  │
│                  │                                  │
│                  ↓                                  │
│  ┌──────────────────────────────────────────────┐  │
│  │   _restart_process_pool()                    │  │
│  │                                              │  │
│  │  • Thread-safe restart with asyncio.Lock    │  │
│  │  • Shutdown old pool (non-blocking)         │  │
│  │  • Create fresh ProcessPoolExecutor         │  │
│  └──────────────────────────────────────────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │   Leaderboard Cache Refresh (60s interval)   │  │
│  │                                              │  │
│  │  • Reactive recovery on pool errors         │  │
│  │  • Triggers health check immediately        │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Benefits

### ✅ Automatic Recovery
- No manual intervention required
- Pool crashes are detected and fixed automatically
- Bot maintains availability

### ✅ Proactive Monitoring
- Health checks every 30 seconds
- Catches issues before they affect users
- Prevents cascade failures

### ✅ Reactive Recovery
- Immediate detection during active tasks
- Minimizes downtime
- Fast recovery path

### ✅ Thread-Safe
- Uses `asyncio.Lock` to prevent concurrent restarts
- Safe under high load
- No race conditions

## Testing

Run the test suite to verify crash recovery:

```bash
python tests/backend/services/test_process_pool_recovery.py
```

**Test Scenarios:**
1. ✅ Normal execution verification
2. ✅ Worker crash (`os._exit`) detection
3. ⚠️  Pool damage verification (demonstrates need for recovery)
4. ✅ Exception handling
5. ✅ Timeout detection
6. ✅ Health check after crash

## Configuration

Adjust monitoring interval in `bot_setup.py`:

```python
await asyncio.sleep(30)  # Check every 30 seconds
```

Adjust health check timeout:

```python
await asyncio.wait_for(future, timeout=5.0)  # 5 second timeout
```

Adjust worker count in `config.py`:

```python
WORKER_PROCESSES = 2  # Number of worker processes
```

## Logs

Monitor pool health in production logs:

```
[Process Pool Monitor] ✅ Health check passed
[Process Pool Monitor] ❌ Health check failed
[Process Pool] Shutting down crashed pool...
[Process Pool] Creating new pool with 2 worker(s)...
[Process Pool] ✅ Process pool restarted successfully
```

## Future Enhancements

Potential improvements:

1. **Metrics & Alerting**
   - Track crash frequency
   - Alert on repeated failures
   - Monitor recovery time

2. **Graceful Degradation**
   - Reduce worker count if crashes persist
   - Fallback to synchronous processing

3. **Crash Analysis**
   - Log crash context (task type, data)
   - Identify patterns
   - Root cause analysis

4. **Circuit Breaker**
   - Temporary disable if crashes exceed threshold
   - Prevent restart loops
   - Manual recovery mode

