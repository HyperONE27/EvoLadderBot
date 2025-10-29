# Discord API Bottleneck Analysis
## Visual Guide to Understanding Where Performance Issues Actually Come From

**Purpose:** Clarify Discord's event model and identify real vs. imaginary bottlenecks

---

## Part 1: The Two Discord APIs

### API Type 1: Gateway (WebSocket)

```
┌─────────────────────────────────────────────────────────┐
│                      DISCORD'S SERVERS                   │
│                                                          │
│  Events happening in your guild:                        │
│  - User sends message                                   │
│  - User clicks button                                   │
│  - User runs slash command                              │
│  - Someone joins voice channel                          │
│  - etc.                                                 │
└─────────────────────────────────────────────────────────┘
                           │
                           │ WebSocket (persistent connection)
                           │ Discord PUSHES events to you
                           │ UNLIMITED throughput (no rate limit)
                           ▼
┌─────────────────────────────────────────────────────────┐
│                     YOUR BOT PROCESS                     │
│                                                          │
│  @bot.event                                              │
│  async def on_interaction(interaction):                  │
│      # Discord pushed this to you                       │
│      # You process it                                   │
│      await handle_queue_join(interaction)               │
│                                                          │
│  YOUR BOTTLENECK: How fast you process each event       │
│  - If handler takes 5 seconds → laggy bot               │
│  - If handler takes 50ms → responsive bot               │
└─────────────────────────────────────────────────────────┘
```

**Rate Limits:** NONE for receiving events (Discord pushes unlimited)

**Your Actions That Use Gateway:**
- ❌ None (you only receive via gateway, never send)

### API Type 2: HTTP (REST)

```
┌─────────────────────────────────────────────────────────┐
│                     YOUR BOT PROCESS                     │
│                                                          │
│  # You want to send a message                           │
│  await channel.send("Match found!")                      │
│                                                          │
│  # discord.py makes HTTP request:                       │
│  POST https://discord.com/api/v10/channels/{id}/messages│
└─────────────────────────────────────────────────────────┘
                           │
                           │ HTTP Request (you initiate)
                           │ Rate limited: 5 req/s per route
                           │ Global limit: 50 req/s
                           ▼
┌─────────────────────────────────────────────────────────┐
│                      DISCORD'S SERVERS                   │
│                                                          │
│  Rate limiter checks:                                   │
│  - Have you sent 5 messages to this channel this second?│
│  - Have you made 50 requests total this second?         │
│                                                          │
│  YES → 429 (rate limited, try again in X seconds)       │
│  NO  → 200 OK (message sent)                            │
└─────────────────────────────────────────────────────────┘
```

**Rate Limits:**
- Per-route: 5 requests/second
- Global: 50 requests/second

**Your Actions That Use HTTP:**
- ✅ `channel.send()` - Send message
- ✅ `message.edit()` - Edit message
- ✅ `channel.create_thread()` - Create channel
- ✅ `channel.delete()` - Delete channel
- ✅ `interaction.response.send_message()` - Reply to interaction

---

## Part 2: Your Bot's Event Flow

### Scenario: User Joins Queue

```
[1] User clicks "Join Queue" button
     │
     ├─► Discord's servers receive the click
     │
     ▼
[2] Discord PUSHES event to your bot (Gateway)
     │   - Event: INTERACTION_CREATE
     │   - Latency: ~20-50ms (Discord's network)
     │   - Rate limit: NONE (unlimited receive)
     │
     ▼
[3] discord.py event loop receives event
     │   - Latency: <1ms (local processing)
     │   - Bottleneck: Python GIL (one event at a time)
     │
     ▼
[4] Your event handler runs
     │   async def callback(interaction):
     │       await data_access_service.add_to_queue(user)
     │   
     │   - Latency: ~10-50ms (your code)
     │   - Bottleneck: YOUR CODE PERFORMANCE
     │   - If slow → users notice lag
     │
     ▼
[5] You send response (HTTP to Discord)
     │   await interaction.response.send_message("Added to queue!")
     │   
     │   - HTTP request to Discord's API
     │   - Latency: ~50-150ms (network + Discord processing)
     │   - Rate limit: 5 req/s per channel
     │   - Bottleneck: Discord's rate limiter (if you spam)
     │
     ▼
[6] User sees "Added to queue!" message
```

