# Quick Reference: What to Do Next

**Last Updated**: 2025  
**For**: Solo developer looking for concrete next steps

---

## TL;DR

1. ✅ **Already done the hardest work** (multiprocessing)
2. 🔴 **Critical blocker**: PostgreSQL migration (must do before launch)
3. 🟡 **Important**: Complete ping/region matching logic
4. 🟢 **Quick wins**: Leaderboard caching (30 mins, huge impact)
5. ❌ **Don't do**: Celery/Redis, microservices, rewrites

**Bottom line**: Your architecture handles 750+ concurrent users as-is. Focus on features, not more scaling.

---

## This Week's Checklist

### Monday-Tuesday: PostgreSQL Migration (6-8 hours)
```bash
# 1. Sign up for Supabase Pro
# 2. Create new project, get connection string
# 3. Update db_reader_writer.py
#    - Change sqlite3 → psycopg2
#    - Update connection string from .env
# 4. Export data: sqlite3 evoladder.db .dump > dump.sql
# 5. Clean for PostgreSQL: sed 's/AUTOINCREMENT/SERIAL/g'
# 6. Import to PostgreSQL
# 7. Test everything thoroughly
```

### Wednesday: Quick Wins (2-3 hours)
```python
# 1. Add leaderboard caching (30 mins)
from cachetools import cached, TTLCache

@cached(cache=TTLCache(maxsize=1, ttl=60))
def get_leaderboard():
    return db_reader.get_top_100_players()

# 2. Fix CommandGuardService (1 hour)
#    Move discord.Embed creation to bot layer

# 3. Profile command (1-2 hours)
#    Copy leaderboard_command.py pattern
```

### Thursday-Friday: Ping/Region Matching (4-6 hours)
```python
# 1. Complete cross-table (2 hours)
# 2. Implement dynamic weighting (2-3 hours)
def get_match_weights(mmr, wait_cycles):
    if mmr < 1200:
        return (0.75, 0.25)  # Favor ping
    elif mmr < 1800:
        return (0.50, 0.50)  # Balanced
    else:
        return (0.25, 0.75)  # Favor MMR

# 3. Test (1 hour)
```

**Total**: ~12-15 hours → Ready for closed alpha! 🚀

---

## This Month: Alpha Testing

### Week 1-2
- Launch closed alpha
- Monitor performance
- Collect user feedback

### Week 3-4
- Fix bugs discovered
- Tune ping/MMR weights based on data
- Add logging/monitoring
- No major changes - let it run!

---

## Files That Need Attention

### High Priority
| File | What to do | Effort | Impact |
|------|------------|--------|--------|
| `src/backend/db/db_reader_writer.py` | PostgreSQL migration | HIGH | CRITICAL |
| `src/backend/services/matchmaking_service.py` | Complete ping logic | MEDIUM | HIGH |
| `src/backend/services/leaderboard_service.py` | Add caching | VERY LOW | HIGH |
| `src/bot/interface/commands/profile_command.py` | Implement command | LOW | MEDIUM |
| `src/backend/services/command_guard_service.py` | Remove Discord dependency | LOW | MEDIUM |

### Low Priority (Can Wait)
| File | What to do | When |
|------|------------|------|
| `src/backend/services/*.py` | Add docstrings | Gradually |
| `src/backend/services/*.py` | Dependency injection | After PostgreSQL |
| `requirements.txt` | Add type checking tools | When refactoring |

---

## Quick Commands

### Testing
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test
python -m pytest tests/backend/services/test_multiprocessing_replay.py -v

# Check test coverage
python -m pytest tests/ --cov=src --cov-report=html
```

### Database
```bash
# Backup SQLite
cp evoladder.db evoladder_backup.db

# Export to PostgreSQL
sqlite3 evoladder.db .dump > dump.sql

# Connect to PostgreSQL (local)
psql -h localhost -U evoladder_user -d evoladder

# Connect to Supabase
psql $DATABASE_URL
```

### Performance Monitoring
```bash
# Check worker processes
ps aux | grep python

# Monitor Railway logs
railway logs

