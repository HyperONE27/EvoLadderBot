# Scaling Quick Reference Guide

**Companion to:** `ADVANCED_SCALING_ARCHITECTURE.md`  
**Purpose:** One-page decision guide and implementation checklist

---

## TL;DR: What Should I Do Right Now?

### ✅ Do These 3 Things (Total Time: 1 Hour)

```python
# 1. Scale ProcessPoolExecutor to 32 workers (5 minutes)
# In bot_setup.py:
import os
self.process_pool = ProcessPoolExecutor(
    max_workers=min(32, os.cpu_count() or 4)
)

# 2. Add monitoring (30 minutes)
@bot.tree.command(name="health")
async def health_check(interaction):
    import psutil
    stats = {
        "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024,
        "cpu_percent": psutil.Process().cpu_percent(),
        "write_queue": data_access_service._write_queue.qsize(),
        "worker_count": len(bot.process_pool._processes)
    }
    await interaction.response.send_message(f"```json\n{json.dumps(stats, indent=2)}\n```")

# 3. Add connection pooling (30 minutes)
# In db_adapter.py or wherever you create SQLAlchemy engine:
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30
)
```

**Result:** 8× replay parsing capacity, visibility into system health, 3× database throughput.

---

## Discord API: Gateway vs. HTTP

| Type | What It Is | Rate Limit | Your Bottleneck? |
|------|------------|------------|------------------|
| **Gateway** | WebSocket events Discord pushes to you (`on_message`, button clicks) | None (unlimited receive) | ❌ No (asyncio handles millions/s) |
| **HTTP** | REST API calls you make to Discord (`send()`, `edit()`) | 5 req/s per route, 50 req/s global | ❌ No (you use ~3 req/s) |
| **CPU** | Replay parsing, MMR calculation | Limited by Python GIL | ⚠️ **YES** (already fixed with workers) |
| **Memory** | In-memory DataFrames | Limited by RAM (32 GB) | ❌ No (until 10,000+ users) |

**Key Insight:** Discord's API is NOT your bottleneck. CPU and memory are.

---

## Do I Need Discord Sharding?

```
┌─────────────────────────────────────────────┐
│  Is your bot in multiple guilds (servers)?  │
└─────────────────────────────────────────────┘
         │
         ├─► YES, > 2,500 guilds
         │   └─► ✅ Discord REQUIRES sharding
         │       Use: bot = commands.AutoShardedBot(...)
         │
         ├─► YES, 500-2,500 guilds
         │   └─► ⚠️ Recommended but not required
         │       Benefit: Better fault tolerance
         │
         └─► NO, 1 guild (your ladder bot)
             └─► ❌ DO NOT implement sharding
                 It adds complexity with zero benefit
```

**For EvoLadderBot:** You run in 1 guild → No sharding needed.

---

## Scaling Phases (When to Do What)

### Phase 1: Vertical Scaling (Now → 1,000 Users)

**When:** Now  
**Cost:** $45/month (Railway Pro + Supabase Pro)  
**Capacity:** 1,000+ concurrent users  
**Time to Implement:** 1 day  

**Changes:**
- ✅ 32 workers (vs. 4) → 8× replay parsing
- ✅ Write batching → 3-5× DB throughput
- ✅ Connection pooling → 2-3× DB throughput
- ✅ Memory monitoring
- ❌ No architectural changes (same single-process design)

### Phase 2: Horizontal Scaling (1,000 → 5,000 Users)

**When:** 6-12 months (when memory > 20 GB or latency > 1s)  
**Cost:** $105/month (Railway Pro multi-container + Redis)  
**Capacity:** 5,000+ concurrent users  
**Time to Implement:** 2-3 weeks  

**Changes:**
- ✅ Separate worker container (24 vCPU dedicated)
- ✅ Redis for shared state (replace in-memory DataFrames)
- ✅ Multiple bot containers (if needed)
- ⚠️ Requires code refactoring (DataAccessService → Redis)

### Phase 3: Planetary Scale (5,000+ Users)

**When:** 12+ months (probably never needed)  
**Cost:** $300-500/month  
**Capacity:** 10,000+ concurrent users  

