# Performance Monitoring Plan

## Overview

This document outlines a comprehensive strategy for measuring and logging bot flow performance to identify bottlenecks, optimize user experience, and track system health over time.

---

## 1. Goals

### Primary Objectives
- **Measure end-to-end latency** for all user-facing commands
- **Identify performance bottlenecks** in database queries, API calls, and processing
- **Track interaction response times** to ensure Discord API compliance (<3s for interactions)
- **Monitor resource utilization** (database connections, process pool, memory)
- **Log slow operations** for debugging and optimization
- **Generate performance reports** for analysis

### Key Metrics
- Command execution time (total)
- Database query time (per query and aggregate)
- External API call time (Discord, storage)
- Replay parsing time (multiprocessing overhead)
- Queue operations and matchmaking cycles
- Interaction response time (deferral to final response)

---

## 2. Architecture

### 2.1 Performance Context Manager

Create a reusable context manager for timing operations:

```python
# src/backend/services/performance_service.py

import time
import logging
from contextlib import contextmanager
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class PerformanceMetric:
    """Single performance measurement"""
    name: str
    duration_ms: float
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent: Optional[str] = None
    
@contextmanager
def measure_time(operation_name: str, metadata: Optional[Dict] = None):
    """
    Context manager to measure operation time.
    
    Usage:
        with measure_time("database_query", {"query": "SELECT * FROM players"}):
            result = db.query(...)
    """
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        log_performance_metric(operation_name, duration_ms, metadata or {})
```

### 2.2 Flow Tracker

Track complete user flows from start to finish:

```python
class FlowTracker:
    """Track complete user interaction flows"""
    
    def __init__(self, flow_name: str, user_id: int):
        self.flow_name = flow_name
        self.user_id = user_id
        self.start_time = time.perf_counter()
        self.checkpoints: List[PerformanceMetric] = []
        self.metadata: Dict[str, Any] = {}
        
    def checkpoint(self, name: str, metadata: Optional[Dict] = None):
        """Record a checkpoint in the flow"""
        current_time = time.perf_counter()
        duration_ms = (current_time - self.start_time) * 1000
        
        metric = PerformanceMetric(
            name=f"{self.flow_name}.{name}",
            duration_ms=duration_ms,
            timestamp=datetime.utcnow(),
            metadata=metadata or {},
            parent=self.flow_name
        )
        self.checkpoints.append(metric)
        
    def complete(self, status: str = "success"):
        """Mark flow as complete and log results"""
        total_duration = (time.perf_counter() - self.start_time) * 1000
        
        log_flow_completion(
            flow_name=self.flow_name,
            user_id=self.user_id,
            duration_ms=total_duration,
            checkpoints=self.checkpoints,
            status=status,
            metadata=self.metadata
        )
```

### 2.3 Database Query Interceptor

Wrap database queries to automatically measure time:

```python
class TimedDatabaseAdapter:
    """Wrapper around database adapter with performance tracking"""
    
    def __init__(self, adapter: DatabaseAdapter):
        self.adapter = adapter
        
    def execute_query(self, query: str, params: tuple = ()):
        with measure_time("db.query", {"query": query[:100]}):
            return self.adapter.execute_query(query, params)
    
    # Wrap all database methods similarly...
```

---

## 3. Implementation Strategy

### 3.1 Phase 1: Core Infrastructure (Week 1)

**Files to Create:**
- `src/backend/services/performance_service.py` - Core performance tracking
- `src/backend/db/adapters/timed_adapter.py` - Database query timing wrapper
- `src/backend/services/performance_logger.py` - Structured logging

**Deliverables:**
- Performance context manager
- Flow tracker class
- Database query timing
- Basic console logging

### 3.2 Phase 2: Command Integration (Week 2)

**Files to Modify:**
- All command files in `src/bot/commands/`
- `src/bot/bot_setup.py` - Global interaction timing

**Implementation:**

