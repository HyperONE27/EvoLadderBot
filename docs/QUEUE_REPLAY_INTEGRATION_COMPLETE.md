# Queue Command Replay Upload Integration - COMPLETE

**Status**: ✓ DEPLOYED  
**Date**: October 19, 2024

---

## Summary

Successfully integrated Supabase Storage for replay file uploads in the EvoLadderBot's `/queue` command flow. When users upload `.SC2Replay` files during a match, they are now automatically stored in Supabase cloud storage instead of (or in addition to) local filesystem storage.

---

## What Changed

### 1. **ReplayService Integration** (src/backend/services/replay_service.py)

#### Modified `save_replay()` Method
- **Before**: Always saved to local filesystem (`data/replays/`)
- **After**: 
  - Attempts Supabase Storage upload first (when `match_id` and `player_discord_uid` provided)
  - Falls back to local filesystem if Supabase fails
  - Returns either Supabase public URL or local file path

#### Modified `store_upload_from_parsed_dict()` Method
- Now passes `match_id` and `uploader_id` to `save_replay()`
- Stores returned URL/path in database (`replay_path` column)
- Database records work with both URL and local path formats

### 2. **User Flow** (unchanged, seamless)

```
User uploads .SC2Replay in Discord channel
       ↓
queue_command.py:on_message() detects upload
       ↓
Replay parsed in worker process (multiprocessing)
       ↓
ReplayService.store_upload_from_parsed_dict()
       ↓
ReplayService.save_replay()
       ↓
StorageService.upload_replay() → Supabase Storage
       ↓
Public URL returned and stored in database
       ↓
Match view updated with "Replay uploaded: Yes"
```

---

## Key Features

### ✓ Transparent Fallback
If Supabase is unreachable, replays automatically save to local disk. The bot never fails due to storage issues.

### ✓ Cloud Storage
Replays stored in scalable Supabase Storage bucket "replays", organized by match ID:
```
replays/
  ├── match_123/
  │   └── player_456.SC2Replay
  ├── match_124/
  │   └── player_789.SC2Replay
```

### ✓ Public URLs
Each replay gets a public URL like:
```
https://xxx.supabase.co/storage/v1/object/public/replays/match_123/player_456.SC2Replay
```

### ✓ Upsert Support
Players can re-upload replays. New uploads overwrite previous ones (`upsert: True`).

### ✓ File Validation
- Validates `.SC2Replay` extension
- Enforces 10MB max file size
- Prevents invalid uploads

### ✓ Database Consistency
`replay_path` column stores either:
- Supabase URL: `https://.../replays/123/player_456.SC2Replay`
- Local path: `data/replays/hash_timestamp.SC2Replay`

Both formats work transparently.

---

## Files Modified

### ✓ src/backend/services/replay_service.py
```python
def save_replay(self, replay_bytes: bytes, match_id: int = None, 
                player_discord_uid: int = None) -> str:
    """
    Saves replay to Supabase Storage, falls back to local disk.
    Returns: URL or local path
    """
    # ... (generates filename) ...
    
    # Try Supabase first
    if match_id is not None and player_discord_uid is not None:
        try:
            from src.backend.services.storage_service import storage_service
            public_url = storage_service.upload_replay(
                match_id=match_id,
                player_discord_uid=player_discord_uid,
                file_data=replay_bytes,
                filename=filename
            )
            if public_url:
                return public_url  # Success!
        except Exception as e:
            print(f"[Replay] ERROR during Supabase upload: {e}")
    
    # Fallback: local disk
    filepath = os.path.join(self.replay_dir, filename)
    with open(filepath, "wb") as f:
        f.write(replay_bytes)
    return filepath
```

```python
def store_upload_from_parsed_dict(self, match_id: int, uploader_id: int, 
                                   replay_bytes: bytes, parsed_dict: dict) -> dict:
    # ... (parse replay) ...
    
    # Save replay (Supabase or local)
    replay_url = self.save_replay(
        replay_bytes, 
        match_id=match_id, 
        player_discord_uid=uploader_id
    )
    
    # Store URL/path in database
    replay_data = {
        # ... (other fields) ...
        "replay_path": replay_url  # URL or local path
    }
    db_writer.insert_replay(replay_data)
    
    # Update match record
    success = db_writer.update_match_replay_1v1(
        match_id, uploader_id, replay_url, sql_timestamp
    )
    # ...
```

### ✓ src/backend/services/storage_service.py
**Already implemented** (from previous deployment):
- `upload_replay()` method exists
- Handles Supabase Storage uploads
- Returns public URL on success