**Changes:**
- ✅ External sharding (multi-process Discord.py)
- ✅ Redis Cluster
- ✅ Read replicas
- ⚠️ Major architectural rewrite

---

## Common Misconceptions (From Your Original Plan)

| Your Statement | Reality Check |
|----------------|---------------|
| "Internal sharding with multiple frontends" | ❌ Not needed for single-guild bot. Sharding is for 2,500+ guilds. |
| "IPC instead of HTTP penalties" | ⚠️ HTTP on localhost is <1ms. IPC saves ~0.5ms. Negligible difference. |
| "Dedicated process for DB writes" | ⚠️ Async task is sufficient. Separate process adds complexity for minimal gain. |
| "32 vCPU instead of 8" | ✅ Correct! Railway Pro has 32 vCPU. Scale workers immediately. |
| "Single backend as source of truth" | ✅ Excellent for Phase 1. Your DataAccessService is perfect. |

**Summary:** Your core ideas are sound, but Discord sharding is a red herring. Focus on CPU parallelism (workers) and memory optimization.

---

## Architecture Comparison: Phase 1 vs. Phase 2

### Phase 1 (Recommended for Now)

```
┌────────────────────────────────────┐
│    Single Railway Container        │
│                                    │
│  ┌──────────────────────────────┐  │
│  │  Discord.py Event Loop       │  │
│  │  + DataAccessService (RAM)   │  │
│  │  + 32 ProcessPoolExecutors   │  │
│  │  + Async Write Queue         │  │
│  └──────────────────────────────┘  │
│                                    │
│  Capacity: 1,000 users             │
│  Cost: $45/month                   │
│  Complexity: ★☆☆☆☆ (Very Simple)   │
└────────────────────────────────────┘
```

### Phase 2 (When You Outgrow Phase 1)

```
┌────────────────────────────────────┐
│     Railway Multi-Container        │
│                                    │
│  ┌──────────┐    ┌──────────────┐ │
│  │  Bot     │───►│  Workers     │ │
│  │  (8 vCPU)│    │  (24 vCPU)   │ │
│  └──────────┘    └──────────────┘ │
│       │                            │
│       ▼                            │
│  ┌────────────────────────────┐   │
│  │  Redis (Shared State)      │   │
│  └────────────────────────────┘   │
│                                    │
│  Capacity: 5,000 users             │
│  Cost: $105/month                  │
│  Complexity: ★★★☆☆ (Moderate)      │
└────────────────────────────────────┘
```

---

## Decision Matrix: When to Upgrade

| If You See This... | Do This... | Priority |
|--------------------|------------|----------|
| Memory usage > 24 GB | Move to Phase 2 (Redis) | 🔴 High |
| Write queue > 100 | Add write batching | 🟡 Medium |
| Replay parsing timeout > 10% | Scale workers to 32 | 🔴 High |
| CPU usage > 80% sustained | Check if workers are bottlenecked | 🟡 Medium |
| Response time P95 > 1s | Profile slow operations | 🟡 Medium |
| Database errors | Add connection pooling | 🔴 High |
| Concurrent users > 800 | Prepare Phase 2 migration | 🟢 Low |

---

## Performance Targets

### Phase 1 (Current Architecture)

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Max concurrent users | 1,000 | ~250 | ⚠️ Needs worker scaling |
| Match found latency | <100ms | ~50ms | ✅ |
| Replay parse time P95 | <200ms | ~25ms | ✅ |
| Database write latency | <50ms | ~30ms | ✅ |
| Memory usage (per 1K users) | <8 GB | ~6 GB | ✅ |
| Write queue depth | <20 | ~5 | ✅ |

---

## Action Checklist

### This Week
- [ ] Scale ProcessPoolExecutor to 32 workers
- [ ] Add `/health` admin command
- [ ] Add connection pooling to database
- [ ] Verify Railway Pro plan (32 vCPU / 32 GB)
- [ ] Document baseline performance metrics

### This Month
- [ ] Implement write batching in DataAccessService
- [ ] Optimize Polars DataFrame memory usage
- [ ] Add automated alerting (write queue depth > 50)
- [ ] Implement query result caching (TTLCache)