```python
# Example: src/bot/commands/queue_command.py

from src.backend.services.performance_service import FlowTracker

async def queue_command(interaction: discord.Interaction):
    flow = FlowTracker("queue_command", interaction.user.id)
    
    try:
        # Guard checks
        flow.checkpoint("guard_checks_start")
        player = guard_service.ensure_player_record(...)
        guard_service.require_queue_access(player)
        flow.checkpoint("guard_checks_complete")
        
        # Get preferences
        flow.checkpoint("load_preferences_start")
        user_preferences = db_reader.get_preferences_1v1(interaction.user.id)
        flow.checkpoint("load_preferences_complete")
        
        # Create view
        flow.checkpoint("create_view_start")
        view = await QueueView.create(...)
        flow.checkpoint("create_view_complete")
        
        # Send response
        flow.checkpoint("send_response_start")
        await send_ephemeral_response(interaction, embed=embed, view=view)
        flow.checkpoint("send_response_complete")
        
        flow.complete("success")
        
    except Exception as e:
        flow.complete("error")
        raise
```

### 3.3 Phase 3: Critical Path Optimization (Week 3)

**Focus Areas:**
1. **Setup Command** - Multi-step flow with dropdowns
2. **Queue Command** - Complex matchmaking flow
3. **Match Result Reporting** - Replay parsing and MMR calculation

**Measurements:**
- Time from interaction to first response
- Database query aggregation
- Replay parsing time (multiprocessing)
- MMR calculation time
- View rendering time

### 3.4 Phase 4: Reporting & Dashboards (Week 4)

**Create:**
- Performance summary script
- Daily/weekly reports
- Slow query alerts
- Performance regression detection

---

## 4. Metrics to Track

### 4.1 Command-Level Metrics

| Command | Key Metrics | Target SLA |
|---------|-------------|------------|
| `/setup` | Total flow time, dropdown rendering | <500ms initial |
| `/queue` | Queue join time, matchmaking cycle | <300ms initial |
| `/profile` | Data fetch + render time | <200ms |
| `/leaderboard` | Query + pagination time | <500ms |
| `/activate` | Code validation time | <200ms |
| `/setcountry` | Autocomplete + update time | <150ms |
| `/termsofservice` | Embed render time | <100ms |

### 4.2 Database Query Metrics

```python
# Track per-query type
- get_player_by_discord_uid: <10ms
- get_preferences_1v1: <15ms
- get_leaderboard_data: <100ms
- get_match_1v1: <20ms
- insert_match_result: <50ms
- update_player_mmr: <30ms
```

### 4.3 External Service Metrics

```python
- Discord interaction response: <2000ms (hard limit)
- Supabase storage upload: <1000ms
- Replay parsing (multiprocessing): <500ms
```

### 4.4 System Resource Metrics

```python
- Database connection pool utilization: <80%
- Process pool queue depth: <5
- Memory usage per worker: <500MB
- Active interaction count: Track concurrent
```

---

## 5. Logging Strategy

### 5.1 Log Levels

```python
# Performance logging levels
DEBUG: All operations >1ms
INFO: User flows, checkpoints
WARNING: Operations >500ms
ERROR: Operations >3000ms (interaction timeout risk)
CRITICAL: System resource exhaustion
```

### 5.2 Log Format

```python
{
    "timestamp": "2025-01-20T15:30:45.123Z",
    "level": "INFO",
    "type": "flow_complete",
    "flow_name": "queue_command",
    "user_id": 123456789,
    "duration_ms": 245.67,
    "checkpoints": [
        {"name": "guard_checks", "duration_ms": 12.34},
        {"name": "load_preferences", "duration_ms": 45.67},
        {"name": "create_view", "duration_ms": 23.45},
        {"name": "send_response", "duration_ms": 164.21}
    ],
    "status": "success",
    "metadata": {
        "command": "queue",
        "guild_id": null,
        "channel_id": 987654321
    }
}
```

### 5.3 Storage

**Development:**
- Console output with colored formatting
- Local file: `logs/performance_{date}.log`

**Production:**
- Structured JSON logs
- Log aggregation service (CloudWatch, Datadog, etc.)
- Database table for historical analysis

---

## 6. Performance Database Schema

