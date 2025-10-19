# Replay Upload Integration with Supabase Storage

**Status**: ✓ COMPLETE  
**Date**: October 19, 2024

---

## Overview

This document describes the integration of Supabase Storage for replay file uploads in the EvoLadderBot's `/queue` command flow.

---

## Architecture

### File Flow

```
Discord User → Upload .SC2Replay
       ↓
queue_command.py:on_message()
       ↓
ReplayService.store_upload_from_parsed_dict()
       ↓
ReplayService.save_replay()
       ↓
StorageService.upload_replay()
       ↓
Supabase Storage Bucket: "replays"
```

### Storage Structure

Replays are organized in Supabase Storage as:
```
replays/
  ├── {match_id}/
  │   └── player_{discord_uid}.SC2Replay
  ├── {match_id}/
  │   └── player_{discord_uid}.SC2Replay
  ...
```

---

## Implementation Details

### 1. Modified `ReplayService.save_replay()` (src/backend/services/replay_service.py)

**Changes**:
- Added optional parameters: `match_id` and `player_discord_uid`
- Attempts Supabase upload first if both parameters provided
- Falls back to local filesystem storage if Supabase fails
- Returns either a Supabase URL or local file path

**Key Code**:
```python
def save_replay(self, replay_bytes: bytes, match_id: int = None, 
                player_discord_uid: int = None) -> str:
    """
    Saves a replay file to Supabase Storage and returns its URL.
    Falls back to local storage if Supabase upload fails.
    """
    replay_hash = self._calculate_replay_hash(replay_bytes)
    filename = self._generate_filename(replay_hash)
    
    # Try Supabase Storage first if match_id and player_discord_uid are provided
    if match_id is not None and player_discord_uid is not None:
        try:
            from src.backend.services.storage_service import storage_service
            
            print(f"[Replay] Uploading to Supabase Storage (match: {match_id}, player: {player_discord_uid})...")
            public_url = storage_service.upload_replay(
                match_id=match_id,
                player_discord_uid=player_discord_uid,
                file_data=replay_bytes,
                filename=filename
            )
            
            if public_url:
                print(f"[Replay] ✓ Upload successful: {public_url}")
                return public_url
            else:
                print(f"[Replay] ✗ Supabase upload failed, falling back to local storage")
                
        except Exception as e:
            print(f"[Replay] ERROR during Supabase upload: {e}")
            print(f"[Replay] Falling back to local storage")
    
    # Fallback: Save to local disk
    filepath = os.path.join(self.replay_dir, filename)
    print(f"[Replay] Saving to local disk: {filepath}")
    
    with open(filepath, "wb") as f:
        f.write(replay_bytes)
    
    return filepath
```

### 2. Updated `ReplayService.store_upload_from_parsed_dict()` (src/backend/services/replay_service.py)

**Changes**:
- Passes `match_id` and `uploader_id` to `save_replay()`
- Stores returned URL/path in database (`replay_path` column)
- Updates match record with replay URL/path

**Key Code**:
```python
# Save the replay file (uploads to Supabase Storage, falls back to local)
# Pass match_id and uploader_id for Supabase storage path
replay_url = self.save_replay(replay_bytes, match_id=match_id, player_discord_uid=uploader_id)

# ... (prepare replay_data) ...

replay_data = {
    # ... (other fields) ...
    "replay_path": replay_url  # Store URL (Supabase) or path (local fallback)
}

# Insert into replays table
db_writer.insert_replay(replay_data)

# Update match record with replay URL/path
success = db_writer.update_match_replay_1v1(
    match_id,
    uploader_id,
    replay_url,  # Store URL (Supabase) or path (local fallback)
    sql_timestamp
)
```

### 3. Existing `StorageService.upload_replay()` (src/backend/services/storage_service.py)

