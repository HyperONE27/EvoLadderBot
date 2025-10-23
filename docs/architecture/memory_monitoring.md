# Memory Monitoring System

## Overview

Comprehensive memory monitoring system for tracking memory usage and detecting leaks in both the main process and worker processes.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Main Process                             │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │         Memory Monitor Service                       │    │
│  │  - psutil for process-level monitoring               │    │
│  │  - tracemalloc for allocation tracking               │    │
│  │  - Periodic reporting (every 5 minutes)              │    │
│  │  - Leak detection (threshold: 100 MB)                │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  Logs memory at:                                             │
│  • Startup (baseline)                                        │
│  • After DB pool init                                        │
│  • After static cache init                                   │
│  • After process pool init                                   │
│  • Before/after replay parsing                               │
│  • Every 5 minutes (periodic)                                │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Worker Processes                          │
│                                                              │
│  Replay Parsing Worker:                                      │
│  • Memory before parse                                       │
│  • Memory after parse                                        │
│  • Delta calculation                                         │
│                                                              │
│  Leaderboard Refresh Worker:                                 │
│  • Memory before refresh                                     │
│  • Memory after refresh                                      │
│  • Delta calculation                                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. MemoryMonitor Service (`memory_monitor.py`)

**Features:**
- **Process-level monitoring**: Uses psutil to track RSS, VMS, and memory percent
- **Allocation tracking**: Uses tracemalloc for detailed allocation information
- **Baseline tracking**: Records baseline memory on initialization
- **Delta calculation**: Tracks memory growth from baseline
- **Leak detection**: Alerts when growth exceeds threshold
- **Garbage collection**: Forces GC and reports freed memory
- **Report generation**: Comprehensive memory reports with top allocations

**Key Methods:**
- `get_memory_usage()` - Current memory in MB
- `get_memory_details()` - Detailed memory information
- `get_memory_delta()` - Change since baseline
- `get_top_allocations()` - Top memory allocations
- `force_garbage_collection()` - Force GC and report
- `generate_report()` - Comprehensive memory report
- `log_memory_usage()` - Quick logging
- `check_memory_leak()` - Leak detection

### 2. Periodic Monitoring Task

**Location:** `bot_setup.py`

**Behavior:**
- Runs every 5 minutes
- Logs current memory usage
- Checks for leaks (threshold: 100 MB)
- If leak detected:
  - Generates detailed report with allocations
  - Forces garbage collection
  - Logs results

### 3. Worker Process Monitoring

**Replay Parsing Worker:**
- Tracks memory before and after sc2reader parsing
- Reports delta to identify memory-intensive replays
- Helps identify replay parsing memory leaks

**Leaderboard Refresh Worker:**
- Tracks memory before and after DataFrame creation
- Reports delta to identify leaderboard cache growth
- Helps identify database query and Polars memory usage

### 4. Critical Operation Logging

**Main Process:**
- Startup baseline
- Database pool initialization
- Static cache initialization
- Process pool initialization
- Replay parsing operations

## Memory Thresholds

| Component | Expected | Alert Threshold | Action |
|-----------|----------|-----------------|--------|
| Baseline | 50-100 MB | N/A | Log only |
| Delta (periodic) | 0-50 MB | 100 MB | Generate report, force GC |
| Replay parsing spike | +20-50 MB | N/A | Log delta |
| Leaderboard refresh spike | +50-100 MB | N/A | Log delta |

## Usage

### Initialize at Startup

```python
from src.backend.monitoring.memory_monitor import initialize_memory_monitor, log_memory

# Initialize with tracemalloc
initialize_memory_monitor(enable_tracemalloc=True)
log_memory("Startup - baseline")
```

### Log Memory at Checkpoints

```python
from src.backend.monitoring.memory_monitor import log_memory

# Before critical operation
log_memory("Before heavy operation")

# ... do work ...

# After critical operation
log_memory("After heavy operation")
```

### Generate Detailed Report

```python
from src.backend.monitoring.memory_monitor import get_memory_monitor

monitor = get_memory_monitor()
if monitor:
    report = monitor.generate_report(include_allocations=True)
    print(report)
```

