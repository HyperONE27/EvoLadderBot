# Emergency Scaling Cheat Sheet

**Print this and keep it handy during launch** 🚨

---

## 🔥 Emergency: Users Reporting Slow Performance

### Symptoms
- "Replay verification is taking forever"
- "Match results are slow"
- Queue depth > 10

### Fix (5 minutes)
1. Go to Railway: https://railway.app
2. Click your project → Variables
3. Find `WORKER_PROCESSES`
4. **Double the current value**
   - If 2 → change to 4
   - If 4 → change to 8
   - If 8 → change to 16
5. Click Save
6. Wait 3 minutes for redeploy
7. ✅ Problem solved

**Cost:** +$10-20/month  
**Benefit:** 2× capacity immediately

---

## 💥 Emergency: Bot Crashed

### Symptoms
- Bot offline
- Railway shows "Crashed"
- Logs show "Out of Memory" or similar

### Fix (2 minutes)
1. Railway dashboard → Click "Restart"
2. If it crashes again:
   - Check you're on **Pro plan** (not Hobby)
   - If on Hobby → Upgrade to Pro immediately
3. If still crashing on Pro:
   - Contact me (this shouldn't happen)

**Most likely cause:** Traffic spike, automatic restart will fix it

---

## 📊 What's Normal vs. What's Not

### ✅ Normal (Don't Panic)
- Queue depth: 0-5
- Memory: 30-65%
- CPU: 20-60% (spikes to 80% during matchmaking waves)
- Match completion: <2 seconds
- Occasional user complaint

### ⚠️ Warning (Monitor Closely)
- Queue depth: 5-10
- Memory: 65-75%
- CPU: 60-80% sustained
- Match completion: 2-3 seconds
- Multiple user complaints

### 🚨 Critical (Scale NOW)
- Queue depth: >10
- Memory: >75%
- CPU: >80% sustained for 5+ minutes
- Match completion: >3 seconds
- Flood of user complaints

---

## 🎯 Quick Decision Matrix

| If you see... | Do this... | Time | Cost |
|---------------|------------|------|------|
| Queue depth 10-15 | Double workers | 5 min | $10-20/mo |
| Queue depth >20 | Triple workers | 5 min | $20-30/mo |
| Memory >75% | Upgrade to Pro (if not already) | 2 min | $15/mo |
| Memory >85% | Call for help | N/A | N/A |
| Many crashes | Check logs, restart, escalate | 5 min | $0 |
| Users angry | Scale workers + post status update | 5 min | $10-20/mo |

---

## 📞 Scaling Command Reference

### Scale to 4 Workers (480 concurrent capacity)
```
Railway → Variables → WORKER_PROCESSES → 4
```

### Scale to 8 Workers (960 concurrent capacity)
```
Railway → Variables → WORKER_PROCESSES → 8
```

### Scale to 12 Workers (1,440 concurrent capacity)
```
Railway → Variables → WORKER_PROCESSES → 12
```

### Scale to 16 Workers (1,920 concurrent capacity - MAX)
```
Railway → Variables → WORKER_PROCESSES → 16
```

**Each scaling step takes 5 minutes and costs $5-10/month more.**

---

## 🔍 How to Check Current Status

### Railway Metrics
```
1. Railway dashboard → Your project
2. Left sidebar → Metrics
3. Check: Memory %, CPU %, Network
```

### Bot Logs
```
1. Railway dashboard → Your project
2. Left sidebar → Deployments → Latest
3. Look for:
   - "[ProcessPool] Initialized with X workers"
   - "[DataAccessService] Write queue: X"
   - Any error messages
```

### In Discord (Admin Command - Future)
```
/admin health
```
Shows current load, queue depths, capacity utilization.

---

## 💰 Emergency Budget Approval

**Your approval to scale immediately:**

| Situation | Action | Max Cost/Month | Authorized |
|-----------|--------|----------------|------------|
| Users complaining | Scale workers | $50 | ✅ YES |
| Bot crashed | Upgrade plan | $50 | ✅ YES |
| Traffic spike | Scale to max (16 workers) | $100 | ✅ YES |

**Infrastructure costs are negligible. Don't hesitate to scale.**

At 1,000 concurrent users:
- Revenue: $24,000/month
- Infrastructure: $65/month
- **You can't overspend on Railway**

---

## 📱 Emergency Contacts

### Railway Support
- Discord: https://discord.gg/railway
- Twitter: @Railway
- Status page: https://status.railway.app

### Supabase Support
- Dashboard: https://app.supabase.com
- Discord: https://discord.supabase.com
- Email: support@supabase.io

### Bot Architecture Designer (AI)
- Refer to: `docs/SCALING_MITIGATION_STRATEGIES.md`
- Emergency procedures documented in detail

---

## 🚀 Launch Day Checklist

### Before Launch
- [ ] Verify on **Railway Pro plan** ($20/month)
- [ ] Set `WORKER_PROCESSES=4` (2× target capacity)
- [ ] Upgrade to **Supabase Pro** ($25/month)
- [ ] Test worker scaling (change to 8, then back to 4)
- [ ] Set up Railway alerts (webhook to admin channel)
- [ ] Print this cheat sheet
- [ ] Keep Railway dashboard open in browser tab

### During Launch (First 4 Hours)
- [ ] Monitor Railway metrics every 15 minutes
- [ ] Check bot logs every 30 minutes
- [ ] Watch Discord for user complaints
- [ ] Track queue depth (should stay <5)
- [ ] Be ready to scale workers if needed

### After Launch (First Week)
- [ ] Check metrics once per day
- [ ] Monitor trends (growing queue depth = scale soon)
- [ ] Collect baseline performance data
- [ ] Document any issues and resolutions

---

## 🎛️ Quick Commands (Copy-Paste Ready)

### Check Current Worker Count
```bash
# In bot logs, search for:
[ProcessPool] Initialized with
```

### Check Queue Depth (Future Admin Command)
```python
from src.backend.services.data_access_service import DataAccessService
service = DataAccessService()
print(f"Queue depth: {service._write_queue.qsize()}")
```

### Check Memory Usage
```python
import psutil
process = psutil.Process()
print(f"Memory: {process.memory_info().rss / 1024 / 1024:.0f} MB")
```

---

## 🧠 Mental Model

**Think of workers as checkout lanes at a grocery store:**

- **2 workers** = 2 lanes (handles small crowd)
- **4 workers** = 4 lanes (handles moderate crowd)
- **8 workers** = 8 lanes (handles busy day)
- **16 workers** = 16 lanes (handles Black Friday)

**When the line gets long (queue depth > 10), open more lanes (add workers).**

It's that simple.

---

## ❓ Common Questions

### "How do I know if I need to scale?"
**Watch queue depth.** If it stays above 5 for 10+ minutes, scale.

### "Will scaling cause downtime?"
**No.** Railway does rolling deploys. ~30 seconds of degraded performance, not full downtime.

### "What if I scale too much?"
**No problem.** You can scale back down. Costs a few extra dollars for a day. Better than angry users.

### "How long does scaling take?"
**5 minutes:** Change variable → Save → Auto-deploy → Online

### "Can I scale during active matches?"
**Yes.** Matches in progress are unaffected. New workers join the pool, existing workers finish their tasks.

### "What if nothing works?"
**Railway auto-restarts crashed services.** Usually fixes itself in 2-3 minutes. If not, manual restart takes 30 seconds.

---

## 🎯 The One Thing to Remember

**If users are complaining about performance:**
1. Go to Railway
2. Double `WORKER_PROCESSES`
3. Problem solved

**Everything else is details.**

---

## 📊 Expected Performance at Launch

### With 4 Workers (Your Starting Config)
- **Capacity:** 480 concurrent users
- **Queue depth:** 0-3 (normal)
- **Match completion:** <2 seconds
- **Replay verification:** <5 seconds
- **Memory:** 40-50%
- **CPU:** 30-50% (spikes to 80%)

**If you see these numbers, everything is fine. Don't change anything.**

---

## 🏁 Final Checklist

- [ ] I know how to access Railway dashboard
- [ ] I know where `WORKER_PROCESSES` is
- [ ] I can double the worker count in 5 minutes
- [ ] I know what queue depth is and where to check it
- [ ] I have this cheat sheet printed or bookmarked
- [ ] I'm on Railway Pro plan ($20/month)
- [ ] I have budget approval to scale if needed
- [ ] I'm ready to launch 🚀

---

**Remember: Your architecture is solid. Scaling is easy. Infrastructure is cheap. Focus on users, not servers.** ✅

