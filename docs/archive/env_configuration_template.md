# Environment Configuration Template

Copy this configuration into your `.env` file and fill in your actual values.

```bash
# =============================================================================
# DISCORD BOT
# =============================================================================
EVOLADDERBOT_TOKEN=your_discord_bot_token_here

# =============================================================================
# MULTIPROCESSING
# =============================================================================
# Number of worker processes for CPU-bound tasks (replay parsing)
# Recommended: (Number of CPU cores) - 1
# Examples: 2-core=1, 4-core=3, 8-core=7
WORKER_PROCESSES=2

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================
# Database type: "sqlite" or "postgresql"
# - sqlite: Local development, simple setup
# - postgresql: Production or local PostgreSQL testing
DATABASE_TYPE=sqlite

# -----------------------------------------------------------------------------
# SQLite Configuration (when DATABASE_TYPE=sqlite)
# -----------------------------------------------------------------------------
SQLITE_DB_PATH=evoladder.db

# -----------------------------------------------------------------------------
# PostgreSQL Configuration - Local Development (when DATABASE_TYPE=postgresql)
# -----------------------------------------------------------------------------
# These are used when DATABASE_URL is NOT set
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=evoladder
POSTGRES_USER=evoladder_user
POSTGRES_PASSWORD=your_local_postgres_password

# -----------------------------------------------------------------------------
# PostgreSQL Configuration - Production (Railway + Supabase)
# -----------------------------------------------------------------------------
# This takes precedence over individual POSTGRES_* vars when set
# Get this from Supabase Dashboard > Settings > Database > Connection String (Pooling)
# Example format: postgresql://postgres.xxx:[PASSWORD]@host.pooler.supabase.com:6543/postgres
# DATABASE_URL=postgresql://user:password@host:port/database
```

## Quick Setup Guides

### Local Development with SQLite (Default)
```bash
DATABASE_TYPE=sqlite
SQLITE_DB_PATH=evoladder.db
```
No additional setup needed. Just run the bot.

### Local Development with PostgreSQL
```bash
DATABASE_TYPE=postgresql
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=evoladder
POSTGRES_USER=evoladder_user
POSTGRES_PASSWORD=your_password_here
```
Requires PostgreSQL installed locally. See `postgresql_setup_guide.md`.

### Production (Railway + Supabase)
```bash
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql://postgres.xxx:[YOUR-PASSWORD]@aws-0-xxx.pooler.supabase.com:6543/postgres
```
Get `DATABASE_URL` from Supabase dashboard. Railway will use this automatically.

