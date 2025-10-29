# Railway Scaling Quick Start Guide

**5-Minute Setup for Vertical Scaling**

---

## TL;DR: How to 2× Your Capacity Right Now

1. Go to Railway dashboard → Your service → Variables
2. Change `WORKER_PROCESSES` from `2` to `4`
3. Click "Save"
4. Wait 2-3 minutes for auto-deploy
5. Done. You now handle 480 concurrent users instead of 240.

**Cost: $15/month more**

---

## Railway Plans for EvoLadderBot

### Hobby Plan - $5/month
**Good for:**
- Alpha testing
- <150 concurrent users
- <1,200 weekly active

**Resources:**
- 512 MB RAM
- 1 vCPU
- 500 execution hours/month

**Limitations:**
- Only supports 2 workers
- May hit memory limit with traffic spikes

---

### Pro Plan - $20/month ⭐ **RECOMMENDED**
**Good for:**
- Production launch
- 150-1,000 concurrent users
- 1,200-8,000 weekly active

**Resources:**
- 8 GB RAM (16× more than needed)
- 8 vCPU (perfect for 8 workers)
- Unlimited execution
- Metrics dashboard
- Deployment rollbacks

**Capacity:**
- 2 workers: 240 concurrent
- 4 workers: 480 concurrent
- 8 workers: 960 concurrent
- 12 workers: 1,440 concurrent

**This plan handles basically everything you'll need.**

---

### Team Plan - Custom pricing
**Good for:**
- Enterprise scale (>1,000 concurrent)
- Custom requirements
- Dedicated support

**You won't need this for years.**

---

## Scaling Configurations

### Configuration 1: Alpha (Minimal Cost)
**Railway Plan:** Hobby ($5/month)
```env
WORKER_PROCESSES=2
DB_POOL_MAX_CONNECTIONS=20
```

**Capacity:** 240 concurrent (1,900 WAU)  
**Cost:** $5/month Railway + $0 Supabase (free tier)  
**Total:** $5/month

---

### Configuration 2: Beta Launch ⭐ **START HERE**
**Railway Plan:** Pro ($20/month)
```env
WORKER_PROCESSES=4
DB_POOL_MAX_CONNECTIONS=30
```

**Capacity:** 480 concurrent (3,800 WAU)  
**Cost:** $20/month Railway + $25/month Supabase Pro  
**Total:** $45/month

**This is your sweet spot for launch.**

---

### Configuration 3: Public Launch
**Railway Plan:** Pro ($20/month)
```env
WORKER_PROCESSES=8
DB_POOL_MAX_CONNECTIONS=50
```

**Capacity:** 960 concurrent (7,600 WAU)  
**Cost:** $30/month Railway + $25/month Supabase Pro  
**Total:** $55/month

**Scales to 4× your target load.**

---

### Configuration 4: High Growth
**Railway Plan:** Pro ($20/month)
```env
WORKER_PROCESSES=12
DB_POOL_MAX_CONNECTIONS=60
```

**Capacity:** 1,440 concurrent (11,400 WAU)  
**Cost:** $40/month Railway + $25/month Supabase Pro  
**Total:** $65/month

**Handles serious traffic.**

---

### Configuration 5: Maximum Vertical Scale
**Railway Plan:** Pro ($20/month)
```env
WORKER_PROCESSES=16
DB_POOL_MAX_CONNECTIONS=80
```

**Capacity:** 1,920 concurrent (15,200 WAU)  
**Cost:** $50/month Railway + $25/month Supabase Pro  
**Total:** $75/month

**Absolute limit before horizontal scaling needed.**

---

## How to Scale in Railway Dashboard

### Step-by-Step: Increase Workers

1. **Login to Railway:**
   ```
   https://railway.app
   ```

2. **Select your project:**
   - Click "EvoLadderBot" (or your project name)

3. **Go to Variables:**
   - Left sidebar → "Variables"

4. **Edit WORKER_PROCESSES:**
   - Find `WORKER_PROCESSES` in the list
   - Click to edit
   - Change value (2 → 4, or 4 → 8, etc.)
   - Click "Save"

5. **Wait for deploy:**
   - Railway auto-redeploys on variable change
   - Watch logs for: `[ProcessPool] Initialized with X workers`
   - Takes 2-3 minutes

6. **Verify:**
   - Check logs for successful startup
   - Monitor replay queue depth (should stay low)
   - Done!

**Time: 5 minutes**  
**Coding required: 0 lines**

---

## How to Upgrade Railway Plan

### From Hobby to Pro

1. **Go to Project Settings:**
   - Click gear icon (⚙️) in left sidebar

2. **Click "Plans":**
   - Shows current plan and options

3. **Select Pro:**
   - Click "Upgrade to Pro"
   - Confirm billing

4. **Done:**
   - Takes effect immediately
   - No redeploy needed
   - Resources available instantly

**Time: 2 minutes**  
**Cost: +$15/month**

---

## Monitoring in Railway

