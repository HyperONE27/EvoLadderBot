"""
Administrative service for live bot inspection and control.

This service handles all admin operations with proper synchronization between
database and in-memory DataFrames. All modifications update both layers atomically.

IMPORTANT: This service contains ONLY business logic and returns raw data.
All Discord-specific formatting, embeds, and notifications are handled by the frontend.
"""

import asyncio
import time
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import polars as pl

from src.backend.services.data_access_service import DataAccessService


class AdminService:
    """
    Administrative functions for live bot inspection and control.
    
    All methods are designed to work with the in-memory architecture and
    handle synchronization between database and DataFrames.
    
    Three layers of operations:
    - Layer 1: Read-only inspection (safe, no state changes)
    - Layer 2: Controlled modifications (atomic updates to DB + memory)
    - Layer 3: Emergency controls (nuclear options, use with caution)
    """
    
    def __init__(self):
        self.data_service = DataAccessService()
        self.action_log = []
    
    async def resolve_user(self, user_input: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a user input (mention, username, or ID) to player info.
        
        Args:
            user_input: Can be "@username", "<@123456>", "username", or "123456"
            
        Returns:
            Dict with 'discord_uid' and 'player_name' if found, None otherwise
        """
        discord_uid = None
        
        # Try to parse as mention (<@123456> or <@!123456>)
        if user_input.startswith('<@') and user_input.endswith('>'):
            user_id_str = user_input[2:-1]
            if user_id_str.startswith('!'):
                user_id_str = user_id_str[1:]
            try:
                discord_uid = int(user_id_str)
            except ValueError:
                pass
        
        # Try to parse as numeric ID
        if discord_uid is None:
            try:
                discord_uid = int(user_input)
            except ValueError:
                pass
        
        # Try to look up by username (remove @ if present)
        if discord_uid is None:
            username = user_input.lstrip('@')
            
            # Search in DataAccessService players
            if self.data_service._players_df is not None:
                matches = self.data_service._players_df.filter(
                    pl.col('discord_username').str.to_lowercase() == username.lower()
                )
                if len(matches) > 0:
                    discord_uid = matches[0, 'discord_uid']
        
        if discord_uid is None:
            return None
        
        # Get player info
        player_info = self.data_service.get_player_info(discord_uid)
        if player_info:
            return {
                'discord_uid': discord_uid,
                'player_name': player_info.get('player_name', 'Unknown')
            }
        
        return {'discord_uid': discord_uid, 'player_name': 'Unknown'}
    
    # ========== LAYER 1: READ-ONLY INSPECTION ==========
    
    def get_system_snapshot(self) -> dict:
        """
        Get complete system state snapshot for debugging.
        
        Returns:
            Comprehensive dict with all system state including memory usage,
            DataFrame statistics, queue status, active matches, write queue depth,
            and process pool health.
        """
        from src.backend.services.queue_service import get_queue_service
        from src.backend.services.match_completion_service import match_completion_service
        from src.backend.services.app_context import ranking_service
        
        queue_service = get_queue_service()
        
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'memory': self._get_memory_stats(),
            'data_frames': self._get_dataframe_stats(),
            'queue': {
                'size': queue_service.get_queue_size() if queue_service else 0,
                'players': self._get_queue_snapshot(queue_service) if queue_service else []
            },
            'matches': {
                'active': len(match_completion_service.monitored_matches),
                'list': list(match_completion_service.monitored_matches)
            },
            'write_queue': {
                'depth': self.data_service._write_queue.qsize(),
                'total_completed': self.data_service._total_writes_completed,
                'total_queued': self.data_service._total_writes_queued
            },
            'process_pool': self._get_process_pool_stats(),
            'ranking_cache': {
                'size': len(ranking_service._rankings) if ranking_service else 0
            }
        }
    
    def _get_memory_stats(self) -> dict:
        """Get memory usage statistics."""
        try:
            import psutil
            process = psutil.Process()
            mem = process.memory_info()
            
            return {
                'rss_mb': mem.rss / 1024 / 1024,
                'vms_mb': mem.vms / 1024 / 1024,
                'percent': process.memory_percent(),
                'available_mb': psutil.virtual_memory().available / 1024 / 1024
            }
        except ImportError:
            return {'error': 'psutil not installed'}
    
    def _get_dataframe_stats(self) -> dict:
        """Get statistics about in-memory DataFrames."""
        stats = {}
        
        if self.data_service._players_df is not None:
            stats['players'] = {
                'rows': len(self.data_service._players_df),
                'size_mb': self.data_service._players_df.estimated_size('mb'),
                'columns': self.data_service._players_df.columns
            }
        
        if self.data_service._mmrs_1v1_df is not None:
            stats['mmrs_1v1'] = {
                'rows': len(self.data_service._mmrs_1v1_df),
                'size_mb': self.data_service._mmrs_1v1_df.estimated_size('mb'),
                'columns': self.data_service._mmrs_1v1_df.columns
            }
        
        if self.data_service._matches_1v1_df is not None:
            stats['matches_1v1'] = {
                'rows': len(self.data_service._matches_1v1_df),
                'size_mb': self.data_service._matches_1v1_df.estimated_size('mb'),
                'columns': self.data_service._matches_1v1_df.columns
            }
        
        if self.data_service._replays_df is not None:
            stats['replays'] = {
                'rows': len(self.data_service._replays_df),
                'size_mb': self.data_service._replays_df.estimated_size('mb'),
                'columns': self.data_service._replays_df.columns
            }
        
        return stats
    
    def _get_queue_snapshot(self, queue_service) -> list:
        """Get list of players currently in queue."""
        if not queue_service:
            return []
        
        players = queue_service.get_snapshot()
        return [
            {
                'discord_id': p.discord_user_id,
                'user_id': p.user_id,
                'races': p.preferences.selected_races,
                'wait_time': time.time() - p.queue_start_time,
                'wait_cycles': p.wait_cycles
            }
            for p in players
        ]
    
    def _get_process_pool_stats(self) -> dict:
        """Get process pool statistics."""
        try:
            from src.backend.services.process_pool_health import _bot_instance
            
            if _bot_instance and hasattr(_bot_instance, 'process_pool'):
                return {
                    'exists': True,
                    'workers': _bot_instance.process_pool._max_workers if _bot_instance.process_pool else 0,
                    'restart_count': getattr(_bot_instance, '_pool_restart_count', 0)
                }
        except ImportError:
            pass
        
        return {'exists': False}
    
    def get_conflict_matches(self) -> list:
        """
        Get all matches with conflicting reports (match_result = -2).
        
        Returns:
            List of conflict match dicts with full details including player info,
            races, reports, replays, and match metadata.
        """
        if self.data_service._matches_1v1_df is None:
            return []
        
        conflicts = self.data_service._matches_1v1_df.filter(
            pl.col('match_result') == -2
        )
        
        result = []
        for row in conflicts.iter_rows(named=True):
            p1_info = self.data_service.get_player_info(row['player_1_discord_uid'])
            p2_info = self.data_service.get_player_info(row['player_2_discord_uid'])
            
            p1_replay = row.get('player_1_replay_path')
            p2_replay = row.get('player_2_replay_path')
            
            result.append({
                'match_id': row['id'],
                'player_1': {
                    'discord_uid': row['player_1_discord_uid'],
                    'name': p1_info.get('player_name') if p1_info else 'Unknown',
                    'race': row['player_1_race'],
                    'report': row.get('player_1_report'),
                    'replay': p1_replay
                },
                'player_2': {
                    'discord_uid': row['player_2_discord_uid'],
                    'name': p2_info.get('player_name') if p2_info else 'Unknown',
                    'race': row['player_2_race'],
                    'report': row.get('player_2_report'),
                    'replay': p2_replay
                },
                'map': row['map_played'],
                'server': row['server_used'],
                'played_at': row['played_at'],
                'status': row.get('status', 'UNKNOWN')
            })
        
        return result
    
    async def get_player_full_state(self, discord_uid: int) -> dict:
        """
        Get complete state for a player (for debugging stuck states).
        
        Args:
            discord_uid: Player's Discord ID
            
        Returns:
            Dict with all player state information including basic info, MMRs,
            queue status, active matches, and recent match history.
        """
        from src.backend.services.queue_service import get_queue_service
        
        queue_service = get_queue_service()
        
        player_info = self.data_service.get_player_info(discord_uid)
        
        mmrs = {}
        if self.data_service._mmrs_1v1_df is not None:
            player_mmrs = self.data_service._mmrs_1v1_df.filter(
                pl.col('discord_uid') == discord_uid
            )
            for row in player_mmrs.iter_rows(named=True):
                mmrs[row['race']] = {
                    'mmr': row['mmr'],
                    'games_played': row['games_played'],
                    'games_won': row['games_won'],
                    'games_lost': row['games_lost'],
                    'games_drawn': row['games_drawn']
                }
        
        in_queue = False
        queue_info = None
        if queue_service:
            in_queue = await queue_service.is_player_in_queue(discord_uid)
            if in_queue:
                player_obj = await queue_service.get_player(discord_uid)
                if player_obj:
                    queue_info = {
                        'races': player_obj.preferences.selected_races,
                        'wait_time': time.time() - player_obj.queue_start_time,
                        'wait_cycles': player_obj.wait_cycles
                    }
        
        active_matches = []
        if self.data_service._matches_1v1_df is not None:
            player_matches = self.data_service._matches_1v1_df.filter(
                (pl.col('player_1_discord_uid') == discord_uid) |
                (pl.col('player_2_discord_uid') == discord_uid)
            ).filter(
                pl.col('status').is_in(['IN_PROGRESS', 'PROCESSING_COMPLETION'])
            )
            
            for row in player_matches.iter_rows(named=True):
                active_matches.append({
                    'match_id': row['id'],
                    'status': row.get('status'),
                    'is_player_1': row['player_1_discord_uid'] == discord_uid,
                    'opponent_id': row['player_2_discord_uid'] if row['player_1_discord_uid'] == discord_uid else row['player_1_discord_uid'],
                    'my_report': row.get('player_1_report') if row['player_1_discord_uid'] == discord_uid else row.get('player_2_report'),
                    'their_report': row.get('player_2_report') if row['player_1_discord_uid'] == discord_uid else row.get('player_1_report'),
                    'match_result': row.get('match_result')
                })
        
        recent_matches = []
        if self.data_service._matches_1v1_df is not None:
            recent = self.data_service._matches_1v1_df.filter(
                (pl.col('player_1_discord_uid') == discord_uid) |
                (pl.col('player_2_discord_uid') == discord_uid)
            ).sort('played_at', descending=True).head(10)
            
            for row in recent.iter_rows(named=True):
                recent_matches.append({
                    'match_id': row['id'],
                    'result': row.get('match_result'),
                    'status': row.get('status'),
                    'played_at': row['played_at']
                })
        
        return {
            'player_info': player_info,
            'mmrs': mmrs,
            'queue_status': {
                'in_queue': in_queue,
                'details': queue_info
            },
            'active_matches': active_matches,
            'recent_matches': recent_matches
        }
    
    def get_match_full_state(self, match_id: int) -> dict:
        """
        Get complete state for a match (for debugging completion issues).
        
        Args:
            match_id: Match ID
            
        Returns:
            Dict with all match state information including match data, player info,
            monitoring status, reports, and replay paths.
        """
        from src.backend.services.match_completion_service import match_completion_service
        
        match_data = self.data_service.get_match(match_id)
        
        if not match_data:
            return {'error': 'Match not found in memory'}
        
        is_monitored = match_id in match_completion_service.monitored_matches
        is_processed = match_id in match_completion_service.processed_matches
        has_waiter = match_id in match_completion_service.completion_waiters
        has_lock = match_id in match_completion_service.processing_locks
        
        p1_info = self.data_service.get_player_info(match_data['player_1_discord_uid'])
        p2_info = self.data_service.get_player_info(match_data['player_2_discord_uid'])
        
        return {
            'match_data': match_data,
            'players': {
                'player_1': p1_info,
                'player_2': p2_info
            },
            'monitoring': {
                'is_monitored': is_monitored,
                'is_processed': is_processed,
                'has_waiter': has_waiter,
                'has_lock': has_lock
            },
            'reports': {
                'player_1': match_data.get('player_1_report'),
                'player_2': match_data.get('player_2_report'),
                'match_result': match_data.get('match_result'),
                'status': match_data.get('status')
            },
            'replays': {
                'player_1': match_data.get('player_1_replay_path'),
                'player_2': match_data.get('player_2_replay_path')
            }
        }
    
    
    # ========== LAYER 2: CONTROLLED MODIFICATIONS ==========
    
    async def resolve_match_conflict(
        self,
        match_id: int,
        resolution: str,
        admin_discord_id: int,
        reason: str = ""
    ) -> dict:
        """
        Resolve a match conflict by admin decision.
        
        This method:
        1. Updates database
        2. Updates in-memory DataFrame
        3. Triggers MMR calculation (if applicable)
        4. Notifies players
        5. Logs admin action
        
        Args:
            match_id: Match ID with conflict
            resolution: How to resolve ('player_1_win', 'player_2_win', 'draw', 'invalidate')
            admin_discord_id: Admin performing action
            reason: Explanation for audit log
            
        Returns:
            Dict with success status and details
        """
        from src.backend.services.matchmaking_service import matchmaker
        from src.backend.services.match_completion_service import match_completion_service
        
        match_data = self.data_service.get_match(match_id)
        if not match_data:
            return {'success': False, 'error': 'Match not found'}
        
        if match_data.get('match_result') != -2:
            return {'success': False, 'error': 'Match is not in conflict state'}
        
        resolution_map = {
            'player_1_win': 1,
            'player_2_win': 2,
            'draw': 0,
            'invalidate': -1
        }
        
        if resolution not in resolution_map:
            return {'success': False, 'error': 'Invalid resolution'}
        
        new_result = resolution_map[resolution]
        
        try:
            # Use DataAccessService facade for proper memory + DB update
            await self.data_service.update_match(
                match_id=match_id,
                match_result=new_result,
                status='PROCESSING_COMPLETION'
            )
            print(f"[AdminService] Updated match {match_id} via DataAccessService: result={new_result}")
            
            mmr_change = 0
            if resolution != 'invalidate':
                print(f"[AdminService] Triggering MMR calculation for match {match_id}")
                mmr_change = await matchmaker._calculate_and_write_mmr(match_id, match_data)
                print(f"[AdminService] MMR calculated: {mmr_change:+} (player 1 perspective)")
            else:
                print(f"[AdminService] Match invalidated, no MMR change")
            
            print(f"[AdminService] Triggering completion notification for match {match_id}")
            asyncio.create_task(match_completion_service.check_match_completion(match_id))
            
            await self._log_admin_action(
                admin_discord_id=admin_discord_id,
                action_type='resolve_conflict',
                target_match_id=match_id,
                details={
                    'resolution': resolution,
                    'new_result': new_result,
                    'mmr_change': mmr_change,
                    'reason': reason
                }
            )
            
            # Return notification data for frontend to handle
            admin_info = self.data_service.get_player_info(admin_discord_id)
            p1_uid = match_data['player_1_discord_uid']
            p2_uid = match_data['player_2_discord_uid']
            
            return {
                'success': True,
                'match_id': match_id,
                'resolution': resolution,
                'mmr_change': mmr_change,
                'notification_data': {
                    'players': [p1_uid, p2_uid],
                    'admin_name': admin_info.get('player_name', 'Admin') if admin_info else 'Admin',
                    'reason': reason,
                    'match_id': match_id,
                    'resolution': resolution,
                    'mmr_change': mmr_change
                }
            }
            
        except Exception as e:
            print(f"[AdminService] ERROR resolving conflict for match {match_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def adjust_player_mmr(
        self,
        discord_uid: int,
        race: str,
        operation: str,
        value: int,
        admin_discord_id: int,
        reason: str
    ) -> dict:
        """
        Adjust a player's MMR (for corrections, penalties, etc.).
        
        This method:
        1. Updates database
        2. Updates in-memory DataFrame
        3. Invalidates leaderboard cache
        4. Logs admin action
        
        Args:
            discord_uid: Player's Discord ID
            race: Race to adjust
            operation: Operation type ('set', 'add', 'subtract')
            value: Value to set/add/subtract
            admin_discord_id: Admin performing action
            reason: Explanation for audit log
            
        Returns:
            Dict with success status and details
        """
        try:
            current_mmr = self.data_service.get_player_mmr(discord_uid, race)
            if current_mmr is None:
                return {'success': False, 'error': 'Player/race not found'}
            
            # Calculate new MMR based on operation
            if operation == 'set':
                new_mmr = value
            elif operation == 'add':
                new_mmr = current_mmr + value
            elif operation == 'subtract':
                new_mmr = current_mmr - value
            else:
                return {'success': False, 'error': f'Invalid operation: {operation}'}
            
            # Ensure MMR doesn't go negative
            if new_mmr < 0:
                return {'success': False, 'error': f'Operation would result in negative MMR ({new_mmr})'}
            
            # Use DataAccessService facade for proper memory + DB update
            # Pass None for game stats to keep them unchanged (admin adjustments don't affect win/loss records)
            await self.data_service.update_player_mmr(
                discord_uid=discord_uid,
                race=race,
                new_mmr=new_mmr,
                games_played=None,  # Don't update game stats
                games_won=None,
                games_lost=None,
                games_drawn=None
            )
            print(f"[AdminService] Updated MMR via DataAccessService: {discord_uid}/{race}: {current_mmr} -> {new_mmr} (operation: {operation} {value})")
            
            from src.backend.services.app_context import leaderboard_service
            leaderboard_service.invalidate_cache()
            print(f"[AdminService] Invalidated leaderboard cache")
            
            from src.backend.services.app_context import ranking_service
            if ranking_service:
                await ranking_service.trigger_refresh()
                print(f"[AdminService] Refreshed ranking service")
            
            await self._log_admin_action(
                admin_discord_id=admin_discord_id,
                action_type='adjust_mmr',
                target_player_uid=discord_uid,
                details={
                    'race': race,
                    'operation': operation,
                    'value': value,
                    'old_mmr': current_mmr,
                    'new_mmr': new_mmr,
                    'change': new_mmr - current_mmr,
                    'reason': reason
                }
            )
            
            # Return notification data for frontend to handle
            player_info = self.data_service.get_player_info(discord_uid)
            admin_info = self.data_service.get_player_info(admin_discord_id)
            
            return {
                'success': True,
                'discord_uid': discord_uid,
                'race': race,
                'old_mmr': current_mmr,
                'new_mmr': new_mmr,
                'change': new_mmr - current_mmr,
                'notification_data': {
                    'player_uid': discord_uid,
                    'player_name': player_info.get('player_name', 'Player') if player_info else 'Player',
                    'admin_name': admin_info.get('player_name', 'Admin') if admin_info else 'Admin',
                    'operation': operation,
                    'value': value,
                    'reason': reason
                }
            }
            
        except Exception as e:
            print(f"[AdminService] ERROR adjusting MMR: {e}")
            return {'success': False, 'error': str(e)}
    
    async def force_remove_from_queue(
        self,
        discord_uid: int,
        admin_discord_id: int,
        reason: str
    ) -> dict:
        """
        Force remove a player from queue (for stuck states).
        
        Args:
            discord_uid: Player to remove
            admin_discord_id: Admin performing action
            reason: Explanation for audit log
            
        Returns:
            Dict with success status
        """
        from src.backend.services.matchmaking_service import matchmaker
        
        try:
            # Check if player is in queue first
            was_in_queue = await matchmaker.is_player_in_queue(discord_uid)
            
            if was_in_queue:
                # Remove from matchmaker (which syncs to QueueService automatically)
                await matchmaker.remove_player(discord_uid)
                print(f"[AdminService] Removed player {discord_uid} from matchmaking queue")
                
                await self._log_admin_action(
                    admin_discord_id=admin_discord_id,
                    action_type='force_remove_queue',
                    target_player_uid=discord_uid,
                    details={'reason': reason}
                )
                
                # Return notification data for frontend to handle
                player_info = self.data_service.get_player_info(discord_uid)
                admin_info = self.data_service.get_player_info(admin_discord_id)
                
                return {
                    'success': True,
                    'discord_uid': discord_uid,
                    'was_in_queue': True,
                    'notification_data': {
                        'player_uid': discord_uid,
                        'player_name': player_info.get('player_name', 'Player') if player_info else 'Player',
                        'admin_name': admin_info.get('player_name', 'Admin') if admin_info else 'Admin',
                        'reason': reason
                    }
                }
            else:
                return {
                    'success': False,
                    'error': 'Player was not in queue'
                }
        
        except Exception as e:
            print(f"[AdminService] ERROR removing from queue: {e}")
            return {'success': False, 'error': str(e)}
    
    async def reset_player_aborts(
        self,
        discord_uid: int,
        new_count: int,
        admin_discord_id: int,
        reason: str
    ) -> dict:
        """
        Reset a player's abort count.
        
        Args:
            discord_uid: Player to modify
            new_count: New abort count
            admin_discord_id: Admin performing action
            reason: Explanation for audit log
            
        Returns:
            Dict with success status
        """
        try:
            current = self.data_service.get_remaining_aborts(discord_uid)
            
            await self.data_service.update_remaining_aborts(discord_uid, new_count)
            
            await self._log_admin_action(
                admin_discord_id=admin_discord_id,
                action_type='reset_aborts',
                target_player_uid=discord_uid,
                details={
                    'old_count': current,
                    'new_count': new_count,
                    'reason': reason
                }
            )
            
            # Return notification data for frontend to handle
            player_info = self.data_service.get_player_info(discord_uid)
            admin_info = self.data_service.get_player_info(admin_discord_id)
            
            return {
                'success': True,
                'discord_uid': discord_uid,
                'old_count': current,
                'new_count': new_count,
                'notification_data': {
                    'player_uid': discord_uid,
                    'player_name': player_info.get('player_name', 'Player') if player_info else 'Player',
                    'admin_name': admin_info.get('player_name', 'Admin') if admin_info else 'Admin',
                    'reason': reason
                }
            }
            
        except Exception as e:
            print(f"[AdminService] ERROR resetting aborts: {e}")
            return {'success': False, 'error': str(e)}
    
    # ========== LAYER 3: EMERGENCY CONTROLS ==========
    
    async def emergency_clear_queue(
        self,
        admin_discord_id: int,
        reason: str
    ) -> dict:
        """
        Emergency: Clear entire matchmaking queue.
        
        WARNING: Removes all players from queue immediately.
        Use only if queue is in corrupted state.
        
        Args:
            admin_discord_id: Admin performing action
            reason: Explanation for audit log
            
        Returns:
            Dict with count of removed players
        """
        from src.backend.services.matchmaking_service import matchmaker
        from src.backend.services.queue_service import get_queue_service
        
        try:
            # Get all player IDs from matchmaker before clearing
            async with matchmaker.lock:
                player_ids = [p.discord_user_id for p in matchmaker.players]
                count = len(player_ids)
                matchmaker.players.clear()
                print(f"[AdminService] EMERGENCY: Cleared matchmaker queue ({count} players)")
            
            # Also clear QueueService to ensure full sync
            queue_service = get_queue_service()
            if queue_service:
                await queue_service.clear_queue()
                print(f"[AdminService] EMERGENCY: Cleared QueueService")
            
            await self._log_admin_action(
                admin_discord_id=admin_discord_id,
                action_type='emergency_clear_queue',
                details={
                    'players_removed': count,
                    'player_ids': player_ids,
                    'reason': reason
                }
            )
            
            # Return notification data for frontend to handle
            admin_info = self.data_service.get_player_info(admin_discord_id)
            
            return {
                'success': True,
                'players_removed': count,
                'notification_data': {
                    'player_uids': player_ids,
                    'admin_name': admin_info.get('player_name', 'Admin') if admin_info else 'Admin',
                    'reason': reason
                }
            }
            
        except Exception as e:
            print(f"[AdminService] ERROR clearing queue: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _log_admin_action(
        self,
        admin_discord_id: int,
        action_type: str,
        target_player_uid: Optional[int] = None,
        target_match_id: Optional[int] = None,
        details: Optional[dict] = None
    ) -> None:
        """
        Log admin action to database for audit trail.
        
        Args:
            admin_discord_id: Admin who performed action
            action_type: Type of action
            target_player_uid: Player affected (if applicable)
            target_match_id: Match affected (if applicable)
            details: JSON-serializable dict with action details
        """
        admin_info = self.data_service.get_player_info(admin_discord_id)
        admin_name = admin_info.get('player_name', 'Unknown') if admin_info else 'Unknown'
        
        # Use DataAccessService facade for proper async write queuing
        await self.data_service.log_admin_action(
            admin_discord_uid=admin_discord_id,
            admin_username=admin_name,
            action_type=action_type,
            target_player_uid=target_player_uid,
            target_match_id=target_match_id,
            action_details=details,
            reason=details.get('reason', '') if details else None
        )
        
        print(f"[AdminService] Logged admin action: {action_type} by {admin_name}")


admin_service = AdminService()

