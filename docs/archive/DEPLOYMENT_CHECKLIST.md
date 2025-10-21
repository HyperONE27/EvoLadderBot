# Database Migration Deployment Checklist

**Date**: October 19, 2025  
**Status**: ✅ Code Complete | 🔄 Railway Deployment Pending

## What Was Completed

### 1. Database Adapter Layer (100% Complete)
- ✅ Created `BaseAdapter` abstract class
- ✅ Implemented `SQLiteAdapter` for local development
- ✅ Implemented `PostgreSQLAdapter` for production (Supabase)
- ✅ Query parameter conversion (`:param` → `%(param)s`)
- ✅ Unified interface for both databases

### 2. Database Migration (100% Complete)
- ✅ **ALL DatabaseReader methods** converted to adapter pattern
- ✅ **ALL DatabaseWriter methods** converted to adapter pattern
- ✅ Removed all direct `sqlite3` imports from `db_reader_writer.py`
- ✅ Removed all `cursor.execute()` calls
- ✅ Removed all `conn.commit()` calls
- ✅ Fixed positional parameter (`?`) usage

### 3. Local Testing (100% Complete)
- ✅ SQLite adapter tested successfully
- ✅ DatabaseReader methods verified
- ✅ DatabaseWriter methods verified
- ✅ 52 players, 202 MMR records tested
- ✅ Existing unit tests pass

### 4. Environment Configuration
- ✅ Centralized all env vars in `src/bot/config.py`
- ✅ No fallback values (fails fast if missing)
- ✅ `DATABASE_TYPE` switches between sqlite/postgresql
- ✅ Railway environment variables configured

---

## What to Verify on Railway

### Step 1: Check Railway Deployment
1. Go to Railway dashboard: https://railway.app/
2. Check the latest deployment status
3. Look for successful build and deploy messages

### Step 2: Verify Database Connection
Check Railway logs for these success indicators:
```
[Database] Using PostgreSQL: postgresql://postgres:***@...
[SUCCESS] Database connection test passed!
Connected to PostgreSQL
Found X tables in database
Bot is ready!
```

### Step 3: Test Discord Bot
Once deployed, test these commands in Discord:
1. `/queue` - Should work (tests preferences table)
2. `/leaderboard` - Should display (tests mmrs_1v1 table)
3. `/profile` - Should show player info (tests players table)
4. `/setcountry` - Should update (tests write operations)

### Step 4: Verify No Data Loss
Check that existing player data is intact:
- Player counts match
- MMR values are correct
- Match history is preserved
- Command logs are present

---

## If Deployment Fails

### Common Issues and Fixes

#### 1. "could not translate host name"
**Cause**: DNS resolution issue  
**Fix**: Use Direct Connection (port 5432) instead of Connection Pooling (port 6543)
```bash
# In Railway environment variables:
DATABASE_URL=postgresql://postgres.xxx:PASSWORD@db.xxx.supabase.co:5432/postgres
```

#### 2. "Required environment variable 'XXX' is not set"
**Cause**: Missing env var in Railway  
**Fix**: Add the variable in Railway dashboard
- Go to Variables tab
- Add missing variable
- Make sure it's marked as "SHARED"

#### 3. "relation 'xxx' does not exist"
**Cause**: Schema not initialized on Supabase  
**Fix**: Run schema creation script on Supabase:
1. Go to Supabase SQL Editor
2. Run `docs/schema_postgres.md` SQL statements
3. Verify tables exist

#### 4. "syntax error at or near ':'"
**Cause**: Query not using adapter (missed conversion)  
**Fix**: This should not happen - all methods were converted!
- Check Railway logs for the specific query
- Report the issue if found

---

## Railway Environment Variables Checklist

Verify these are set in Railway dashboard:

- ✅ `EVOLADDERBOT_TOKEN` - Your Discord bot token
- ✅ `DATABASE_TYPE` - Set to `postgresql`
- ✅ `DATABASE_URL` - Your Supabase connection string
- ✅ `GLOBAL_TIMEOUT` - Command timeout (e.g., `180`)
- ✅ `WORKER_PROCESSES` - Number of workers (e.g., `2`)

**Note**: `SQLITE_DB_PATH` is not needed on Railway (only for local dev).

---

## Rollback Plan

If deployment fails and you need to rollback:

1. **Immediate Rollback** (Railway):
   ```bash
   # In Railway dashboard, go to Deployments tab
   # Find the previous working deployment
   # Click "Redeploy"
   ```

2. **Code Rollback** (Git):
   ```bash
   git revert a93ba1c
   git push
   ```

3. **Database Connection Fallback** (Railway env vars):
   - Temporarily set `DATABASE_TYPE=sqlite` (will fail on Railway)
   - Better: Keep PostgreSQL but fix the connection string

---

## Success Indicators

### ✅ Deployment Successful If:
1. Railway build completes without errors
2. Bot shows "ready" in logs
3. Database connection test passes
4. Discord commands respond normally
5. No "adapter" or "connection" errors in logs

### 🎉 Migration Complete When:
- Bot runs on Railway with PostgreSQL ✅
- All Discord commands work ✅
- No data loss ✅
- Can switch between SQLite (local) and PostgreSQL (production) transparently ✅

---

## Next Steps After Successful Deployment

1. **Monitor for 24 hours** - Watch for any edge case errors
2. **Test all command paths** - Queue, profile, leaderboard, match reporting
3. **Verify replay uploads** - Make sure file paths work
4. **Check match history** - Ensure writes are persisting
5. **Performance monitoring** - Compare response times

---

## Technical Details

### Architecture
```
Discord Bot (interface_main.py)
    ↓
Services (matchmaking_service, mmr_service, etc.)
    ↓
Database Classes (DatabaseReader, DatabaseWriter)
    ↓
Adapter Layer (BaseAdapter)
    ↙         ↘
SQLiteAdapter    PostgreSQLAdapter
    ↓                    ↓
Local DB File        Supabase PostgreSQL
```

### Key Changes in This Release
- 🔄 All database operations now use adapter pattern
- 🔄 Query parameters converted automatically
- 🔄 No more SQLite-specific code in application layer
- 🔄 Environment-based database selection
- 🔄 Fail-fast on missing configuration

### Files Modified
- `src/backend/db/db_reader_writer.py` - All methods converted
- `src/backend/db/adapters/` - New adapter layer
- `src/bot/config.py` - Centralized configuration
- `docs/DATABASE_MIGRATION_STATUS.md` - Progress tracking

---

**Questions or Issues?**  
Check Railway logs first, then review this checklist. All common issues are documented above.

**Ready to verify?** → Check Railway dashboard now!

