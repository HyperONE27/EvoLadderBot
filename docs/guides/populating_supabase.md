# Supabase Mock Data Population Guide

## Prerequisites

You need the following environment variables set in your `.env` file:

```env
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@[YOUR-PROJECT-REF].supabase.co:5432/postgres
SUPABASE_URL=https://[YOUR-PROJECT-REF].supabase.co
SUPABASE_KEY=[YOUR-ANON-KEY]
```

## How to Get Your Supabase Credentials

1. **Go to your Supabase project dashboard**
   - Visit: https://supabase.com/dashboard/project/[your-project]

2. **Get DATABASE_URL**:
   - Go to **Settings** → **Database**
   - Find **Connection String** under **Connection Info**
   - Select **URI** format
   - Copy the connection string and replace `[YOUR-PASSWORD]` with your actual database password

3. **Get SUPABASE_URL**:
   - Go to **Settings** → **API**
   - Find **Project URL**
   - Copy the URL (format: `https://xxx.supabase.co`)

4. **Get SUPABASE_KEY**:
   - Go to **Settings** → **API**
   - Find **Project API keys**
   - Copy the **anon/public** key (NOT the service_role key for security)

## Running the Population Script

Once your `.env` file is configured:

```bash
cd C:\Users\funcr\Documents\GitHub\EvoLadderBot
python scripts/populate_supabase.py
```

## What the Script Does

The script will:
1. ✅ Load 50 mock players from `src/backend/db/mock_data.json`
2. ✅ Load 200 MMR records (4 races per player)
3. ✅ Load 50 preference records (race/veto preferences)
4. ✅ Connect to your Supabase database remotely
5. ✅ Insert data using `ON CONFLICT DO NOTHING/UPDATE` (safe for re-runs)
6. ✅ Verify the data was inserted correctly
7. ✅ Show a summary report

## Expected Output

```
============================================================
🚀 Supabase Mock Data Population Script
============================================================

✅ Environment variables configured
  SUPABASE_URL: https://xxx.supabase.co

✅ Loaded mock data: 50 players, 200 MMR records, 50 preferences

🔌 Connecting to Supabase...
✅ Connected to Supabase

🎮 Inserting 50 players...
  Inserted 10/50 players...
  Inserted 20/50 players...
  Inserted 30/50 players...
  Inserted 40/50 players...
  Inserted 50/50 players...
✅ Players: 50 inserted, 0 skipped (already exist)

📊 Inserting 200 MMR records...
  Inserted 50/200 MMR records...
  Inserted 100/200 MMR records...
  Inserted 150/200 MMR records...
  Inserted 200/200 MMR records...
✅ MMR records: 200 inserted/updated, 0 skipped

⚙️ Inserting 50 preference records...
✅ Preferences: 50 inserted/updated, 0 skipped

✅ All changes committed to database

🔍 Verifying data...
  Players in database: 50
  MMR records in database: 200
  Preferences in database: 50

📋 Sample player:
  Name: RTSLegend554
  Country: BG
  MMR records: 4

============================================================
📊 POPULATION SUMMARY
============================================================
✅ Players inserted/updated: 50
✅ MMR records inserted/updated: 200
✅ Preferences inserted/updated: 50

📈 Total records in database:
  Players: 50
  MMR records: 200
  Preferences: 50
============================================================
🎉 Population complete!
============================================================
```

## Mock Player Data Details

### Players (50 total)
- Discord UIDs: 100000000 - 100000049
- Names: RTSLegend554, Strategic952, Captain22, etc.
- Countries: BG, CA, FR, DK, CR, TW, RO, BO, ID, ZZ (unknown)
- Regions: Various (NAE, EUW, SEA, etc.)
- All players have:
  - ✅ Accepted TOS
  - ✅ Completed setup
  - ✅ Activation code (format: MOCK{discord_uid})

### MMR Records (200 total, 4 per player)
- Races: bw_terran, bw_protoss, bw_zerg, sc2_terran, sc2_protoss, sc2_zerg
- MMR range: 1000-2000
- Games played: 10-99 per race
- Includes wins, losses, draws

### Preferences (50 total)
- Last chosen races: Array of 4 races per player
- Last chosen vetoes: Array of map names (0-4 per player)

## Safety Features

✅ **Idempotent**: Safe to run multiple times
- Players: `ON CONFLICT DO NOTHING` (won't duplicate)
- MMR records: `ON CONFLICT DO UPDATE` (will update stats)
- Preferences: `ON CONFLICT DO UPDATE` (will update preferences)

✅ **Error Handling**: Continues on individual record errors

✅ **Transaction**: All changes committed at once or rolled back

## Troubleshooting

### Connection Errors

**Error**: `connection refused` or `timeout`
- **Fix**: Check your `DATABASE_URL` is correct
- Verify your Supabase project is not paused
- Check your IP is allowed (Supabase allows all by default)

**Error**: `authentication failed`
- **Fix**: Double-check your database password in `DATABASE_URL`

### Data Errors

**Error**: `foreign key constraint` violations
- **Fix**: Ensure the `players` table schema exists first
- Run the schema creation SQL from `docs/schema_postgres.md`

**Error**: `column does not exist`
- **Fix**: Your schema might be outdated
- Re-run the schema creation SQL

## Next Steps After Population

1. **Verify in Supabase Dashboard**:
   - Go to **Table Editor**
   - Check `players`, `mmrs_1v1`, `preferences_1v1` tables
   - Verify data looks correct

2. **Test Your Bot**:
   - Run the bot locally
   - Try `/profile` command with a mock player Discord ID
   - Try `/leaderboard` to see MMR rankings

3. **Add More Data** (optional):
   - Edit `src/backend/db/mock_data.json`
   - Add more players/MMR records
   - Re-run the script (existing data won't duplicate)

## Security Notes

⚠️ **Production Considerations**:
- The mock data uses predictable Discord UIDs (100000000+)
- These won't conflict with real Discord UIDs (18-19 digits)
- The activation codes are fake (format: MOCK{discord_uid})
- Consider clearing mock data before production launch

---

**Script Location**: `scripts/populate_supabase.py`  
**Mock Data Location**: `src/backend/db/mock_data.json`  
**Schema Documentation**: `docs/schema_postgres.md`