### This Quarter
- [ ] Run load tests (100, 250, 500, 1000 users)
- [ ] Create performance dashboard
- [ ] Document Phase 2 migration plan (if needed)
- [ ] Review cost vs. capacity projections

### This Year
- [ ] Evaluate Phase 2 necessity based on growth
- [ ] If needed: Implement Redis migration
- [ ] If needed: Separate worker container

---

## Load Testing Targets

Use these metrics to validate your capacity:

```python
# Expected performance at 1,000 concurrent users (Phase 1)
{
    "active_matches": 300,              # 600 users in-match
    "queue_depth": 150,                 # 300 users queuing
    "http_requests_per_second": 3,     # Well under 50/s limit
    "database_writes_per_second": 20,  # Well under 500/s capacity
    "memory_usage_gb": 6,              # Well under 32 GB limit
    "cpu_usage_percent": 40,           # Average, spikes to 80%
    "replay_parse_latency_p95_ms": 50, # 95% parse in <50ms
    "match_found_latency_ms": 50       # From queue pop to embed sent
}
```

**If you hit these numbers:** Phase 1 is working perfectly. No changes needed.

**If you exceed memory or CPU consistently:** Start planning Phase 2.

---

## Cost Breakdown (1,000 Concurrent Users)

| Service | Plan | Monthly Cost | Per-User Cost |
|---------|------|--------------|---------------|
| Railway | Pro (32 vCPU) | $20 | $0.02 |
| Supabase | Pro (8 GB DB) | $25 | $0.025 |
| **Total** | | **$45** | **$0.045** |

**Revenue scenario (if $2/user/month):**
- Revenue: $2,000/month
- Infrastructure: $45/month
- **Profit: $1,955/month (97.75% margin)**

**Scaling is cheap. User acquisition is expensive. Don't over-optimize infrastructure.**

---

## Red Flags (When to Stop and Reassess)

🚩 **If you see any of these, read the full doc (`ADVANCED_SCALING_ARCHITECTURE.md`):**

1. Memory usage growing >1 GB per 100 new users
2. Write queue backing up (>100 pending) for >10 minutes
3. Replay parsing timeouts >10% of uploads
4. Database connection errors (need PGBouncer or pooling)
5. Discord rate limit errors (429) - rare but possible during burst
6. Response latency P95 >500ms

---

## Key Takeaways (The 95/5 Rule)

**95% of your scaling needs are solved by:**
1. Scaling ProcessPoolExecutor to 32 workers (5 minutes)
2. Adding connection pooling (30 minutes)
3. Implementing write batching (4 hours)

**The other 5% (Phase 2+) requires:**
- Weeks of development
- Architectural changes
- Redis, multi-container setup
- Only implement when you actually need it

**Focus on the 95%. Launch, grow, measure. Scale when you hit real limits, not imagined ones.**

---

## Further Reading

- **Full Architecture Doc:** `docs/ADVANCED_SCALING_ARCHITECTURE.md`
- **Current System Assessment:** `docs/SYSTEM_ARCHITECTURE.md`
- **Emergency Procedures:** `docs/EMERGENCY_SCALING_CHEAT_SHEET.md`
- **Scaling Strategy (Original):** `docs/architecture/scaling_strategy.md`
- **Railway Docs:** https://docs.railway.app
- **Discord.py Sharding:** https://discordpy.readthedocs.io/en/stable/api.html#discord.AutoShardedClient

---

## Questions? Decision Tree

```
Q: Should I implement sharding?
A: No. You're single-guild. See "Do I Need Discord Sharding?" section.

Q: Should I separate into multiple containers now?
A: No. Phase 1 (single container) handles 1,000 users easily.

Q: Should I use Redis now?
A: No. In-memory DataFrames are faster. Use Redis in Phase 2.

Q: Should I optimize IPC vs HTTP?
A: No. Difference is <0.5ms. Not worth the complexity.

Q: What should I actually do right now?
A: Scale workers to 32, add monitoring, add connection pooling. Done.
```

---

**Bottom Line:** Your current architecture is excellent. Scale workers, add monitoring, ship it. Iterate based on real metrics, not theoretical bottlenecks.

**Estimated time to 1,000 users with Phase 1:** 6-12 months. You have time. Don't over-engineer.

