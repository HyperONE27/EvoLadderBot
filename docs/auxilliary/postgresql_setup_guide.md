# PostgreSQL Setup Guide

This guide walks you through setting up PostgreSQL both locally (for development) and on Railway + Supabase (for production), using a flexible configuration system.

## Overview

You'll set up a dual-database configuration:
- **Local Development**: PostgreSQL running on your machine
- **Production**: Supabase (hosted PostgreSQL) via Railway

The same codebase will work for both environments by changing a single environment variable.

---

## Part 1: Install PostgreSQL Locally

### Option A: Windows (Recommended - PostgreSQL Installer)

1. **Download PostgreSQL 16**:
   - Go to: https://www.postgresql.org/download/windows/
   - Download the installer (PostgreSQL 16.x)

2. **Run the Installer**:
   - Default port: `5432` (keep this)
   - Set a password for the `postgres` user (remember this!)
   - Install Stack Builder: No (not needed)
   - Install pgAdmin 4: Yes (helpful GUI tool)

3. **Verify Installation**:
   ```powershell
   psql --version
   # Should show: psql (PostgreSQL) 16.x
   ```

4. **Add to PATH** (if needed):
   - Add `C:\Program Files\PostgreSQL\16\bin` to your PATH environment variable

### Option B: Windows (via Docker)

```powershell
# Install Docker Desktop first, then:
docker pull postgres:16
docker run --name evoladder-postgres -e POSTGRES_PASSWORD=yourpassword -p 5432:5432 -d postgres:16
```

### Option C: macOS (via Homebrew)

```bash
brew install postgresql@16
brew services start postgresql@16
```

### Option D: Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

---

## Part 2: Create Local Database

### Using Command Line (psql)

```powershell
# Connect to PostgreSQL
psql -U postgres

# Inside psql:
CREATE DATABASE evoladder;
CREATE USER evoladder_user WITH PASSWORD 'local_dev_password';
GRANT ALL PRIVILEGES ON DATABASE evoladder TO evoladder_user;
\q
```

### Using pgAdmin 4 (GUI Method)

1. Open pgAdmin 4
2. Connect to local server (password: what you set during install)
3. Right-click "Databases" → Create → Database
   - Name: `evoladder`
   - Owner: `postgres`
4. Right-click "Login/Group Roles" → Create → Login/Group Role
   - Name: `evoladder_user`
   - Password: `local_dev_password`
   - Privileges: Can login: Yes

---

## Part 3: Configure Environment Variables

### Create `.env` File (if you don't have one)

```bash
# Discord Bot Token
EVOLADDERBOT_TOKEN=your_discord_token_here

# Worker Processes for Multiprocessing
WORKER_PROCESSES=2

# Database Configuration
# Options: "sqlite" or "postgresql"
DATABASE_TYPE=sqlite

# SQLite Configuration (for local development with SQLite)
SQLITE_DB_PATH=evoladder.db

# PostgreSQL Configuration (for local development with PostgreSQL)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=evoladder
POSTGRES_USER=evoladder_user
POSTGRES_PASSWORD=local_dev_password

# Production PostgreSQL (Supabase) - Add these later
# DATABASE_URL=postgresql://user:password@host:port/database
```

### Explanation of Configuration

- **`DATABASE_TYPE`**: Switch between `sqlite` and `postgresql`
  - Development with SQLite: `DATABASE_TYPE=sqlite`
  - Development with PostgreSQL: `DATABASE_TYPE=postgresql`
  - Production (Railway/Supabase): `DATABASE_TYPE=postgresql`

- **Local PostgreSQL**: Uses individual env vars (`POSTGRES_HOST`, etc.)
- **Production (Supabase)**: Uses single `DATABASE_URL` connection string

---

## Part 4: Update Database Connection Code

### Create a Flexible Database Connection Module

Create `src/backend/db/db_connection.py`:

