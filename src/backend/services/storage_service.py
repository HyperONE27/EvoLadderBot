"""
Supabase Storage Service for file uploads (primarily replay files).

Handles uploading, downloading, and managing files in Supabase Storage buckets.
"""

from typing import Optional
import os
from datetime import datetime


class StorageService:
    """Handle file uploads to Supabase Storage."""
    
    def __init__(self):
        """Initialize Supabase storage client."""
        from supabase import create_client, Client
        from src.bot.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_BUCKET_NAME
        
        # Use service role key for admin operations (can bypass RLS)
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        self.bucket_name = SUPABASE_BUCKET_NAME
        print(f"[Storage] Initialized with bucket: {self.bucket_name}")
    
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
            # Upload to Supabase Storage
            print(f"[Storage] Uploading replay to: {file_path}")
            
            # Attempt upload
            try:
                response = self.supabase.storage.from_(self.bucket_name).upload(
                    path=file_path,
                    file=file_data,
                    file_options={"content-type": "application/octet-stream"}
                )
            except Exception as upload_error:
                # If file already exists (409 Duplicate), remove and retry
                error_str = str(upload_error)
                if "409" in error_str or "Duplicate" in error_str or "already exists" in error_str:
                    print(f"[Storage] File exists, removing and re-uploading...")
                    try:
                        self.supabase.storage.from_(self.bucket_name).remove([file_path])
                    except:
                        pass  # Ignore errors during removal
                    
                    # Retry upload
                    response = self.supabase.storage.from_(self.bucket_name).upload(
                        path=file_path,
                        file=file_data,
                        file_options={"content-type": "application/octet-stream"}
                    )
                else:
                    raise  # Re-raise if it's a different error
            
            # Get public URL
            public_url = self.supabase.storage.from_(self.bucket_name).get_public_url(file_path)
            
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
            response = self.supabase.storage.from_(self.bucket_name).download(file_path)
            print(f"[Storage] ✓ Download successful: {len(response)} bytes")
            return response
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
        return self.supabase.storage.from_(self.bucket_name).get_public_url(file_path)
    
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
            self.supabase.storage.from_(self.bucket_name).remove([file_path])
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
            folder_path = f"{match_id}/"
            response = self.supabase.storage.from_(self.bucket_name).list(folder_path)
            return [item['name'] for item in response]
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
            self.supabase.storage.from_(self.bucket_name).upload(
                path=file_path,
                file=file_data,
                file_options={
                    "content-type": content_type,
                    "upsert": upsert
                }
            )
            
            public_url = self.supabase.storage.from_(self.bucket_name).get_public_url(file_path)
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
            buckets = self.supabase.storage.list_buckets()
            bucket = next((b for b in buckets if b['name'] == self.bucket_name), None)
            return bucket if bucket else {}
        except Exception as e:
            print(f"[Storage] ERROR getting bucket info: {e}")
            return {}


# Global singleton instance
storage_service = StorageService()

