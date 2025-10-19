# Supabase Storage Integration Plan - Replay Files

**Date**: October 19, 2025  
**Status**: Planning  
**Supabase Bucket**: `replays`

## Current State Analysis

### How Replays Are Currently Stored
Need to investigate:
1. Where replay files are stored now (local filesystem?)
2. How users upload replays
3. What metadata is stored in database
4. How replays are retrieved/downloaded

### Supabase Storage Structure
```
Supabase Storage Bucket: "replays"
├── {match_id}/
│   ├── player_1_{discord_uid}.SC2Replay
│   └── player_2_{discord_uid}.SC2Replay
```

---

## Solution Architecture

### 1. Add Supabase Storage Client

**Install Dependencies:**
```bash
pip install supabase
```

**Environment Variables (.env):**
```bash
# Supabase Configuration
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_anon_key_here  # From Supabase dashboard
SUPABASE_BUCKET_NAME=replays
```

### 2. Create Storage Service

**File: `src/backend/services/storage_service.py`**
```python
from typing import Optional
import os
from supabase import create_client, Client
from src.bot.config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_BUCKET_NAME

class StorageService:
    """Handle file uploads to Supabase Storage."""
    
    def __init__(self):
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.bucket_name = SUPABASE_BUCKET_NAME
    
    def upload_replay(
        self,
        match_id: int,
        player_discord_uid: int,
        file_data: bytes,
        filename: str
    ) -> Optional[str]:
        """
        Upload replay file to Supabase Storage.
        
        Args:
            match_id: Match ID
            player_discord_uid: Player's Discord UID
            file_data: Replay file bytes
            filename: Original filename
            
        Returns:
            Public URL of uploaded file, or None if failed
        """
        # Path in bucket: {match_id}/player_{discord_uid}.SC2Replay
        file_path = f"{match_id}/player_{player_discord_uid}.SC2Replay"
        
        try:
            # Upload to Supabase Storage
            response = self.supabase.storage.from_(self.bucket_name).upload(
                path=file_path,
                file=file_data,
                file_options={
                    "content-type": "application/octet-stream",
                    "upsert": True  # Overwrite if exists
                }
            )
            
            # Get public URL
            public_url = self.supabase.storage.from_(self.bucket_name).get_public_url(file_path)
            
            return public_url
            
        except Exception as e:
            print(f"Error uploading replay: {e}")
            return None
    
    def download_replay(
        self,
        match_id: int,
        player_discord_uid: int
    ) -> Optional[bytes]:
        """Download replay file from Supabase Storage."""
        file_path = f"{match_id}/player_{player_discord_uid}.SC2Replay"
        
        try:
            response = self.supabase.storage.from_(self.bucket_name).download(file_path)
            return response
        except Exception as e:
            print(f"Error downloading replay: {e}")
            return None
    
    def get_replay_url(
        self,
        match_id: int,
        player_discord_uid: int
    ) -> str:
        """Get public URL for replay file."""
        file_path = f"{match_id}/player_{player_discord_uid}.SC2Replay"
        return self.supabase.storage.from_(self.bucket_name).get_public_url(file_path)
```

### 3. Update Database Schema

**Add to `replays` table (if not exists):**
```sql
-- Public URL to replay file in Supabase Storage
ALTER TABLE replays ADD COLUMN IF NOT EXISTS storage_url TEXT;

-- For matches_1v1 table
ALTER TABLE matches_1v1 ADD COLUMN IF NOT EXISTS player_1_replay_url TEXT;
ALTER TABLE matches_1v1 ADD COLUMN IF NOT EXISTS player_2_replay_url TEXT;
```

### 4. Update Replay Upload Flow

**Current Flow (assuming):**
```
User uploads file → Discord attachment → Save to disk → Process
```

**New Flow:**
```
User uploads file → Discord attachment → Upload to Supabase → Save URL to DB → Process
```

**Implementation:**
```python
# In match result reporting view
async def handle_replay_upload(self, interaction: discord.Interaction):
    # Get attachment from Discord
    attachment = interaction.message.attachments[0]
    
    # Download file data
    file_data = await attachment.read()
    
    # Upload to Supabase
    storage_service = StorageService()
    public_url = storage_service.upload_replay(
        match_id=self.match_id,
        player_discord_uid=interaction.user.id,
        file_data=file_data,
        filename=attachment.filename
    )
    
    if public_url:
        # Save URL to database
        db_writer.update_match_replay_1v1(
            match_id=self.match_id,
            player_discord_uid=interaction.user.id,
            replay_url=public_url,
            replay_time=get_timestamp()
        )
        return True
    return False
```

