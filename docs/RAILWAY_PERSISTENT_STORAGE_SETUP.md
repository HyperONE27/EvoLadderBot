# Railway Persistent Storage Setup Guide

## Overview

This document explains how the `write_log.sqlite` database is configured to persist across Railway deployments using a persistent volume mount.

## The Problem

The SQLite-based write-ahead log prevents data loss during process crashes by storing pending database writes on disk. However, without a persistent volume, this file lives in the container's ephemeral filesystem and is destroyed during redeployments, negating the durability benefits.

## The Solution

Railway provides **Persistent Volumes** that survive container replacements. By mounting a volume and configuring the application to use it, the write log database persists across all deployments, crashes, and restarts.

## Setup Steps

### 1. Create a Persistent Volume in Railway

1. Go to your Railway project dashboard
2. Click on your bot service
3. Navigate to the "Volumes" tab
4. Click "New Volume"
5. Configure:
   - **Name**: `bot-persistent-storage` (or any descriptive name)
   - **Size**: 1-5 GB (more than sufficient for the write log)
   - **Mount Path**: `/volume`

### 2. Set Environment Variable

In your Railway service's environment variables, add:

```
RAILWAY_PERSISTENT_STORAGE_PATH=/volume
```

**Important**: The value must exactly match the mount path you chose in step 1.

### 3. Deploy

The application is already configured to use this environment variable. Simply deploy your code, and the bot will automatically:
- Create the `write_log.sqlite` database at `/volume/write_log.sqlite`
- Store all pending writes there
- Recover pending writes on startup

## How It Works

### Code Configuration

The application reads the storage path from the environment variable:

**File: `src/bot/config.py`**
```python
RAILWAY_PERSISTENT_STORAGE_PATH = os.getenv("RAILWAY_PERSISTENT_STORAGE_PATH", "data")
```

**File: `src/backend/services/data_access_service.py`**
```python
db_path = os.path.join(RAILWAY_PERSISTENT_STORAGE_PATH, "write_log.sqlite")
self._write_log = WriteLog(db_path=db_path)
```

### Volume Mount Behavior

When Railway starts your container:
1. The persistent volume is mounted at `/volume` (or your chosen path)
2. Any data written to `/volume` is stored on the persistent volume
3. When a new container is deployed, it attaches to the **same volume**
4. The new container sees all data from the previous container

This ensures the `write_log.sqlite` file and its contents persist indefinitely.

## Local Development

For local development without Railway, the application defaults to using a local `data` directory:

```
RAILWAY_PERSISTENT_STORAGE_PATH=data (default)
```

The write log will be created at `data/write_log.sqlite` in your project directory.

## Verification

After deployment, check your Railway logs for confirmation:

```
[Write Log] Initialized at /volume/write_log.sqlite
```

This confirms the application is using the persistent volume.

## Data Durability Guarantees

With this setup:
- ✅ **Process crashes**: Data persists (always did)
- ✅ **Container restarts**: Data persists (always did)
- ✅ **Redeployments**: Data persists (NEW - this is what the volume solves)
- ✅ **Code updates**: Data persists (NEW)
- ✅ **Railway infrastructure changes**: Data persists (NEW)

The write log now provides true durability in all scenarios.

## Troubleshooting

### Issue: "Database file not found" after deployment

**Cause**: Environment variable `RAILWAY_PERSISTENT_STORAGE_PATH` is not set or doesn't match the volume mount path.

**Fix**: Ensure the environment variable value exactly matches your volume's mount path (e.g., `/volume`).

### Issue: "Permission denied" when writing to database

**Cause**: The mount path is not writable by the application.

**Fix**: Railway volumes are automatically writable. If this occurs, check that the mount path is correctly configured in Railway's volume settings.

### Issue: Application still uses `data/` directory

**Cause**: The environment variable is not being read correctly.

**Fix**: Verify the environment variable is set in Railway's dashboard and restart the service.

## Testing

The implementation includes comprehensive tests:
- `tests/test_write_durability.py` (6 tests) - Verifies write log durability
- `tests/test_match_state_race_condition.py` (4 tests) - Verifies race condition fixes
- `tests/test_persistent_storage_config.py` (3 tests) - Verifies path configuration

All 13 tests pass, confirming the system works correctly.