```python
"""
Database connection configuration.

Supports both SQLite (for development) and PostgreSQL (for production).
Switch between them using the DATABASE_TYPE environment variable.
"""

import os
from typing import Optional


def get_database_connection_string() -> str:
    """
    Get the appropriate database connection string based on environment configuration.
    
    Returns:
        Connection string for SQLite or PostgreSQL
    """
    db_type = os.getenv("DATABASE_TYPE", "sqlite").lower()
    
    if db_type == "sqlite":
        # SQLite connection
        db_path = os.getenv("SQLITE_DB_PATH", "evoladder.db")
        return f"sqlite:///{db_path}"
    
    elif db_type == "postgresql":
        # Check if using production DATABASE_URL (Supabase/Railway)
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            # Production: Use the full DATABASE_URL
            # Fix for Railway/Supabase: Replace postgres:// with postgresql://
            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql://", 1)
            return database_url
        
        # Local development: Build connection string from individual env vars
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        database = os.getenv("POSTGRES_DB", "evoladder")
        user = os.getenv("POSTGRES_USER", "evoladder_user")
        password = os.getenv("POSTGRES_PASSWORD", "")
        
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    
    else:
        raise ValueError(f"Unknown DATABASE_TYPE: {db_type}. Must be 'sqlite' or 'postgresql'")


def get_database_type() -> str:
    """Get the current database type ('sqlite' or 'postgresql')."""
    return os.getenv("DATABASE_TYPE", "sqlite").lower()


def is_postgresql() -> bool:
    """Check if currently using PostgreSQL."""
    return get_database_type() == "postgresql"


def is_sqlite() -> bool:
    """Check if currently using SQLite."""
    return get_database_type() == "sqlite"


# Example usage:
if __name__ == "__main__":
    print(f"Database Type: {get_database_type()}")
    print(f"Connection String: {get_database_connection_string()}")
```

---

## Part 5: Migrate Your Database Code

### Current State (SQLite-only)

Your current `db_reader_writer.py` probably has:
```python
import sqlite3

class DatabaseReader:
    def __init__(self, db_path="evoladder.db"):
        self.db_path = db_path
        
    def _get_connection(self):
        return sqlite3.connect(self.db_path)
```

### New State (Flexible)

You have two options:

#### Option A: Minimal Changes (Keep sqlite3 for now)

1. Just update the connection path based on env var:
```python
import os
import sqlite3

class DatabaseReader:
    def __init__(self):
        db_type = os.getenv("DATABASE_TYPE", "sqlite")
        if db_type != "sqlite":
            raise NotImplementedError("PostgreSQL migration not yet complete")
        self.db_path = os.getenv("SQLITE_DB_PATH", "evoladder.db")
```

This allows you to test the configuration system without changing query code.

#### Option B: Full Migration with SQLAlchemy (Recommended)

This is the proper way, but more work. I'll provide a migration guide separately.

---

## Part 6: Testing Local PostgreSQL

### 1. Switch to PostgreSQL

Update `.env`:
```bash
DATABASE_TYPE=postgresql
```

### 2. Create Tables

Run your table creation script against PostgreSQL:
```powershell
python src/backend/db/create_table.py
```

### 3. Test Connection

Create a test script `test_pg_connection.py`:
```python
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD")
    )
    print("✅ Connected to PostgreSQL successfully!")
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()
    print(f"PostgreSQL version: {version[0]}")
    conn.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
```

Run it:
```powershell
python test_pg_connection.py
```

---

## Part 7: Setting Up Supabase (Production)

### 1. Create Supabase Project

1. Go to https://supabase.com
2. Sign up / Log in
3. Create new project:
   - Name: `EvoLadderBot`
   - Database Password: (save this!)
   - Region: Choose closest to your users
   - Plan: Pro ($25/month recommended)

### 2. Get Connection String

1. In Supabase dashboard, go to **Settings** → **Database**
2. Find **Connection String** section
3. Copy the **Connection pooling** string (uses port 6543, better for Railway)
   - Format: `postgresql://postgres.xxx:[YOUR-PASSWORD]@aws-0-xxx.pooler.supabase.com:6543/postgres`

### 3. Configure Railway

1. Go to your Railway project
2. Add environment variable:
   ```
   DATABASE_URL=postgresql://postgres.xxx:[YOUR-PASSWORD]@aws-0-xxx.pooler.supabase.com:6543/postgres
   ```