# Check database connections
# (In PostgreSQL)
SELECT count(*) FROM pg_stat_activity;
```

---

## Performance Checklist

### ✅ Already Optimized
- [x] Non-blocking replay parsing (multiprocessing)
- [x] Async/await throughout
- [x] Replay files on disk, not in database
- [x] Process pool with configurable workers

### 🎯 Do Next
- [ ] PostgreSQL (multi-writer concurrency)
- [ ] Leaderboard caching (90% query reduction)
- [ ] Connection pooling (PGBouncer on Supabase)

### ⏰ Can Wait
- [ ] Database indexes (measure first)
- [ ] Read replicas (only if needed at high scale)
- [ ] Advanced caching (Redis, Memcached)

---

## Common Questions

### "Should I implement Celery + Redis?"
**No.** Your ProcessPoolExecutor handles 600 replays/minute. Your realistic load is ~20/minute. You have 30x headroom.

### "Should I add more worker processes?"
**Not yet.** Start with 2, monitor utilization. Only increase if you see consistent 90%+ utilization.

### "Should I rewrite with FastAPI?"
**No.** Your architecture is good. If you want a web interface, add FastAPI as a separate service that shares your backend services.

### "When should I worry about scaling?"
**When you see**:
- Worker queue backlogs (50+ replays waiting)
- Database connection errors ("too many connections")
- Consistent slow response times (> 1s for most operations)
- 90%+ CPU usage sustained

**Not when**:
- A single user reports lag once
- You're at 50 concurrent users
- You read a blog post about microservices

### "What metrics should I track?"
**Essential**:
- Active matches count
- Queue size
- Worker pool utilization
- Database query times
- API response times

**Nice to have**:
- Cache hit rates
- Error rates by type
- User retention metrics

---

## Effort Estimates Reference

### Very Low Effort (< 1 hour)
- Leaderboard caching
- Environment variable documentation
- Add health check endpoint
- Fix CommandGuardService

### Low Effort (1-3 hours)
- Profile command
- Performance logging
- Terms of Service update
- Most bug fixes

### Medium Effort (4-8 hours)
- Complete ping/region matching
- Add more integration tests
- Extract magic numbers
- Centralized configuration

### High Effort (1-2 days)
- PostgreSQL migration
- Dependency injection refactoring
- Repository pattern implementation

### Very High Effort (1+ weeks)
- **DON'T DO**: Celery + Redis
- **DON'T DO**: Microservices
- **DON'T DO**: Full rewrite

---

## When Things Go Wrong

### "Bot is unresponsive"
1. Check Railway logs for exceptions
2. Verify process pool is created
3. Check if a replay parse is stuck
4. Restart if needed (one-click in Railway)

### "Database is locked" error
**Root cause**: Still on SQLite (single writer)  
**Solution**: Migrate to PostgreSQL (blocks other work!)

### "Match results not saving"
1. Check database connection
2. Verify transaction commits
3. Look for exceptions in match_completion_service
4. Check if both players reported correctly

### "Leaderboard is slow"
1. Add caching (30 mins)
2. Check database indexes
3. Consider limiting to top 100 (not top 1000)

---

## Success Metrics

### Week 1
- PostgreSQL migration complete
- No "database locked" errors
- Bot responding < 500ms to all commands
- Closed alpha ready

### Week 2
- 10-20 alpha testers
- < 5 bugs reported
- All matches completing correctly
- Leaderboard loading < 1s

### Month 1
- 50+ active users
- Matchmaking working smoothly
- No major performance issues
- Positive user feedback on matches

### Month 3
- 200+ active users
- Ready for open beta
- Infrastructure stable
- Feature requests prioritized

---

## Resources

### Documentation
- Full roadmap: `docs/COMPREHENSIVE_IMPROVEMENT_ROADMAP.md`
- Scaling strategy: `docs/scaling_strategy.md`
- Multiprocessing guide: `docs/concurrency_strategy.md`
- PostgreSQL setup: `docs/postgresql_setup_guide.md`

### External Resources
- [Supabase Docs](https://supabase.com/docs)
- [Railway Docs](https://docs.railway.app)
- [Python Multiprocessing](https://docs.python.org/3/library/multiprocessing.html)
- [Discord.py Guide](https://discordpy.readthedocs.io/)

---

**Remember**: You've already solved the hardest problem (making the bot not freeze). Everything else is polish. Focus on features that make players happy, not architectural perfection. 🚀