```sql
-- Table for storing performance metrics
CREATE TABLE IF NOT EXISTS performance_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    flow_name VARCHAR(100) NOT NULL,
    operation_name VARCHAR(200) NOT NULL,
    duration_ms FLOAT NOT NULL,
    user_id BIGINT,
    status VARCHAR(20) DEFAULT 'success',
    metadata JSONB,
    parent_flow_id INTEGER REFERENCES performance_metrics(id),
    INDEX idx_flow_name (flow_name),
    INDEX idx_timestamp (timestamp),
    INDEX idx_duration (duration_ms)
);

-- Table for aggregated statistics
CREATE TABLE IF NOT EXISTS performance_stats (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    flow_name VARCHAR(100) NOT NULL,
    operation_name VARCHAR(200) NOT NULL,
    count INTEGER NOT NULL,
    avg_duration_ms FLOAT NOT NULL,
    min_duration_ms FLOAT NOT NULL,
    max_duration_ms FLOAT NOT NULL,
    p50_duration_ms FLOAT NOT NULL,
    p95_duration_ms FLOAT NOT NULL,
    p99_duration_ms FLOAT NOT NULL,
    UNIQUE(date, flow_name, operation_name)
);
```

---

## 7. Analysis & Reporting

### 7.1 Real-Time Monitoring

```python
# Example: Performance monitor service
class PerformanceMonitor:
    """Real-time performance monitoring"""
    
    def __init__(self):
        self.recent_metrics = []
        self.alert_thresholds = {
            "queue_command": 500,
            "setup_command": 1000,
            "profile_command": 300,
        }
    
    def check_performance(self, metric: PerformanceMetric):
        """Check if metric exceeds thresholds"""
        threshold = self.alert_thresholds.get(metric.name, 1000)
        
        if metric.duration_ms > threshold:
            self.alert_slow_operation(metric)
    
    def alert_slow_operation(self, metric: PerformanceMetric):
        """Alert on slow operations"""
        logger.warning(
            f"Slow operation detected: {metric.name} "
            f"took {metric.duration_ms:.2f}ms "
            f"(threshold: {self.alert_thresholds.get(metric.name)}ms)"
        )
```

### 7.2 Daily Reports

```python
# Generate daily performance summary
def generate_daily_report(date: datetime) -> str:
    """
    Generate daily performance report:
    - Total commands executed
    - Average response times per command
    - Slowest operations (top 10)
    - Resource utilization
    - Error rate
    """
    pass
```

### 7.3 Performance Regression Detection

```python
# Compare with historical baselines
def detect_regressions():
    """
    Compare current performance with 7-day average:
    - Alert if any metric >20% slower
    - Flag new slow queries
    - Track trend over time
    """
    pass
```

---

## 8. Integration Points

### 8.1 Global Interaction Wrapper

```python
# src/bot/bot_setup.py

class EvoLadderBot(commands.Bot):
    async def on_interaction(self, interaction: discord.Interaction):
        # Start timing
        interaction_start = time.perf_counter()
        
        # Existing logic...
        if interaction.type == discord.InteractionType.application_command:
            command_name = interaction.command.name if interaction.command else "unknown"
            
            # DM check...
            
            # Log command call...
            
        # Continue with command processing
        await super().on_interaction(interaction)
        
        # Log total interaction time
        duration_ms = (time.perf_counter() - interaction_start) * 1000
        log_interaction_time(command_name, duration_ms, interaction.user.id)
```

### 8.2 Database Adapter Integration

```python
# src/backend/db/db_reader_writer.py

class DatabaseReader:
    def __init__(self, adapter: DatabaseAdapter):
        # Wrap adapter with timing
        self.adapter = TimedDatabaseAdapter(adapter)
```

### 8.3 Matchmaking Service Integration

```python
# src/backend/services/matchmaking_service.py

class Matchmaker:
    async def run(self):
        while self.is_running:
            cycle_start = time.perf_counter()
            
            # Matchmaking logic...
            
            cycle_duration = (time.perf_counter() - cycle_start) * 1000
            log_matchmaking_cycle(cycle_duration, matches_made)
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

```python
# tests/backend/services/test_performance_service.py

def test_measure_time_context_manager():
    """Test basic timing functionality"""
    with measure_time("test_operation") as timer:
        time.sleep(0.1)
    
    assert timer.duration_ms >= 100
    assert timer.duration_ms < 120