3. Add:
   ```
   DATABASE_TYPE=postgresql
   ```

### 4. Run Migrations on Supabase

Option 1: Use Supabase SQL Editor
- Copy your schema from `docs/schema_postgres.md`
- Paste into Supabase SQL Editor
- Run it

Option 2: Use psql remotely
```powershell
psql "postgresql://postgres.xxx:[YOUR-PASSWORD]@aws-0-xxx.pooler.supabase.com:6543/postgres"
# Then paste your CREATE TABLE statements
```

---

## Part 8: Development Workflow

### Local Development with SQLite (Default)
```bash
DATABASE_TYPE=sqlite
```
- Fast, no setup needed
- Good for testing features

### Local Development with PostgreSQL
```bash
DATABASE_TYPE=postgresql
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
# ... other vars
```
- Tests production-like environment
- Catches PostgreSQL-specific issues early

### Production (Railway + Supabase)
```bash
DATABASE_TYPE=postgresql
DATABASE_URL=<supabase-connection-string>
```
- Fully managed
- Automatic backups
- Scalable

---

## Part 9: SQL Differences to Watch For

### SQLite → PostgreSQL Changes Needed

1. **Auto-increment**:
   - SQLite: `INTEGER PRIMARY KEY AUTOINCREMENT`
   - PostgreSQL: `SERIAL PRIMARY KEY` or `INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY`

2. **Boolean types**:
   - SQLite: Uses integers (0/1)
   - PostgreSQL: Has native `BOOLEAN` type

3. **Date/Time**:
   - SQLite: Text strings
   - PostgreSQL: Native `TIMESTAMP` type

4. **String concatenation**:
   - SQLite: `||`
   - PostgreSQL: `||` or `CONCAT()`

5. **LIMIT/OFFSET**:
   - Both support, but PostgreSQL also has `FETCH FIRST n ROWS`

6. **Placeholders**:
   - SQLite: `?`
   - PostgreSQL (psycopg2): `%s`
   - SQLAlchemy: Handles this automatically

### Your Schema Conversion

Good news! Your `schema_postgres.md` already has the PostgreSQL-compatible schema. You just need to:
1. Run it against your local PostgreSQL
2. Update query placeholders in `db_reader_writer.py` from `?` to `%s`

---

## Part 10: Quick Start Commands

### Setup Everything Locally

```powershell
# 1. Install PostgreSQL (if not installed)
# See Part 1

# 2. Create database
psql -U postgres
CREATE DATABASE evoladder;
CREATE USER evoladder_user WITH PASSWORD 'local_dev_password';
GRANT ALL PRIVILEGES ON DATABASE evoladder TO evoladder_user;
\q

# 3. Update .env
DATABASE_TYPE=postgresql
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=evoladder
POSTGRES_USER=evoladder_user
POSTGRES_PASSWORD=local_dev_password

# 4. Install PostgreSQL Python driver
pip install psycopg2-binary

# 5. Create tables
python src/backend/db/create_table.py

# 6. Test it
python -c "from src.backend.db.db_connection import *; print(get_database_connection_string())"
```

---

## Troubleshooting

### "psql: command not found"
- Add PostgreSQL bin directory to PATH
- Windows: `C:\Program Files\PostgreSQL\16\bin`

### "password authentication failed"
- Check your password in `.env` matches what you set
- Try connecting with `postgres` superuser first

### "database does not exist"
- Did you run `CREATE DATABASE evoladder;`?
- Check database name matches in `.env`

### "could not connect to server"
- Is PostgreSQL running? `pg_ctl status` (Windows) or `brew services list` (macOS)
- Check firewall isn't blocking port 5432

### Railway: "relation does not exist"
- You need to run migrations on Supabase
- Copy schema from `schema_postgres.md` to Supabase SQL Editor

---

## Next Steps

After setting up PostgreSQL:
1. Test locally with `DATABASE_TYPE=postgresql`
2. Migrate your queries from SQLite to PostgreSQL syntax
3. Test thoroughly locally
4. Deploy to Railway with Supabase
5. Run migrations on Supabase
6. Test production environment

You now have a flexible, production-ready database configuration! 🚀