**Already Implemented** (from previous deployment):
```python
def upload_replay(
    self,
    match_id: int,
    player_discord_uid: int,
    file_data: bytes,
    filename: str
) -> Optional[str]:
    """
    Upload replay file to Supabase Storage.
    
    File path structure: {match_id}/player_{discord_uid}.SC2Replay
    
    Args:
        match_id: Match ID
        player_discord_uid: Player's Discord UID
        file_data: Replay file bytes
        filename: Original filename (for validation)
        
    Returns:
        Public URL of uploaded file, or None if failed
    """
    # Validate file extension
    if not filename.lower().endswith('.sc2replay'):
        print(f"[Storage] ERROR: Invalid file type: {filename}")
        return None
    
    # Validate file size (max 10MB for safety)
    max_size = 10 * 1024 * 1024  # 10MB
    if len(file_data) > max_size:
        print(f"[Storage] ERROR: File too large: {len(file_data)} bytes (max {max_size})")
        return None
    
    # Path in bucket: {match_id}/player_{discord_uid}.SC2Replay
    file_path = f"{match_id}/player_{player_discord_uid}.SC2Replay"
    
    try:
        # Upload to Supabase Storage
        print(f"[Storage] Uploading replay to: {file_path}")
        response = self.supabase.storage.from_(self.bucket_name).upload(
            path=file_path,
            file=file_data,
            file_options={
                "content-type": "application/octet-stream",
                "upsert": True  # Overwrite if exists (player re-uploading)
            }
        )
        
        # Get public URL
        public_url = self.supabase.storage.from_(self.bucket_name).get_public_url(file_path)
        
        print(f"[Storage] ✓ Upload successful: {public_url}")
        return public_url
        
    except Exception as e:
        print(f"[Storage] ERROR uploading replay: {e}")
        return None
```

---

## Key Features

### 1. **Transparent Fallback**
- If Supabase upload fails, the system automatically falls back to local filesystem storage
- This ensures development/testing can continue even without Supabase access

### 2. **Upsert Support**
- `upsert: True` in the storage upload allows players to re-upload replays
- Previous uploads are overwritten

### 3. **File Validation**
- Validates `.SC2Replay` extension
- Enforces max file size (10MB)

### 4. **Organized Storage**
- Replays grouped by `match_id` for easy management
- Each player's replay stored as `player_{discord_uid}.SC2Replay`

### 5. **Database Consistency**
- `replay_path` column stores either:
  - Supabase public URL (e.g., `https://.../replays/123/player_456.SC2Replay`)
  - Local file path (e.g., `data/replays/hash_timestamp.SC2Replay`)
- Both formats work transparently in the application

---

## Testing Checklist

### Local Development (SQLite + Supabase)
- [ ] Upload a replay via `/queue`
- [ ] Verify replay appears in Supabase Storage bucket "replays"
- [ ] Check that `matches_1v1.replay_uploaded` is set to "Yes"
- [ ] Verify `replays.replay_path` contains Supabase URL
- [ ] Test fallback: Temporarily break Supabase connection, verify local storage works

### Production (PostgreSQL + Supabase)
- [ ] Upload a replay via `/queue`
- [ ] Verify replay appears in Supabase Storage
- [ ] Check database record contains Supabase URL
- [ ] Verify public URL is accessible

---

## Environment Configuration

Required environment variables:
```bash
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your_anon_public_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
SUPABASE_BUCKET_NAME=replays
```

---

## Supabase Bucket Setup

### 1. Create Bucket
```sql
-- In Supabase Dashboard → Storage
-- Create a new bucket named "replays"
-- Set to public or configure RLS as needed
```

### 2. Configure Policies (Optional)
If using RLS, create policies to allow:
- Public read access
- Service role write access

---

## Files Modified

1. `src/backend/services/replay_service.py`
   - Modified `save_replay()` method
   - Modified `store_upload_from_parsed_dict()` method

2. `src/backend/services/storage_service.py`
   - Already had `upload_replay()` method (no changes needed)

3. `src/bot/config.py`
   - Already had Supabase configuration (no changes needed)

4. `requirements.txt`
   - Already had `supabase>=2.3.0` (no changes needed)

---

## Next Steps

1. **Test the integration**:
   - Upload a replay locally
   - Verify it appears in Supabase Storage
   - Check database records

2. **Deploy to Railway**:
   - Push changes to GitHub
   - Verify Railway deployment succeeds
   - Test replay uploads in production

3. **Monitor logs**:
   - Watch for `[Replay]` and `[Storage]` log messages
   - Verify uploads are successful
   - Check for any fallback to local storage

---

## Rollback Plan

If issues occur:
1. The fallback to local storage ensures the bot remains functional
2. To disable Supabase uploads temporarily:
   - Comment out the Supabase upload attempt in `save_replay()`
   - Or remove `SUPABASE_URL` from environment variables (will cause startup failure)

---

## Benefits

✓ **Cloud Storage**: Replays stored in scalable cloud storage  
✓ **Public URLs**: Easy sharing and access  
✓ **Automatic Cleanup**: Can implement retention policies via Supabase  
✓ **No Local Disk**: Railway doesn't need to store large files  
✓ **Failsafe**: Local fallback ensures reliability  
✓ **Idempotent**: Upsert prevents duplicate files  

---

**Implementation Complete**: Ready for testing! 🚀