def test_flow_tracker_checkpoints():
    """Test flow tracker checkpoint recording"""
    flow = FlowTracker("test_flow", 123)
    flow.checkpoint("step1")
    time.sleep(0.05)
    flow.checkpoint("step2")
    flow.complete()
    
    assert len(flow.checkpoints) == 2
    assert flow.checkpoints[1].duration_ms > flow.checkpoints[0].duration_ms
```

### 9.2 Integration Tests

```python
# tests/bot/test_command_performance.py

@pytest.mark.asyncio
async def test_queue_command_performance():
    """Ensure queue command stays under SLA"""
    # Mock interaction
    interaction = MockInteraction()
    
    start = time.perf_counter()
    await queue_command(interaction)
    duration_ms = (time.perf_counter() - start) * 1000
    
    assert duration_ms < 500, f"Queue command took {duration_ms}ms (SLA: 500ms)"
```

---

## 10. Alerting & Notifications

### 10.1 Alert Conditions

| Condition | Severity | Action |
|-----------|----------|--------|
| Any command >3000ms | CRITICAL | Page on-call engineer |
| Command >2x baseline | WARNING | Log to monitoring |
| DB query >500ms | WARNING | Review query optimization |
| Connection pool >90% | CRITICAL | Scale database connections |
| Process pool queue >10 | WARNING | Monitor worker health |

### 10.2 Notification Channels

- **Discord webhook** for critical alerts
- **Email** for daily summaries
- **Slack** for warning-level events
- **CloudWatch/Datadog** for metric tracking

---

## 11. Maintenance & Optimization

### 11.1 Weekly Review

- Review top 10 slowest operations
- Identify optimization opportunities
- Check for performance regressions
- Update baselines

### 11.2 Monthly Analysis

- Trend analysis (are things getting slower?)
- Capacity planning (connection pools, workers)
- User experience impact assessment
- Performance documentation updates

### 11.3 Continuous Optimization

```python
# Example: Automated optimization suggestions
def suggest_optimizations():
    """
    Analyze performance data and suggest:
    - Queries that need indexes
    - Commands that need caching
    - Flows that could be parallelized
    - Resources that need scaling
    """
    pass
```

---

## 12. Success Metrics

### 12.1 User Experience Goals

- **95% of commands** complete in <500ms
- **99% of commands** complete in <2000ms
- **0% interaction timeouts** (all <3000ms)
- **Database queries** average <50ms

### 12.2 System Health Goals

- **Connection pool** utilization <80%
- **Process pool** queue depth <5
- **Memory** usage per worker <500MB
- **No performance regressions** >10% over 7 days

---

## 13. Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Create `performance_service.py`
- [ ] Implement `measure_time` context manager
- [ ] Implement `FlowTracker` class
- [ ] Create `TimedDatabaseAdapter`
- [ ] Set up structured logging
- [ ] Create performance database tables

### Phase 2: Command Integration
- [ ] Add flow tracking to `/queue`
- [ ] Add flow tracking to `/setup`
- [ ] Add flow tracking to `/profile`
- [ ] Add flow tracking to `/leaderboard`
- [ ] Add flow tracking to `/activate`
- [ ] Add flow tracking to `/setcountry`
- [ ] Add flow tracking to `/termsofservice`

### Phase 3: Analysis & Reporting
- [ ] Implement daily report generation
- [ ] Set up alerting thresholds
- [ ] Create performance dashboard
- [ ] Implement regression detection

### Phase 4: Optimization
- [ ] Optimize slow queries identified
- [ ] Add caching where beneficial
- [ ] Tune connection pool settings
- [ ] Document performance best practices

---

## 14. Future Enhancements

- **Distributed tracing** (OpenTelemetry integration)
- **User-facing performance metrics** (show users their average wait times)
- **A/B testing framework** (compare performance of different implementations)
- **Automatic scaling triggers** (scale resources based on performance)
- **Performance budgets** (CI/CD fails if performance regresses)

---

## Conclusion

This performance monitoring system will provide comprehensive visibility into bot operation times, enabling:

1. **Proactive optimization** before users notice issues
2. **Data-driven decisions** about architecture and scaling
3. **Reliability improvements** through early bottleneck detection
4. **Better user experience** with consistently fast responses

The phased approach ensures we can start tracking quickly while building toward a comprehensive monitoring solution.