### Check for Leaks

```python
monitor = get_memory_monitor()
if monitor:
    if monitor.check_memory_leak(threshold_mb=100.0):
        # Generate report
        report = monitor.generate_report(include_allocations=True)
        logger.warning(f"Memory leak detected:\n{report}")
        
        # Force GC
        collected, freed = monitor.force_garbage_collection()
        logger.info(f"GC freed {freed:.2f} MB")
```

## Output Examples

### Startup Logging

```
[Startup] Initializing memory monitor...
[Memory Monitor] tracemalloc started
[Memory Monitor] Baseline memory: 45.23 MB
[Memory Monitor] 45.23 MB (Delta +0.00 MB) - Startup - baseline
[Memory Monitor] 58.45 MB (Delta +13.22 MB) - After DB pool init
[Memory Monitor] 72.31 MB (Delta +27.08 MB) - After static cache init
[Memory Monitor] 75.12 MB (Delta +29.89 MB) - After process pool init
```

### Periodic Check

```
[Memory Monitor] 110.45 MB (Delta +65.22 MB) - Periodic check
```

### Leak Detection

```
[Memory Monitor] Potential memory leak detected! Growth: 120.45 MB (threshold: 100.00 MB)
============================================================
MEMORY USAGE REPORT
============================================================
Current RSS:     165.68 MB
Virtual Memory:  250.12 MB
Memory Percent:  0.52%
Baseline:        45.23 MB
Delta:           +120.45 MB

Top 5 Allocations:
------------------------------------------------------------
  45.23 MB: File "src/backend/services/leaderboard_service.py", line 142
  28.67 MB: File "src/backend/db/db_reader_writer.py", line 234
  15.32 MB: File "src/backend/services/replay_service.py", line 156
  ...
============================================================

[Memory Monitor] Forced GC: collected 1234 objects, freed 8.45 MB
```

### Worker Process Logging

```
[Worker Process] Memory before parse: 85.23 MB
[Worker Process] Parse complete for hash abc123 in 2.456s
[Worker Process] Memory after parse: 112.45 MB (Delta +27.22 MB)

[Leaderboard Worker] Memory before refresh: 90.12 MB
[Leaderboard Worker] Created DataFrame with 1523 rows
[Leaderboard Worker] Memory after refresh: 145.67 MB (Delta +55.55 MB)
```

## Troubleshooting

### High Baseline Memory

**Symptoms:** Baseline > 100 MB at startup

**Possible Causes:**
- Large static data files loaded
- Database connection pool too large
- Mock data files accidentally loaded

**Investigation:**
1. Check top allocations in startup report
2. Review static cache initialization
3. Verify connection pool size

### Growing Delta Over Time

**Symptoms:** Delta increases continuously without recovery

**Possible Causes:**
- Memory leak in cache
- Database connections not released
- Worker processes accumulating memory

**Investigation:**
1. Check periodic reports for growth trend
2. Review top allocations for leak source
3. Force GC and check if memory is freed

### Large Spikes

**Symptoms:** Periodic large memory spikes

**Possible Causes:**
- Heavy replay parsing
- Large leaderboard refresh
- Concurrent operations

**Investigation:**
1. Check worker process logs for deltas
2. Correlate spikes with operations
3. Review if memory recovers after spike

## Best Practices

1. **Always initialize early**: Initialize memory monitor before other resources
2. **Log at checkpoints**: Log memory at critical checkpoints
3. **Monitor trends**: Look for increasing deltas over time
4. **Investigate spikes**: Large deltas indicate memory-intensive operations
5. **Force GC when needed**: If leak detected, force GC to reclaim memory
6. **Review worker logs**: Worker deltas show per-operation memory usage

## Dependencies

- `psutil>=5.9.0` - Process-level memory monitoring
- Python `tracemalloc` (built-in) - Allocation tracking
- Python `gc` (built-in) - Garbage collection

## Testing

Run the memory monitoring test suite:

```bash
python tests/backend/services/test_memory_monitor.py
```

Tests verify:
- Basic memory tracking
- Report generation
- Garbage collection
- Leak detection
- Periodic monitoring
