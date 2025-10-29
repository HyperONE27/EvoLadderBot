"""
Supabase Storage Service for file uploads (primarily replay files).

Handles uploading, downloading, and managing files in Supabase Storage buckets.

NOTE: Uses direct HTTP API instead of supabase-py client to avoid creating
unnecessary database connections. The supabase-py client creates 10+ connections
to PostgREST/Realtime even when only using Storage.
"""

from typing import Optional
import os
from datetime import datetime
import httpx


class StorageService:
    """Handle file uploads to Supabase Storage using direct HTTP API."""
    
    def __init__(self):
        """Initialize Supabase storage client with HTTP-only approach."""
        from src.bot.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_BUCKET_NAME
        
        self.supabase_url = SUPABASE_URL
        self.service_role_key = SUPABASE_SERVICE_ROLE_KEY
        self.bucket_name = SUPABASE_BUCKET_NAME
        
        # Storage API endpoint (no database connections needed)
        self.storage_url = f"{SUPABASE_URL}/storage/v1"
        
        # HTTP headers for authentication
        self.headers = {
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "apikey": SUPABASE_SERVICE_ROLE_KEY
        }
        
        print(f"[Storage] Initialized with bucket: {self.bucket_name} (HTTP-only, no DB connections)")
    
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
        
        # Validate file size (max 10MB for safety, SC2 replays are typically <1MB)
        max_size = 10 * 1024 * 1024  # 10MB
        if len(file_data) > max_size:
            print(f"[Storage] ERROR: File too large: {len(file_data)} bytes (max {max_size})")
            return None
        
        # Path in bucket: {match_id}/{hash}_{timestamp}.SC2Replay
        # Use the provided filename which already follows the naming scheme
        file_path = f"{match_id}/{filename}"
        
        try:
            # Upload to Supabase Storage via direct HTTP API
            print(f"[Storage] Uploading replay to: {file_path}")
            
            upload_url = f"{self.storage_url}/object/{self.bucket_name}/{file_path}"
            
            with httpx.Client(timeout=30.0) as client:
                # Attempt upload
                response = client.post(
                    upload_url,
                    headers={
                        **self.headers,
                        "Content-Type": "application/octet-stream"
                    },
                    content=file_data
                )
                
                # If file already exists (409 Duplicate), remove and retry
                if response.status_code == 409:
                    print(f"[Storage] File exists, removing and re-uploading...")
                    
                    delete_url = f"{self.storage_url}/object/{self.bucket_name}/{file_path}"
                    client.delete(delete_url, headers=self.headers)
                    
                    # Retry upload
                    response = client.post(
                        upload_url,
                        headers={
                            **self.headers,
                            "Content-Type": "application/octet-stream"
                        },
                        content=file_data
                    )
                
                if response.status_code not in (200, 201):
                    raise Exception(f"Upload failed: {response.status_code} {response.text}")
            
            # Construct public URL
            public_url = f"{self.supabase_url}/storage/v1/object/public/{self.bucket_name}/{file_path}"
            
            print(f"[Storage] Upload successful: {public_url}")
            return public_url
            
        except Exception as e:
            print(f"[Storage] ERROR uploading replay: {e}")
            return None
    
    def download_replay(
        self,
        match_id: int,
        player_discord_uid: int
    ) -> Optional[bytes]:
        """
        Download replay file from Supabase Storage.
        
        Args:
            match_id: Match ID
            player_discord_uid: Player's Discord UID
            
        Returns:
            Replay file bytes, or None if failed
        """
        file_path = f"{match_id}/player_{player_discord_uid}.SC2Replay"
        
        try:
            print(f"[Storage] Downloading replay from: {file_path}")
            
            download_url = f"{self.storage_url}/object/{self.bucket_name}/{file_path}"
            
            with httpx.Client(timeout=30.0) as client:
                response = client.get(download_url, headers=self.headers)
                
                if response.status_code != 200:
                    raise Exception(f"Download failed: {response.status_code} {response.text}")
                
                file_bytes = response.content
                print(f"[Storage] ✓ Download successful: {len(file_bytes)} bytes")
                return file_bytes
                
        except Exception as e:
            print(f"[Storage] ERROR downloading replay: {e}")
            return None
    
    def get_replay_url(
        self,
        match_id: int,
        player_discord_uid: int
    ) -> str:
        """
        Get public URL for replay file.
        
        Args:
            match_id: Match ID
            player_discord_uid: Player's Discord UID
            
        Returns:
            Public URL to replay file
        """
        file_path = f"{match_id}/player_{player_discord_uid}.SC2Replay"
        return f"{self.supabase_url}/storage/v1/object/public/{self.bucket_name}/{file_path}"
    
    def delete_replay(
        self,
        match_id: int,
        player_discord_uid: int
    ) -> bool:
        """
        Delete replay file from Supabase Storage.
        
        Args:
            match_id: Match ID
            player_discord_uid: Player's Discord UID
            
        Returns:
            True if successful, False otherwise
        """
        file_path = f"{match_id}/player_{player_discord_uid}.SC2Replay"
        
        try:
            print(f"[Storage] Deleting replay: {file_path}")
            
            delete_url = f"{self.storage_url}/object/{self.bucket_name}/{file_path}"
            
            with httpx.Client(timeout=30.0) as client:
                response = client.delete(delete_url, headers=self.headers)
                
                if response.status_code not in (200, 204):
                    raise Exception(f"Delete failed: {response.status_code} {response.text}")
            
            print(f"[Storage] ✓ Deletion successful")
            return True
            
        except Exception as e:
            print(f"[Storage] ERROR deleting replay: {e}")
            return False
    
    def list_match_replays(self, match_id: int) -> list[str]:
        """
        List all replay files for a specific match.
        
        Args:
            match_id: Match ID
            
        Returns:
            List of file paths
        """
        try:
            folder_path = f"{match_id}"
            list_url = f"{self.storage_url}/object/list/{self.bucket_name}"
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    list_url,
                    headers=self.headers,
                    json={
                        "prefix": folder_path,
                        "limit": 100,
                        "offset": 0
                    }
                )
                
                if response.status_code != 200:
                    raise Exception(f"List failed: {response.status_code} {response.text}")
                
                items = response.json()
                return [item['name'] for item in items if 'name' in item]
                
        except Exception as e:
            print(f"[Storage] ERROR listing replays: {e}")
            return []
    
    def upload_generic_file(
        self,
        file_path: str,
        file_data: bytes,
        content_type: str = "application/octet-stream",
        upsert: bool = False
    ) -> Optional[str]:
        """
        Upload any file to Supabase Storage.
        
        Args:
            file_path: Path in bucket (e.g., "images/avatar.png")
            file_data: File bytes
            content_type: MIME type
            upsert: Whether to overwrite if exists
            
        Returns:
            Public URL of uploaded file, or None if failed
        """
        try:
            print(f"[Storage] Uploading file to: {file_path}")
            
            upload_url = f"{self.storage_url}/object/{self.bucket_name}/{file_path}"
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    upload_url,
                    headers={
                        **self.headers,
                        "Content-Type": content_type,
                        "x-upsert": "true" if upsert else "false"
                    },
                    content=file_data
                )
                
                if response.status_code not in (200, 201):
                    raise Exception(f"Upload failed: {response.status_code} {response.text}")
            
            public_url = f"{self.supabase_url}/storage/v1/object/public/{self.bucket_name}/{file_path}"
            print(f"[Storage] ✓ Upload successful: {public_url}")
            return public_url
            
        except Exception as e:
            print(f"[Storage] ERROR uploading file: {e}")
            return None
    
    def get_bucket_info(self) -> dict:
        """
        Get information about the storage bucket.
        
        Returns:
            Dictionary with bucket information
        """
        try:
            list_buckets_url = f"{self.storage_url}/bucket"
            
            with httpx.Client(timeout=30.0) as client:
                response = client.get(list_buckets_url, headers=self.headers)
                
                if response.status_code != 200:
                    raise Exception(f"List buckets failed: {response.status_code} {response.text}")
                
                buckets = response.json()
                bucket = next((b for b in buckets if b.get('name') == self.bucket_name), None)
                return bucket if bucket else {}
                
        except Exception as e:
            print(f"[Storage] ERROR getting bucket info: {e}")
            return {}


# Global singleton instance is created in app_context.py