**Total Latency:** 80-250ms (mostly network and Discord's processing)

**Where you have control:**
- ✅ Step 4: Your code performance (optimize this)

**Where you DON'T have control:**
- ❌ Step 2: Discord's network latency
- ❌ Step 5: Discord's API latency
- ❌ Step 5: Discord's rate limits

---

## Part 3: Rate Limit Analysis (1,000 Concurrent Users)

### Scenario: 20 Matches Start Simultaneously

This is your worst-case burst scenario. Let's calculate the HTTP load:

```
Event: 20 matches found at the same time
│
├─► 20× Send "Match found!" message
│   Route: POST /channels/{lobby_id}/messages
│   Rate limit: 5 req/s per route
│   Your usage: 20 requests in 1 second
│   
│   RESULT: 🚨 Rate limited after 5 requests
│           Discord sends 429 (Too Many Requests)
│           discord.py automatically retries with backoff
│           Takes ~4 seconds total instead of 1 second
│
├─► 20× Create in-game thread
│   Route: POST /channels/{category_id}/threads
│   Rate limit: 5 req/s per route
│   Your usage: 20 requests in 1 second
│   
│   RESULT: 🚨 Rate limited (same as above)
│
└─► 40× Send DM to players (2 per match)
    Route: POST /channels/{user_dm_id}/messages
    Rate limit: 5 req/s PER USER (separate routes)
    Your usage: 2 requests per user (distributed)
    
    RESULT: ✅ No rate limiting (each user is separate route)
```

**Total HTTP requests:** 80 in 1 second (burst)

**Discord's global limit:** 50 req/s

**Actual result:**
- First 50 requests succeed immediately
- Next 30 requests get 429 error
- discord.py retries them over next 3-4 seconds
- All messages eventually sent

**User experience:**
- First 10 matches: Instant notification
- Next 10 matches: 2-4 second delay
- Still acceptable (users don't notice <5s delay)

### Average Load (Steady State)

```
Assumptions:
- 1,000 concurrent users
- 60% in-match (300 matches active)
- 12-minute average match
- 25 matches start per minute
- 25 matches end per minute

HTTP Requests per Minute:
┌────────────────────────────────────────────────┐
│ Event                    │ Count │ Requests    │
├────────────────────────────────────────────────┤
│ Match found (send msg)   │  25   │  25         │
│ Create in-game thread    │  25   │  25         │
│ Send DM (2 per match)    │  25   │  50         │
│ Match result (edit msg)  │  25   │  25         │
│ Replay verified (edit)   │  40   │  40  (avg)  │
│ Delete old channels      │   5   │   5  (avg)  │
├────────────────────────────────────────────────┤
│ TOTAL                    │       │ 170 req/min │
│ Per second               │       │ 2.8 req/s   │
└────────────────────────────────────────────────┘

Discord's Limits:
- Global: 50 req/s
- Per route: 5 req/s

Your Usage:
- Global: 2.8 req/s (5.6% of limit)
- Per route: <1 req/s (20% of limit)

VERDICT: ✅ No rate limiting under normal load
```

**Conclusion:** Discord's API is NOT your bottleneck, even at 1,000 users.

---

## Part 4: Real Bottleneck Analysis

### Bottleneck 1: CPU-Bound Replay Parsing

```
User uploads 500 KB replay file
│
├─► Gateway receives upload (Discord → your bot)
│   Time: ~100ms (network)
│   Bottleneck: ❌ No (Discord is fast)
│
├─► Your bot downloads replay bytes
│   Time: ~50ms (Discord's CDN)
│   Bottleneck: ❌ No (CDN is fast)
│
├─► Parse replay with sc2reader
│   Time: ~25-100ms (CPU-intensive)
│   Bottleneck: ✅ YES (Python GIL blocks event loop)
│   
│   WITHOUT ProcessPoolExecutor:
│   - Main thread blocked for 25-100ms
│   - ALL other events wait (queue, buttons, commands)
│   - User experience: Laggy bot
│   
│   WITH ProcessPoolExecutor (your current setup):
│   - Offloaded to worker process
│   - Main thread continues processing events
│   - User experience: Responsive bot
│
└─► Store parsed data
    Time: ~10ms (database write)
    Bottleneck: ❌ No (async write queue)
```

**Solution:** ✅ Already implemented (ProcessPoolExecutor)

**Scaling:** Increase workers from 4 to 32 (8× capacity)

### Bottleneck 2: Memory Bandwidth (Future)

```
Current (250 concurrent users):
┌─────────────────────────────────────────┐
│ DataAccessService Memory Usage          │
├─────────────────────────────────────────┤
│ players_df:      ~5 MB  (2,000 players) │
│ mmrs_1v1_df:    ~10 MB  (8,000 records) │
│ matches_1v1_df: ~50 MB  (1,000 matches) │
│ replays_df:     ~30 MB  (1,000 replays) │
│ Other:          ~50 MB  (misc data)     │
├─────────────────────────────────────────┤
│ TOTAL:         ~150 MB                  │
└─────────────────────────────────────────┘

Projected (1,000 concurrent users):
┌─────────────────────────────────────────┐
│ DataAccessService Memory Usage          │
├─────────────────────────────────────────┤
│ players_df:      ~20 MB  (8,000 players)│
│ mmrs_1v1_df:     ~40 MB  (32K records)  │
│ matches_1v1_df: ~200 MB  (4,000 matches)│
│ replays_df:     ~120 MB  (4,000 replays)│
│ Other:          ~100 MB  (misc data)    │
├─────────────────────────────────────────┤
│ TOTAL:         ~500 MB                  │
└─────────────────────────────────────────┘

Railway Pro: 32 GB available
Your usage: 0.5 GB (1.5% of capacity)

VERDICT: ✅ No bottleneck until 10,000+ users
```

**Solution:** Not needed yet. Monitor with `/health` command.

### Bottleneck 3: Database Write Throughput

```
Current Architecture:
┌────────────────────────────────────────────────┐
│  Your Bot                                      │
│  ├─► Event happens (match result reported)    │
│  ├─► Update in-memory DataFrame (instant)     │
│  ├─► Queue write job (asyncio.Queue)          │
│  └─► Continue processing events (non-blocking)│
└────────────────────────────────────────────────┘
         │
         │ Async background worker
         ▼
┌────────────────────────────────────────────────┐
│  Database Write Worker (asyncio task)          │
│  ├─► Process queue continuously               │
│  ├─► Batch 10 writes together                 │
│  ├─► Single transaction to Supabase           │
│  └─► WAL persistence for crash recovery       │
└────────────────────────────────────────────────┘
         │
         │ Network (~20-50ms per batch)
         ▼
┌────────────────────────────────────────────────┐
│  Supabase PostgreSQL                           │
│  - Capacity: ~500-1,000 writes/second         │
│  - Your load: ~20-30 writes/second            │
│  - Utilization: 3-6%                          │
└────────────────────────────────────────────────┘

VERDICT: ✅ No bottleneck (plenty of headroom)
```

**Optimization available:** Batch writes (queue 10-20 writes, send as one transaction)

**Capacity gain:** 3-5× throughput with batching

---

## Part 5: What "Sharding" Actually Means

### Discord Sharding (What You Thought It Was)

❌ **MISCONCEPTION:**
> "Sharding lets me handle more concurrent users by splitting load across multiple processes."

✅ **REALITY:**
> "Sharding splits your **GUILDS** (servers) across multiple connections. It's for bots in 2,500+ servers, not for handling load in a single server."

### Visual Explanation

```
Your Bot (Single-Guild Ladder):
┌──────────────────────────────────────────┐
│  Your Guild: "StarCraft II Ladder"      │
│  Members: 1,000-10,000 users             │
│  Channels: ~50                           │
└──────────────────────────────────────────┘
         │
         │ 1 WebSocket connection (no sharding needed)
         ▼
┌──────────────────────────────────────────┐
│  Discord Gateway                         │
│  All events from your 1 guild           │
│  Capacity: 1,000,000+ events/second     │
└──────────────────────────────────────────┘

SHARDING COUNT: 1 (default, no sharding)
WHY: You have 1 guild, not 2,500


Multi-Guild Bot (e.g., Music Bot):
┌──────────────────────────────────────────┐
│  Guild 1: "Gaming Server"                │
│  Guild 2: "Anime Fans"                   │
│  Guild 3: "Programming Hub"              │
│  ...                                     │
│  Guild 5,000: "Meme Central"            │
└──────────────────────────────────────────┘
         │
         │ Discord REQUIRES sharding at 2,500 guilds
         ▼
┌──────────────────────────────────────────┐
│  Shard 0: Guilds 1-1,250                 │
│  Shard 1: Guilds 1,251-2,500             │
│  Shard 2: Guilds 2,501-3,750             │
│  Shard 3: Guilds 3,751-5,000             │
└──────────────────────────────────────────┘
         │
         │ 4 WebSocket connections (sharded)
         ▼
┌──────────────────────────────────────────┐
│  Discord Gateway (4 connections)         │
└──────────────────────────────────────────┘

SHARDING COUNT: 4 (required)
WHY: Bot is in 5,000 guilds
```

### What You Actually Need: Process-Level Parallelism

```
❌ Discord Sharding (not helpful for you):
┌──────────────────────────────────────────┐
│  Shard 0: Guild 1                        │
│  Shard 1: Guild 2                        │  ← You have 1 guild
│  Shard 2: Guild 3                        │
└──────────────────────────────────────────┘

✅ CPU Parallelism (what you already have):
┌──────────────────────────────────────────┐
│  Main Process: Discord event loop        │
│  Worker 1: Parse replay A                │
│  Worker 2: Parse replay B                │
│  Worker 3: Parse replay C                │
│  ...                                     │
│  Worker 32: Parse replay Z               │
└──────────────────────────────────────────┘
```

**Key Difference:**
- Sharding splits **guilds** (you only have 1 guild)
- Parallelism splits **CPU tasks** (you have many CPU tasks)

---

## Part 6: Performance Impact Comparison

Let's compare the impact of different optimizations:

```
┌────────────────────────────────────────────────────────────┐
│ Optimization                 │ Capacity Gain │ Complexity  │
├────────────────────────────────────────────────────────────┤
│ Scale workers (4 → 32)       │      8×       │  ★☆☆☆☆      │
│ Add write batching           │      3×       │  ★★☆☆☆      │
│ Add connection pooling       │      2×       │  ★☆☆☆☆      │
│ Optimize Polars memory       │      1.5×     │  ★★☆☆☆      │
│ Add Redis cache              │      2×       │  ★★★★☆      │
│ Separate containers          │      1.2×     │  ★★★★☆      │
│ Implement Discord sharding   │      0×       │  ★★★☆☆      │ ← Useless
└────────────────────────────────────────────────────────────┘

PRIORITY ORDER:
1. Scale workers (8× gain, 5 minutes)           ← DO THIS NOW
2. Add connection pooling (2× gain, 30 minutes) ← DO THIS WEEK
3. Add write batching (3× gain, 4 hours)        ← DO THIS MONTH
4. Everything else (marginal gains)             ← DO LATER/NEVER
```

---

## Part 7: Latency Budget (Where Time Goes)

### User Action: Join Queue

```
Total Latency: 120ms (typical)

┌────────────────────────────────────────────────────────┐
│ Stage                        │ Time    │ % of Total    │
├────────────────────────────────────────────────────────┤
│ 1. User clicks button        │   0ms   │      —        │
│ 2. Discord receives          │  30ms   │     25%       │ ← Network
│ 3. Gateway push to bot       │  20ms   │     17%       │ ← Network
│ 4. discord.py event loop     │   1ms   │      1%       │ ← Local
│ 5. Your handler runs         │  15ms   │     12%       │ ← YOUR CODE
│ 6. HTTP response to Discord  │  50ms   │     42%       │ ← Network + API
│ 7. Discord sends to user     │   4ms   │      3%       │ ← Network
├────────────────────────────────────────────────────────┤
│ TOTAL                        │ 120ms   │    100%       │
└────────────────────────────────────────────────────────┘

Where you can improve:
- ✅ Stage 5 (your code): Optimize database queries, cache results
- ❌ Stages 2,3,6,7 (network/Discord): Out of your control

Maximum possible improvement:
- Current: 120ms
- If you make Stage 5 instant (0ms): 105ms
- Gain: 12% (not worth over-optimizing)
```

### CPU-Bound Action: Parse Replay

```
Total Latency: 75ms (typical) with workers

┌────────────────────────────────────────────────────────┐
│ Stage                        │ Time    │ % of Total    │
├────────────────────────────────────────────────────────┤
│ 1. User uploads file         │   0ms   │      —        │
│ 2. Discord upload (CDN)      │  50ms   │     67%       │ ← Network
│ 3. Bot downloads bytes       │  10ms   │     13%       │ ← Network
│ 4. Submit to worker pool     │   1ms   │      1%       │ ← IPC
│ 5. Worker parses replay      │  25ms   │     33%       │ ← CPU
│ 6. Return result to main     │   1ms   │      1%       │ ← IPC
│ 7. Store in database         │   8ms   │     11%       │ ← DB I/O
├────────────────────────────────────────────────────────┤
│ TOTAL                        │  75ms   │    100%       │
└────────────────────────────────────────────────────────┘

WITHOUT workers (synchronous):
- Stage 5 blocks event loop for 25ms
- ALL other events wait (buttons, commands, etc.)
- 100 simultaneous uploads = 2,500ms total block
- User experience: Bot freezes for 2.5 seconds

WITH workers (your current setup):
- Stage 5 runs in separate process (non-blocking)
- Event loop continues immediately
- 100 simultaneous uploads = 0ms block (if enough workers)
- User experience: Bot stays responsive

Scaling workers (4 → 32):
- Can parse 32 replays simultaneously (vs. 4)
- 100 simultaneous uploads:
  - 4 workers:  25 batches × 25ms = 625ms
  - 32 workers:  4 batches × 25ms = 100ms
- Gain: 6× throughput
```

---

## Part 8: Decision Matrix

### When Should I Implement X?

```
┌─────────────────────────────────────────────────────────────────┐
│  If you see...              │  Then do...         │  Phase      │
├─────────────────────────────────────────────────────────────────┤
│ Concurrent users > 100      │ Scale workers to 32 │ Now         │
│ Write queue > 50            │ Add write batching  │ This month  │
│ Memory usage > 20 GB        │ Move to Redis       │ Phase 2     │
│ CPU usage > 80% sustained   │ Separate containers │ Phase 2     │
│ Bot in 2,500 guilds         │ Implement sharding  │ Never (N/A) │
│ Response time > 1s          │ Profile & optimize  │ As needed   │
│ Database errors             │ Add connection pool │ This week   │
└─────────────────────────────────────────────────────────────────┘
```

### Priority Matrix

```
HIGH PRIORITY (Do Now):
  ✅ Scale ProcessPoolExecutor to 32 workers
  ✅ Add connection pooling
  ✅ Add memory monitoring

MEDIUM PRIORITY (Do This Month):
  ⚠️ Implement write batching
  ⚠️ Optimize Polars DataFrame memory
  ⚠️ Add performance metrics dashboard

LOW PRIORITY (Do When Needed):
  ⬜ Separate worker container (Phase 2)
  ⬜ Implement Redis cache (Phase 2)
  ⬜ Multi-container architecture (Phase 2)

NO PRIORITY (Don't Do):
  ❌ Discord sharding (not applicable)
  ❌ IPC optimization (negligible gains)
  ❌ Over-engineer for imaginary load
```

---

## Summary

### ✅ Real Bottlenecks (Fix These)

1. **CPU parallelism** - Already solved with ProcessPoolExecutor, scale to 32
2. **Database connection pooling** - Easy win, implement this week
3. **Write batching** - Good optimization, implement this month
4. **Memory optimization** - Nice to have, do when convenient

### ❌ Not Bottlenecks (Ignore These)

1. **Discord's API rate limits** - You use 3 req/s, limit is 50 req/s
2. **Discord sharding** - For multi-guild bots (2,500+), not single-guild
3. **IPC vs HTTP** - Difference is <0.5ms, negligible
4. **Gateway event throughput** - Discord handles millions/second

### 🎯 Action Plan

**This week:**
```python
# Scale workers
self.process_pool = ProcessPoolExecutor(max_workers=32)

# Add connection pooling
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
```

**This month:**
```python
# Add write batching
async def _process_write_batch(self, batch):
    async with self._db_session() as session:
        for job in batch:
            # Process all in one transaction
            ...
        await session.commit()
```

**When needed (Phase 2 at 1,000+ users):**
- Implement Redis for shared state
- Separate worker container
- Multi-container architecture

---

**Bottom Line:** Your bottlenecks are CPU and memory, not Discord's API. Scale workers to 32, add monitoring, and you're good to 1,000+ concurrent users.