---

## Migration Steps

### 1. Enable Supabase Storage
```sql
-- In Supabase SQL Editor
-- 1. Create bucket (if not exists)
-- This is done via Supabase Dashboard: Storage → Create Bucket → "replays"

-- 2. Set bucket to public (if replays should be public)
UPDATE storage.buckets SET public = true WHERE name = 'replays';

-- 3. Set up RLS policies
CREATE POLICY "Allow public read access"
ON storage.objects FOR SELECT
USING (bucket_id = 'replays');

CREATE POLICY "Allow authenticated uploads"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'replays' AND auth.role() = 'authenticated');
```

### 2. Update Environment Variables
```bash
# Add to Railway and local .env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_anon_key_here
SUPABASE_BUCKET_NAME=replays
```

### 3. Update Config
```python
# src/bot/config.py
SUPABASE_URL = _get_required_env("SUPABASE_URL")
SUPABASE_KEY = _get_required_env("SUPABASE_KEY")
SUPABASE_BUCKET_NAME = os.getenv("SUPABASE_BUCKET_NAME", "replays")
```

### 4. Migrate Existing Replays (Optional)
If you have existing replays on disk:
```python
# migration_script.py
def migrate_local_replays_to_supabase():
    storage = StorageService()
    db_reader = DatabaseReader()
    
    # Get all replays from DB
    replays = db_reader.execute_query("SELECT * FROM replays WHERE storage_url IS NULL")
    
    for replay in replays:
        if os.path.exists(replay['replay_path']):
            with open(replay['replay_path'], 'rb') as f:
                file_data = f.read()
            
            url = storage.upload_replay(
                match_id=replay['match_id'],
                player_discord_uid=replay['player_discord_uid'],
                file_data=file_data,
                filename=os.path.basename(replay['replay_path'])
            )
            
            if url:
                # Update database
                db_writer.execute_write(
                    "UPDATE replays SET storage_url = :url WHERE id = :id",
                    {"url": url, "id": replay['id']}
                )
```

---

## Testing

### Local Testing
```python
# test_storage_service.py
def test_upload_replay():
    storage = StorageService()
    
    # Read test replay file
    with open('test.SC2Replay', 'rb') as f:
        file_data = f.read()
    
    # Upload
    url = storage.upload_replay(
        match_id=123,
        player_discord_uid=456,
        file_data=file_data,
        filename='test.SC2Replay'
    )
    
    assert url is not None
    print(f"Uploaded to: {url}")
```

---

## Benefits

1. **Scalable Storage** - No disk space limits on Railway
2. **CDN Distribution** - Fast downloads globally
3. **Backup** - Supabase handles backups
4. **Access Control** - Fine-grained permissions via RLS
5. **Cost Effective** - Pay for what you use

---

## Security Considerations

1. **File Size Limits** - Set max file size (SC2 replays usually <1MB)
2. **File Type Validation** - Only allow .SC2Replay files
3. **Rate Limiting** - Prevent spam uploads
4. **Signed URLs** - Use signed URLs for private replays

```python
def upload_replay_with_validation(self, file_data: bytes, filename: str) -> Optional[str]:
    # Validate file extension
    if not filename.endswith('.SC2Replay'):
        raise ValueError("Only .SC2Replay files allowed")
    
    # Validate file size (max 5MB)
    if len(file_data) > 5 * 1024 * 1024:
        raise ValueError("File too large (max 5MB)")
    
    # Upload
    return self.upload_replay(...)
```

---

## Rollout Plan

1. **Phase 1**: Create storage service (1 hour)
2. **Phase 2**: Update config with Supabase credentials (15 min)
3. **Phase 3**: Wire up replay upload flow (1-2 hours)
4. **Phase 4**: Test with sample replays (30 min)
5. **Phase 5**: Deploy to Railway (15 min)
6. **Phase 6**: Migrate existing replays (optional, 1 hour)

**Total Time**: 3-4 hours