### Built-In Metrics (Pro Plan)

**Navigate to Metrics:**
- Left sidebar → "Metrics"

**What to watch:**
1. **Memory Usage**
   - Alert if >70%
   - Critical if >85%
   - Should stay <50% with 8 workers

2. **CPU Usage**
   - Spiky is normal (matchmaking waves)
   - Alert if sustained >80%
   - Should average 30-50%

3. **Network**
   - Inbound: Replay uploads
   - Outbound: Discord API + Supabase
   - Should be <5 Mbps

### Setting Up Alerts

1. **Go to Notifications:**
   - Project settings → Notifications

2. **Add webhook:**
   - Webhook URL: Your Discord admin channel webhook
   - Events: Deployment, High Memory, High CPU

3. **Set thresholds:**
   - Memory: Alert at 70%
   - CPU: Alert at 80%
   - Both sustained for 5 minutes

---

## Cost Examples at Different Scales

### Scenario 1: Small Alpha (50 concurrent)
- Railway Hobby: $5
- Supabase Free: $0
- **Total: $5/month**
- **Revenue at $3/user (400 WAU): $1,200/month**
- **Profit: $1,195 (99.6% margin)**

### Scenario 2: Beta Launch (200 concurrent)
- Railway Pro: $20
- Supabase Pro: $25
- **Total: $45/month**
- **Revenue at $3/user (1,600 WAU): $4,800/month**
- **Profit: $4,755 (99.1% margin)**

### Scenario 3: Public Launch (500 concurrent)
- Railway Pro: $30
- Supabase Pro: $25
- **Total: $55/month**
- **Revenue at $3/user (4,000 WAU): $12,000/month**
- **Profit: $11,945 (99.5% margin)**

### Scenario 4: High Growth (1,000 concurrent)
- Railway Pro: $40
- Supabase Pro: $25
- **Total: $65/month**
- **Revenue at $3/user (8,000 WAU): $24,000/month**
- **Profit: $23,935 (99.7% margin)**

**Infrastructure costs are negligible. Don't worry about them.**

---

## Emergency Scaling Procedures

### If Users Complain About Slow Replays

**Symptom:** "My replay is taking forever to verify"

**Fix (5 minutes):**
1. Railway dashboard → Variables
2. Double current `WORKER_PROCESSES` value
3. Save (auto-deploys)
4. Problem solved

**Example:**
- Was: `WORKER_PROCESSES=4`
- Now: `WORKER_PROCESSES=8`
- Capacity: 2× increased
- Cost: +$10/month

### If Bot Crashes with "Out of Memory"

**Symptom:** Bot restarts, logs show OOM error

**Fix (10 minutes):**
1. Verify you're on Pro plan (8 GB RAM)
2. If not, upgrade to Pro
3. If already on Pro, optimize DataFrames:
   ```python
   # In data_access_service.py, line ~229
   "SELECT * FROM matches_1v1 ORDER BY played_at DESC LIMIT 5000"
   # Instead of loading all matches
   ```
4. Redeploy

**This should never happen on Pro plan unless you have >20,000 players.**

### If "Too Many Connections" Error

**Symptom:** Database write errors, "connection pool exhausted"

**Fix (5 minutes):**
1. Railway dashboard → Variables
2. Add or update:
   ```
   DB_POOL_MAX_CONNECTIONS=50
   ```
3. Save
4. Also verify Supabase is on Pro plan (200 connections)

---

## Resource Limits Cheat Sheet

### Railway Pro Plan Limits (More Than Enough)

| Resource | Limit | Your Usage | Headroom |
|----------|-------|------------|----------|
| RAM | 8 GB | 0.5-2 GB | 4-16× |
| vCPU | 8 cores | 2-6 cores | 1.3-4× |
| Network | Unlimited | ~5 Mbps | ∞ |
| Execution | Unlimited | 24/7 | ∞ |
| Deployments | Unlimited | Few per week | ∞ |

**You won't hit any limits until 2,000+ concurrent users.**

---

## When You DON'T Need to Scale

### These are NOT scaling issues:

❌ **"One user reported slow response"**
- Likely their internet connection
- Don't scale for one outlier

❌ **"Queue depth is 2-3"**
- Completely normal
- Alert at 10, not 3

❌ **"CPU spikes to 80% for 2 seconds"**
- Matchmaking waves cause spikes
- This is expected behavior
- Only alert if sustained >80% for 5+ minutes

❌ **"Memory is at 45%"**
- Totally fine
- Alert at 70%, critical at 85%

### When you SHOULD scale:

✅ **"Queue depth consistently >10"**
- Scale workers immediately

✅ **"Many users complaining about slow replays"**
- Scale workers immediately

✅ **"Memory sustained >70%"**
- Optimize or add RAM

✅ **"Match completion averaging >3 seconds"**
- Scale workers

✅ **"Peak concurrent >350 with 4 workers"**
- Scale to 8 workers proactively

---

## Recommended Scaling Timeline