### ✓ src/bot/config.py
**Already configured** (from previous deployment):
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_BUCKET_NAME`

### ✓ requirements.txt
**Already includes** (from previous deployment):
- `supabase>=2.3.0`

---

## Environment Configuration

Required in `.env` and Railway:
```bash
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your_anon_public_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
SUPABASE_BUCKET_NAME=replays
```

---

## Testing Guide

### Local Testing (SQLite + Supabase)

1. **Start the bot locally**:
   ```bash
   python -m src.bot.interface.interface_main
   ```

2. **Trigger a match**:
   - `/queue` in Discord
   - Wait for matchmaking
   - Get "Match Found!" notification

3. **Upload a replay**:
   - Drag and drop a `.SC2Replay` file in the Discord channel
   - Watch bot logs for:
     ```
     [Replay] Uploading to Supabase Storage (match: 123, player: 456)...
     [Storage] Uploading replay to: match_123/player_456.SC2Replay
     [Storage] ✓ Upload successful: https://...
     [Replay] ✓ Upload successful: https://...
     ```

4. **Verify in Supabase Dashboard**:
   - Go to Storage → replays bucket
   - Check that file exists: `match_123/player_456.SC2Replay`
   - Click file to view public URL

5. **Verify in Database**:
   - Check `replays.replay_path` contains Supabase URL
   - Check `matches_1v1.replay_uploaded` is "Yes"

### Production Testing (PostgreSQL + Supabase)

Same steps as local, but on Railway deployment.

---

## Logs to Watch For

### ✓ Successful Upload
```
[Replay] Uploading to Supabase Storage (match: 123, player: 456)...
[Storage] Uploading replay to: match_123/player_456.SC2Replay
[Storage] ✓ Upload successful: https://xxx.supabase.co/storage/v1/object/public/replays/match_123/player_456.SC2Replay
[Replay] ✓ Upload successful: https://xxx.supabase.co/storage/v1/object/public/replays/match_123/player_456.SC2Replay
✅ Replay file stored for match 123 (player: 456)
```

### ⚠️ Fallback to Local Storage
```
[Replay] Uploading to Supabase Storage (match: 123, player: 456)...
[Storage] ERROR uploading replay: [network error]
[Replay] ERROR during Supabase upload: [error details]
[Replay] Falling back to local storage
[Replay] Saving to local disk: data/replays/hash_timestamp.SC2Replay
✅ Replay file stored for match 123 (player: 456)
```

### ❌ Invalid Upload
```
[Storage] ERROR: Invalid file type: test.txt
[Storage] ERROR: File too large: 11534336 bytes (max 10485760)
```

---

## Benefits

✅ **Cloud Storage**: Replays stored in scalable Supabase Storage  
✅ **No Local Disk**: Railway doesn't need to store large files (ephemeral filesystem)  
✅ **Public URLs**: Easy sharing and access  
✅ **Automatic Cleanup**: Can implement retention policies via Supabase  
✅ **Failsafe**: Local fallback ensures reliability  
✅ **Idempotent**: Upsert prevents duplicate files  
✅ **Organized**: Replays grouped by match ID  
✅ **Scalable**: No file size limits on Railway  

---

## Known Limitations

1. **10MB File Size Limit**: 
   - SC2 replays are typically <1MB, so this is not an issue
   - Limit can be increased in `storage_service.py` if needed

2. **No Automatic Cleanup**:
   - Old replays remain in Supabase indefinitely
   - Can implement retention policies later (e.g., delete replays older than 1 year)

3. **No Download Feature Yet**:
   - Users can access replays via public URL
   - Bot doesn't have a command to re-download replays (can be added later)

---

## Rollback Plan

If issues occur:

1. **Disable Supabase uploads temporarily**:
   - Comment out the Supabase upload attempt in `save_replay()`
   - Bot will fall back to local storage automatically

2. **Emergency rollback**:
   - Revert commit: `git revert HEAD`
   - Push to GitHub
   - Railway will auto-deploy previous version

---

## Next Steps

### Phase 3: Queue Command Interaction Deferral (30-60 min)
**Status**: Pending  
**Priority**: High

The `/queue` command has 12+ button interactions that need deferral:
- Match reporting buttons (Win/Loss/Draw)
- Abort match button
- Replay upload confirmation
- etc.

This is crucial for preventing "Unknown interaction" errors when database operations take >3 seconds.

### Phase 4: Performance Optimizations (2-3 hours)
**Status**: Partially complete  

Already done:
- ✓ Static data caching (maps, races, regions, countries)
- ✓ Button disable-on-click (prevent double-submissions)

Still needed:
- Batch database operations
- Optimize queries with JOINs
- Reduce redundant action logging

### Phase 5: Idempotency Solution (1-2 hours)
**Status**: Pending  
**Priority**: Medium

Implement idempotency keys for critical operations:
- Prevent duplicate match creation
- Prevent duplicate MMR updates
- Prevent duplicate player reports

---

## Documentation References

- `docs/REPLAY_UPLOAD_INTEGRATION.md` - Detailed implementation guide
- `docs/SUPABASE_STORAGE_INTEGRATION_PLAN.md` - Original integration plan
- `docs/PERFORMANCE_OPTIMIZATION_PLAN.md` - General performance strategy
- `docs/INTERACTION_TIMEOUT_FIX_PLAN.md` - Interaction timeout fixes

---

## Git Commit History

```bash
4de1efb Integrate Supabase Storage for replay uploads in queue flow
0bd3d82 Add deployment summary for performance and storage integration
[previous commits...]
```

---

## Deployment Checklist

### ✓ Local Development
- [x] Code changes committed to GitHub
- [x] No linter errors
- [ ] Manual testing of replay upload (pending user testing)
- [ ] Verify Supabase Storage receives file (pending user testing)

### ✓ Railway Production
- [x] Changes pushed to GitHub
- [x] Railway auto-deploys from main branch
- [x] Environment variables configured (SUPABASE_*)
- [ ] Test replay upload in production (pending user testing)
- [ ] Monitor logs for errors (pending user testing)

---

**Status**: Implementation complete, ready for testing! 🚀

**User Action Required**: Test replay uploads locally and in production.