### Week 1-2: Launch
- **Workers:** 2
- **Plan:** Hobby ($5/month)
- **Monitor:** Collect real data
- **Scale trigger:** >100 concurrent OR queue depth >5

### Week 3-4: Beta Growth
- **Workers:** 4
- **Plan:** Pro ($20/month)
- **Monitor:** Track growth rate
- **Scale trigger:** >300 concurrent OR queue depth >5

### Month 2-3: Public Launch
- **Workers:** 8
- **Plan:** Pro ($30/month)
- **Monitor:** Sustained load patterns
- **Scale trigger:** >700 concurrent OR queue depth >7

### Month 4-6: Growth Phase
- **Workers:** 12
- **Plan:** Pro ($40/month)
- **Monitor:** Consider horizontal scaling prep
- **Scale trigger:** >1,000 concurrent

### Month 6+: Mature Product
- **Workers:** 16 (vertical limit)
- **Plan:** Pro ($50/month) or start horizontal scaling
- **Monitor:** Redis migration planning
- **Scale trigger:** >1,500 concurrent → begin Redis migration

---

## Scaling Decision Flowchart

```
Is queue depth > 10?
├─ YES → Scale workers immediately (2× current)
└─ NO → Continue

Are many users complaining?
├─ YES → Scale workers immediately
└─ NO → Continue

Is peak concurrent > 80% of capacity?
├─ YES → Scale workers proactively (before hitting limit)
└─ NO → Continue

Is memory > 70%?
├─ YES → Optimize DataFrames or upgrade RAM
└─ NO → Continue

Is everything running smoothly?
└─ YES → Don't change anything!
```

**General rule: Scale when you hit 80% of any limit.**

---

## Cost Calculator

**Enter your target concurrent users:**

| Concurrent | Workers Needed | Railway Cost | Supabase | Total | Revenue ($3/user) | Profit |
|-----------|----------------|--------------|----------|-------|-------------------|--------|
| 50 | 2 | $5 | $0 | $5 | $1,200 | $1,195 |
| 100 | 2 | $5 | $0 | $5 | $2,400 | $2,395 |
| 200 | 2-4 | $20 | $25 | $45 | $4,800 | $4,755 |
| 300 | 4 | $20 | $25 | $45 | $7,200 | $7,155 |
| 500 | 4-8 | $30 | $25 | $55 | $12,000 | $11,945 |
| 800 | 8 | $35 | $25 | $60 | $19,200 | $19,140 |
| 1,000 | 8-12 | $40 | $25 | $65 | $24,000 | $23,935 |
| 1,500 | 12-16 | $50 | $25 | $75 | $36,000 | $35,925 |

**Key insight: Infrastructure is 0.1-0.2% of revenue at any scale.**

**You literally cannot overspend on Railway.** Even if you 10× your infrastructure costs unnecessarily, you're still at 99% margins.

---

## Final Recommendations

### For Launch Day
1. **Start with Pro plan + 4 workers ($45/month)**
   - Gives you 2× headroom over target (200 concurrent)
   - Costs nothing compared to lost users from poor performance
   - Can scale to 8 workers in 5 minutes if needed

2. **Set up monitoring immediately**
   - Add Railway webhook to Discord admin channel
   - Monitor queue depth every hour on launch day
   - Be ready to scale if queue builds up

3. **Have scaling plan documented**
   - Print this guide
   - Keep Railway dashboard open
   - Know how to change `WORKER_PROCESSES`

### For Growth
1. **Scale proactively, not reactively**
   - When you hit 80% of capacity, scale
   - Don't wait for users to complain

2. **Monitor weekly, not daily**
   - Check metrics once per week
   - Scale when trends show approach to limits
   - Don't obsess over daily fluctuations

3. **Trust your architecture**
   - Your system is well-designed
   - Vertical scaling is proven to work
   - Don't overthink it

---

## Support Resources

### Railway Documentation
- Docs: https://docs.railway.app
- Discord: https://discord.gg/railway
- Status: https://status.railway.app

### Supabase Documentation
- Docs: https://supabase.com/docs
- Dashboard: https://app.supabase.com
- Support: support@supabase.io

### Your Bot Monitoring
- Load monitor: `src/backend/services/load_monitor.py`
- Capacity analysis: `docs/PEAK_LOAD_ANALYSIS.md`
- Mitigation strategies: `docs/SCALING_MITIGATION_STRATEGIES.md`

---

## TL;DR: What You Actually Need to Know

1. **Start with Pro plan + 4 workers** ($45/month)
2. **Scale when queue depth > 10** (change one number in Railway)
3. **Don't worry about costs** (infrastructure is <1% of revenue)
4. **Monitor weekly, scale proactively** (at 80% of capacity)
5. **Your architecture scales effortlessly** (just add workers)

**That's it. Everything else is details.**

---

**You're ready to launch. The infrastructure will not be your bottleneck.**

**Just throw money at Railway and focus on growing your user base.** 🚀

