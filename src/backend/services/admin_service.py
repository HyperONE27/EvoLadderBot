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
from src.backend.services.app_context import mmr_service, races_service


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
    
    async def _clear_player_queue_lock(self, discord_uid: int) -> None:
        """
        Clear all queue-lock states for a player.
        
        This removes the player from:
        - queue_searching_view_manager (active queue views)
        - match_results (active match results)
        - channel_to_match_view_map (active match views)
        
        Args:
            discord_uid: Player's Discord ID
        """
        try:
            from src.bot.commands.queue_command import (
                queue_searching_view_manager,
                match_results,
                channel_to_match_view_map
            )
            
            # Clear from queue searching view manager
            await queue_searching_view_manager.unregister(discord_uid, deactivate=True)
            print(f"[AdminService] Cleared queue view for player {discord_uid}")
            
            # Clear from match_results
            if discord_uid in match_results:
                del match_results[discord_uid]
                print(f"[AdminService] Cleared match result for player {discord_uid}")
            
            # Clear from channel_to_match_view_map (find channels associated with this player)
            channels_to_remove = []
            for channel_id, view in channel_to_match_view_map.items():
                if hasattr(view, 'match_result'):
                    match_result = view.match_result
                    if (match_result.player_1_discord_id == discord_uid or 
                        match_result.player_2_discord_id == discord_uid):
                        channels_to_remove.append(channel_id)
            
            for channel_id in channels_to_remove:
                del channel_to_match_view_map[channel_id]
                print(f"[AdminService] Cleared match view for player {discord_uid} in channel {channel_id}")
            
        except Exception as e:
            print(f"[AdminService] WARNING: Error clearing queue lock for {discord_uid}: {e}")
            # Don't fail the whole operation if queue lock clearing fails
    
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
                # First try discord_username
                matches = self.data_service._players_df.filter(
                    pl.col('discord_username').str.to_lowercase() == username.lower()
                )
                
                # If no match, try player_name field
                if len(matches) == 0:
                    matches = self.data_service._players_df.filter(
                        pl.col('player_name').str.to_lowercase() == username.lower()
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
                'player_name': player_info.get('player_name')
            }
        
        return {'discord_uid': discord_uid, 'player_name': None}
    
    # ========== LAYER 1: READ-ONLY INSPECTION ==========
    
    def get_system_snapshot(self) -> dict:
        """
        Get complete system state snapshot for debugging.
        
        Returns formatted data for 3 Discord embeds displaying system state.
        
        Discord Embed Character Limits:
            - Title: 256 chars max
            - Description: 4096 chars max
            - Field name: 256 chars max
            - Field value: 1024 chars max
            - Total across all embeds: 6000 chars max
            - Max embeds per message: 10
        
        Current Usage (~2400 chars total, well under 6000 limit):
            Embed 1 (System Stats): ~500 chars
                - Title: "🔍 Admin System Snapshot" (~27 chars)
                - 4 fields: Memory, DataFrames, Write Queue, Process Pool
            
            Embed 2 (Queue Status): ~950 chars (text-based format)
                - Title: "🎮 Queue Status" (~15 chars)
                - 30 player slots (15 per column × 2 columns, ~31 chars each)
                - Format: `A T1 KR ReBellioN   ` ` 794s`
                - Each line: 1 rank letter + 2 race + 2 country + 12 name + 4 time
            
            Embed 3 (Active Matches): ~1020 chars (text-based format)
                - Title: "⚔️ Active Matches" (~17 chars)
                - 15 match slots (~68 chars each)
                - Format: `  638` `A T1 KR ReBellioN   ` `vs` `B T2 KR milbob      ` ` 794s`
                - Each line: 5 match_id + 2×(1+2+2+12) + 4 time
        
        Returns:
            Comprehensive dict with all system state including memory usage,
            DataFrame statistics, queue status, active matches, write queue depth,
            and process pool health.
        """
        from src.backend.services.matchmaking_service import matchmaker
        from src.backend.services.match_completion_service import match_completion_service
        from src.backend.services.app_context import ranking_service
        import time as time_module
        
        # Get queue player details for display (always show 30 slots)
        queue_players_raw = self._get_queue_snapshot_from_matchmaker()
        queue_player_strings = []
        MAX_QUEUE_SLOTS = 30
        
        for idx in range(1, MAX_QUEUE_SLOTS + 1):
            # Check if we have a player for this slot
            if idx <= len(queue_players_raw):
                p = queue_players_raw[idx - 1]
                player_info = self.data_service.get_player_info(p['discord_id'])
                player_name = player_info.get('player_name', 'Unknown') if player_info else 'Unknown'
                country = player_info.get('country') if player_info else None
                
                # Determine which races the player is queueing with
                bw_race = None
                sc2_race = None
                for race in p['races']:
                    if race.startswith('bw_'):
                        bw_race = race
                    elif race.startswith('sc2_'):
                        sc2_race = race
                
                # Get rank for the primary race (prefer BW if both, otherwise use whichever they have)
                rank_race = bw_race if bw_race else sc2_race
                rank = 'u_rank'
                if rank_race:
                    rank = ranking_service.get_letter_rank(p['discord_id'], rank_race)
                
                # Get text-based components
                rank_letter = rank[0].upper() if rank and rank != 'u_rank' else 'U'
                
                # Get short names for both races (if present)
                bw_short = races_service.get_race_short_name(bw_race) if bw_race else None
                if bw_short == bw_race:
                    bw_short = None
                sc2_short = races_service.get_race_short_name(sc2_race) if sc2_race else None
                if sc2_short == sc2_race:
                    sc2_short = None
                
                # Format races: "Z1 T2", "Z1   ", "   T2", or "     "
                if bw_short and sc2_short:
                    races_str = f"{bw_short} {sc2_short}"
                elif bw_short:
                    races_str = f"{bw_short}   "
                elif sc2_short:
                    races_str = f"   {sc2_short}"
                else:
                    races_str = "     "
                
                country_code = country.upper() if country else '??'
                
                # Format player name: truncate to 12 chars, then pad to 12 chars
                player_name_truncated = player_name[:12]
                player_name_padded = f"{player_name_truncated:<12}"
                
                # Format wait time (4 chars, right-aligned, integer only)
                wait_time_int = int(p['wait_time'])
                wait_time_str = f"{wait_time_int:>4d}s"
                
                # Format: `A Z1 T2 KR ReBellioN   ` ` 794s`
                queue_player_strings.append(
                    f"`{rank_letter} {races_str} {country_code} {player_name_padded}` `{wait_time_str}`"
                )
            else:
                # Empty slot - just blank spaces
                blank_name = " " * 12
                blank_time = " " * 5
                queue_player_strings.append(
                    f"`        {blank_name}` `{blank_time}`"
                )
        
        # Get active match details for display (always show 15 slots)
        active_matches = list(match_completion_service.monitored_matches) if match_completion_service else []
        match_strings = []
        MAX_MATCH_SLOTS = 15
        
        # Determine the maximum width needed for match IDs (minimum 5)
        max_id_width = 5
        if active_matches:
            max_match_id = max(active_matches)
            max_id_width = max(5, len(str(max_match_id)))
        
        for idx in range(MAX_MATCH_SLOTS):
            # Check if we have a match for this slot
            if idx < len(active_matches):
                match_id = active_matches[idx]
                match_data = self.data_service.get_match(match_id)
                
                if match_data:
                    p1_uid = int(match_data['player_1_discord_uid'])
                    p2_uid = int(match_data['player_2_discord_uid'])
                    p1_info = self.data_service.get_player_info(p1_uid)
                    p2_info = self.data_service.get_player_info(p2_uid)
                    p1_name = p1_info.get('player_name', 'Unknown') if p1_info else 'Unknown'
                    p2_name = p2_info.get('player_name', 'Unknown') if p2_info else 'Unknown'
                    p1_country = p1_info.get('country') if p1_info else None
                    p2_country = p2_info.get('country') if p2_info else None
                    
                    # Get race for each player in this match
                    p1_race = match_data.get('player_1_race')
                    p2_race = match_data.get('player_2_race')
                    
                    # Get rank for each player-race combination
                    p1_rank = ranking_service.get_letter_rank(p1_uid, p1_race) if p1_race else 'u_rank'
                    p2_rank = ranking_service.get_letter_rank(p2_uid, p2_race) if p2_race else 'u_rank'
                    
                    # Get text-based components
                    p1_rank_letter = p1_rank[0].upper() if p1_rank and p1_rank != 'u_rank' else 'U'
                    p2_rank_letter = p2_rank[0].upper() if p2_rank and p2_rank != 'u_rank' else 'U'
                    p1_race_short = races_service.get_race_short_name(p1_race) if p1_race else '??'
                    if p1_race_short == p1_race:
                        p1_race_short = '??'
                    p2_race_short = races_service.get_race_short_name(p2_race) if p2_race else '??'
                    if p2_race_short == p2_race:
                        p2_race_short = '??'
                    p1_country_code = p1_country.upper() if p1_country else '??'
                    p2_country_code = p2_country.upper() if p2_country else '??'
                    
                    # Format player names: truncate to 12 chars, then pad to 12 chars
                    p1_name_truncated = p1_name[:12]
                    p1_name_padded = f"{p1_name_truncated:<12}"
                    p2_name_truncated = p2_name[:12]
                    p2_name_padded = f"{p2_name_truncated:<12}"
                    
                    # Calculate elapsed time since match was assigned
                    played_at = match_data.get('played_at')
                    if played_at:
                        # Convert played_at to datetime if it's a string
                        if isinstance(played_at, str):
                            from datetime import datetime as dt_class
                            played_at_dt = dt_class.fromisoformat(played_at.replace('Z', '+00:00'))
                        else:
                            played_at_dt = played_at
                        
                        # Calculate elapsed seconds using module-level datetime
                        now_utc = datetime.now(timezone.utc)
                        elapsed_seconds = int((now_utc - played_at_dt).total_seconds())
                        elapsed_str = f"{elapsed_seconds:>4d}s"
                    else:
                        elapsed_str = "   ?s"
                    
                    # Format match ID (dynamically sized, use as position)
                    match_id_padded = f"{match_id:>{max_id_width}d}"
                    
                    # Format: `  638` `A T1 KR ReBellioN   ` vs `B T2 KR milbob      ` ` 794s`
                    match_strings.append(
                        f"`{match_id_padded}` `{p1_rank_letter} {p1_race_short} {p1_country_code} {p1_name_padded}` `vs` `{p2_rank_letter} {p2_race_short} {p2_country_code} {p2_name_padded}` `{elapsed_str}`"
                    )
                else:
                    # Match data not found - show empty slot
                    blank_name = " " * 12
                    blank_id = " " * max_id_width
                    blank_time = " " * 5
                    match_strings.append(
                        f"`{blank_id}` `        {blank_name}` `vs` `        {blank_name}` `{blank_time}`"
                    )
            else:
                # Empty slot - just blank spaces
                blank_name = " " * 12
                blank_id = " " * max_id_width
                blank_time = " " * 5
                match_strings.append(
                    f"`{blank_id}` `        {blank_name}` `vs` `        {blank_name}` `{blank_time}`"
                )
        
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'memory': self._get_memory_stats(),
            'data_frames': self._get_dataframe_stats(),
            'queue': {
                'size': matchmaker.get_queue_size(),
                'players': queue_player_strings
            },
            'matches': {
                'active': len(active_matches),
                'match_list': match_strings
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
    
    def _get_queue_snapshot_from_matchmaker(self) -> list:
        """Get list of players currently in queue from matchmaker."""
        from src.backend.services.matchmaking_service import matchmaker
        
        players = matchmaker.get_queue_players()
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
                    'name': p1_info.get('player_name'),
                    'race': row['player_1_race'],
                    'report': row.get('player_1_report'),
                    'replay': p1_replay
                },
                'player_2': {
                    'discord_uid': row['player_2_discord_uid'],
                    'name': p2_info.get('player_name'),
                    'race': row['player_2_race'],
                    'report': row.get('player_2_report'),
                    'replay': p2_replay
                },
                'map': row['map_played'],
                'server': row['server_used'],
                'played_at': row['played_at'],
                'status': row.get('status')
            })
        
        return result
    
    async def get_player_full_state(self, discord_uid: int) -> dict:
        """
        Get complete state for a player with all display data pre-calculated.
        
        Args:
            discord_uid: Player's Discord ID
            
        Returns:
            Dict with all player state information including basic info, enriched MMRs,
            queue status, active matches, and recent match history. All data is ready
            for display (names resolved, ranks calculated, etc.). Includes time_stats.
        """
        from src.backend.services.matchmaking_service import matchmaker
        from src.backend.services.app_context import (
            countries_service, regions_service, races_service, ranking_service, user_info_service
        )
        
        # Get player info with time-stratified stats
        player_info = user_info_service.get_player_with_time_stats(discord_uid)
        
        # Enrich player_info with display-ready data
        if player_info:
            # Add country name
            if player_info.get('country'):
                country = countries_service.get_country_by_code(player_info['country'])
                player_info['country_name'] = country.get('name') if country else player_info['country']
            
            # Add region name
            if player_info.get('region'):
                region_name = regions_service.get_region_name(player_info['region'])
                player_info['region_name'] = region_name if region_name else player_info['region']
                
                # Add globe emoji code for region
                region_data = regions_service.get_region_by_code(player_info['region'])
                if region_data and region_data.get('globe_emote'):
                    player_info['region_globe_emote'] = region_data.get('globe_emote')
        
        # Enrich MMR data with ranks, race names, and race order
        mmrs = {}
        race_order = races_service.get_race_order()
        
        if self.data_service._mmrs_1v1_df is not None:
            player_mmrs = self.data_service._mmrs_1v1_df.filter(
                pl.col('discord_uid') == discord_uid
            )
            for row in player_mmrs.iter_rows(named=True):
                race_code = row['race']
                
                # Calculate rank for this race
                rank = ranking_service.get_letter_rank(discord_uid, race_code)
                
                # Get race name
                race_name = races_service.get_race_name(race_code)
                
                # Determine sort order
                try:
                    sort_order = race_order.index(race_code)
                except ValueError:
                    sort_order = len(race_order)
                
                mmrs[race_code] = {
                    'mmr': row['mmr'],
                    'games_played': row['games_played'],
                    'games_won': row['games_won'],
                    'games_lost': row['games_lost'],
                    'games_drawn': row['games_drawn'],
                    'last_played': row.get('last_played'),
                    'rank': rank,
                    'race_name': race_name,
                    'sort_order': sort_order,
                    'is_bw': race_code.startswith('bw_'),
                    'is_sc2': race_code.startswith('sc2_')
                }
        
        in_queue = False
        queue_info = None
        in_queue = await matchmaker.is_player_in_queue(discord_uid)
        if in_queue:
            # Find the player in the queue
            for player_obj in matchmaker.get_queue_players():
                if player_obj.discord_user_id == discord_uid:
                    queue_info = {
                        'races': player_obj.preferences.selected_races,
                        'wait_time': time.time() - player_obj.queue_start_time,
                        'wait_cycles': player_obj.wait_cycles
                    }
                    break
        
        # Active matches - check by match_result instead of status
        active_matches = []
        if self.data_service._matches_1v1_df is not None:
            player_matches = self.data_service._matches_1v1_df.filter(
                (pl.col('player_1_discord_uid') == discord_uid) |
                (pl.col('player_2_discord_uid') == discord_uid)
            ).filter(
                pl.col('match_result').is_null() |  # Match not finished
                (pl.col('match_result') == 0)        # Or match_result is 0 (in progress)
            )
            
            for row in player_matches.iter_rows(named=True):
                opponent_uid = row['player_2_discord_uid'] if row['player_1_discord_uid'] == discord_uid else row['player_1_discord_uid']
                opponent_info = self.data_service.get_player_info(opponent_uid)
                opponent_name = opponent_info.get('player_name', 'Unknown') if opponent_info else 'Unknown'
                
                active_matches.append({
                    'match_id': row['id'],
                    'is_player_1': row['player_1_discord_uid'] == discord_uid,
                    'opponent_discord_uid': opponent_uid,
                    'opponent_name': opponent_name,
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
                'match_result': match_data.get('match_result')
            },
            'replays': {
                'player_1': match_data.get('player_1_replay_path'),
                'player_2': match_data.get('player_2_replay_path')
            }
        }
    
    async def get_replay_embeds_for_match(self, match_id: int) -> dict:
        """
        Get replay detail embeds for both players with full verification.
        Returns embeds exactly as players would see them during match upload.
        
        Args:
            match_id: Match ID
            
        Returns:
            Dict with player_1_embed and player_2_embed (discord.Embed objects or None)
        """
        from src.backend.services.match_completion_service import match_completion_service
        from src.bot.components.replay_details_embed import ReplayDetailsEmbed
        import json
        
        match_data = self.data_service.get_match(match_id)
        if not match_data:
            return {
                'player_1_embed': None,
                'player_2_embed': None
            }
        
        p1_info = self.data_service.get_player_info(match_data['player_1_discord_uid'])
        p2_info = self.data_service.get_player_info(match_data['player_2_discord_uid'])
        
        p1_name = p1_info.get('player_name', 'Unknown') if p1_info else 'Unknown'
        p2_name = p2_info.get('player_name', 'Unknown') if p2_info else 'Unknown'
        
        p1_replay_path = match_data.get('player_1_replay_path')
        p2_replay_path = match_data.get('player_2_replay_path')
        
        def _process_replay_data(replay_data: dict) -> dict:
            """Process replay data from database - parse JSON strings back to Python objects."""
            # Parse observers from JSON string to list
            if isinstance(replay_data.get('observers'), str):
                try:
                    replay_data['observers'] = json.loads(replay_data['observers'])
                except (json.JSONDecodeError, TypeError):
                    replay_data['observers'] = []
            
            # Parse cache_handles from JSON string to list
            if isinstance(replay_data.get('cache_handles'), str):
                try:
                    replay_data['cache_handles'] = json.loads(replay_data['cache_handles'])
                except (json.JSONDecodeError, TypeError):
                    replay_data['cache_handles'] = []
            
            return replay_data
        
        async def create_replay_embed(replay_path: str, player_name: str, player_num: int):
            """Create full replay embed with verification for a player."""
            if not replay_path:
                return None
            
            try:
                # Get replay data from database
                replay_data = self.data_service.get_replay_by_path(replay_path)
                if not replay_data:
                    print(f"[AdminService] No replay data found for path: {replay_path}")
                    return None
                
                # Process JSON fields
                replay_data = _process_replay_data(replay_data)
                
                # Get verification results (same as players see during upload)
                verification_results = await match_completion_service.verify_replay_data(
                    match_id=match_id,
                    replay_data=replay_data
                )
                
                # Create embed with full verification (exactly as players see it)
                embed = ReplayDetailsEmbed.get_success_embed(
                    replay_data=replay_data,
                    verification_results=verification_results
                )
                
                # Customize title to show player number
                embed.title = f"📄 Player #{player_num} Replay Details"
                
                return embed
                
            except Exception as e:
                print(f"[AdminService] Error creating replay embed for player {player_num}: {e}")
                import traceback
                traceback.print_exc()
                return None
        
        # Create embeds for both players
        p1_embed = await create_replay_embed(p1_replay_path, p1_name, 1)
        p2_embed = await create_replay_embed(p2_replay_path, p2_name, 2)
        
        return {
            'player_1_embed': p1_embed,
            'player_2_embed': p2_embed
        }
    
    async def fetch_match_replay_files(self, match_id: int) -> dict:
        """
        Fetch replay files for both players in a match.
        
        Args:
            match_id: Match ID
            
        Returns:
            Dict with player_1_replay and player_2_replay as bytes (or None if not available)
            Format: {
                'player_1_replay': bytes or None,
                'player_1_name': str,
                'player_2_replay': bytes or None,
                'player_2_name': str
            }
        """
        from src.backend.services.app_context import storage_service
        from pathlib import Path
        
        match_data = self.data_service.get_match(match_id)
        if not match_data:
            return {
                'player_1_replay': None,
                'player_1_name': 'Unknown',
                'player_2_replay': None,
                'player_2_name': 'Unknown'
            }
        
        p1_info = self.data_service.get_player_info(match_data['player_1_discord_uid'])
        p2_info = self.data_service.get_player_info(match_data['player_2_discord_uid'])
        
        p1_name = p1_info.get('player_name', 'Unknown') if p1_info else 'Unknown'
        p2_name = p2_info.get('player_name', 'Unknown') if p2_info else 'Unknown'
        
        p1_replay_path = match_data.get('player_1_replay_path')
        p2_replay_path = match_data.get('player_2_replay_path')
        
        async def fetch_replay_bytes(replay_path: str, player_uid: int) -> bytes:
            """Fetch replay bytes from Supabase or local storage."""
            if not replay_path:
                return None
            
            try:
                # Check if it's a Supabase URL
                if replay_path.startswith('http'):
                    print(f"[AdminService] Downloading replay from Supabase URL: {replay_path}")
                    
                    # Download directly from the URL using httpx
                    import httpx
                    with httpx.Client(timeout=30.0) as client:
                        response = client.get(replay_path)
                        
                        if response.status_code != 200:
                            print(f"[AdminService] Failed to download replay: {response.status_code} {response.text}")
                            return None
                        
                        replay_bytes = response.content
                        print(f"[AdminService] Successfully downloaded replay ({len(replay_bytes)} bytes)")
                        return replay_bytes
                else:
                    # It's a local file path
                    print(f"[AdminService] Reading replay from local storage: {replay_path}")
                    replay_path_obj = Path(replay_path)
                    
                    if not replay_path_obj.exists():
                        print(f"[AdminService] Local replay file not found: {replay_path}")
                        return None
                    
                    with open(replay_path_obj, 'rb') as f:
                        replay_bytes = f.read()
                    
                    print(f"[AdminService] Successfully read local replay ({len(replay_bytes)} bytes)")
                    return replay_bytes
                    
            except Exception as e:
                print(f"[AdminService] Error fetching replay for player {player_uid}: {e}")
                import traceback
                traceback.print_exc()
                return None
        
        # Fetch both replays
        p1_replay_bytes = await fetch_replay_bytes(p1_replay_path, match_data['player_1_discord_uid'])
        p2_replay_bytes = await fetch_replay_bytes(p2_replay_path, match_data['player_2_discord_uid'])
        
        return {
            'player_1_replay': p1_replay_bytes,
            'player_1_name': p1_name,
            'player_2_replay': p2_replay_bytes,
            'player_2_name': p2_name
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
        Resolve a match by admin decision.
        
        Uses two different approaches depending on match state:
        1. Fresh/in-progress matches: Simulates both players reporting (normal flow)
        2. Terminal matches (CONFLICT/COMPLETE): Direct manipulation and manual completion
        
        Args:
            match_id: Match ID
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
        
        p1_uid = match_data['player_1_discord_uid']
        p2_uid = match_data['player_2_discord_uid']
        p1_report = match_data.get('player_1_report')
        p2_report = match_data.get('player_2_report')
        match_result = match_data.get('match_result')
        
        resolution_map = {
            'player_1_win': 1,
            'player_2_win': 2,
            'draw': 0,
            'invalidate': -1
        }
        
        if resolution not in resolution_map:
            return {'success': False, 'error': 'Invalid resolution'}
        
        new_result = resolution_map[resolution]
        
        # CRITICAL: Don't rely on status field - check if players have actually reported
        # If BOTH reports are filled, match has been through player reporting → use terminal path
        # If reports are NULL, match is fresh/abandoned → use fresh path
        has_reports = (p1_report is not None and p2_report is not None)
        
        # Also check if match has a result (might have been admin-resolved before)
        has_result = match_result is not None and match_result != 0
        
        # Use terminal path if match has been processed by players OR already has a result
        is_terminal = has_reports or has_result
        
        try:
            if is_terminal:
                reason_text = "has player reports" if has_reports else "has existing result"
                print(f"[AdminService] Match {match_id} is TERMINAL ({reason_text}: p1={p1_report}, p2={p2_report}, result={match_result}) - using direct manipulation")
                return await self._resolve_terminal_match(
                    match_id, new_result, resolution, admin_discord_id, reason, 
                    match_data, p1_uid, p2_uid
                )
            else:
                print(f"[AdminService] Match {match_id} is FRESH (no reports: p1={p1_report}, p2={p2_report}) - using simulated reports")
                return await self._resolve_fresh_match(
                    match_id, new_result, resolution, admin_discord_id, reason,
                    match_data, p1_uid, p2_uid
                )
            
        except Exception as e:
            print(f"[AdminService] ERROR resolving match {match_id}: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    async def _resolve_fresh_match(
        self,
        match_id: int,
        new_result: int,
        resolution: str,
        admin_discord_id: int,
        reason: str,
        match_data: dict,
        p1_uid: int,
        p2_uid: int
    ) -> dict:
        """
        Resolve a fresh/in-progress match by simulating both players reporting.
        This triggers the normal match completion flow.
        """
        from src.backend.services.match_completion_service import match_completion_service
        
        # Save original reports (if any) before modifying them
        original_p1_report = match_data.get('player_1_report')
        original_p2_report = match_data.get('player_2_report')
        print(f"[AdminService] Saving original reports: P1={original_p1_report}, P2={original_p2_report}")
        
        # Step 1: Update match_result in memory
        await self.data_service.update_match(
            match_id=match_id,
            match_result=new_result
        )
        print(f"[AdminService] Set match_result={new_result} for match {match_id}")
        
        # Step 2: Simulate both players reporting with matching results
        # This directly updates the DataFrame, bypassing record_match_result's validation
        await self._update_player_reports_directly(match_id, p1_uid, p2_uid, new_result)
        print(f"[AdminService] Simulated both players reporting result={new_result}")
        
        # Step 3: Trigger normal completion flow
        # This will detect both reports match and call _handle_match_completion
        # which handles: MMR calc, notifications, queue locks, cleanup
        print(f"[AdminService] Triggering normal completion flow for match {match_id}")
        
        # CRITICAL: Call check_match_completion synchronously and await it
        # If we use asyncio.create_task(), there's a race condition where the match
        # gets marked as processed before the completion logic runs
        await match_completion_service.check_match_completion(match_id)
        
        # Step 4: Get MMR change from completed match
        final_match_data = self.data_service.get_match(match_id)
        mmr_change = final_match_data.get('mmr_change', 0) if final_match_data else 0
        
        # Step 5: Restore original reports in memory
        import polars as pl
        
        self.data_service._matches_1v1_df = self.data_service._matches_1v1_df.with_columns([
            pl.when(pl.col("id") == match_id)
              .then(pl.lit(original_p1_report))
              .otherwise(pl.col("player_1_report"))
              .alias("player_1_report"),
            pl.when(pl.col("id") == match_id)
              .then(pl.lit(original_p2_report))
              .otherwise(pl.col("player_2_report"))
              .alias("player_2_report")
        ])
        print(f"[AdminService] Restored original reports in memory: P1={original_p1_report}, P2={original_p2_report}")
        
        # Step 6: Queue admin resolution write to restore original reports in DB and set updated_at
        # This is an atomic operation that preserves original reports, sets final result, and timestamps
        from src.backend.services.data_access_service import WriteJob, WriteJobType
        import time
        
        admin_resolve_job = WriteJob(
            job_type=WriteJobType.ADMIN_RESOLVE_MATCH,
            data={
                "match_id": match_id,
                "match_result": new_result,
                "p1_report": original_p1_report,
                "p2_report": original_p2_report
            },
            timestamp=time.time()
        )
        await self.data_service._queue_write(admin_resolve_job)
        print(f"[AdminService] Queued ADMIN_RESOLVE_MATCH: result={new_result}, P1={original_p1_report}, P2={original_p2_report}")
        
        # Step 7: Log admin action
        await self._log_admin_action(
            admin_discord_id=admin_discord_id,
            action_type='resolve_match',
            target_match_id=match_id,
            details={
                'resolution': resolution,
                'new_result': new_result,
                'method': 'simulated_reports',
                'mmr_change': mmr_change,
                'reason': reason
            }
        )
        
        # Step 8: Get player details for embed
        admin_info = self.data_service.get_player_info(admin_discord_id)
        p1_info = self.data_service.get_player_info(p1_uid)
        p2_info = self.data_service.get_player_info(p2_uid)
        
        # Get player details
        p1_name = p1_info.get('player_name') if p1_info else 'Unknown'
        p2_name = p2_info.get('player_name') if p2_info else 'Unknown'
        p1_country = p1_info.get('country')
        p2_country = p2_info.get('country')
        p1_race = final_match_data.get('player_1_race')
        p2_race = final_match_data.get('player_2_race')
        map_name = final_match_data.get('map_played')
        
        # Get MMR details - use match table's stored initial MMRs
        p1_mmr_initial = final_match_data.get('player_1_mmr')
        p2_mmr_initial = final_match_data.get('player_2_mmr')
        
        # Calculate "after" MMRs based on initial + change
        p1_mmr_after = p1_mmr_initial + mmr_change
        p2_mmr_after = p2_mmr_initial - mmr_change
        
        # Get ranks
        from src.backend.services.app_context import ranking_service
        p1_rank = ranking_service.get_letter_rank(p1_uid, p1_race)
        p2_rank = ranking_service.get_letter_rank(p2_uid, p2_race)
        
        # Return success with calculated MMR and full match data
        return {
            'success': True,
            'match_id': match_id,
            'resolution': resolution,
            'method': 'simulated_reports',
            'mmr_change': mmr_change,
            'match_data': {
                'player_1_uid': p1_uid,
                'player_2_uid': p2_uid,
                'player_1_name': p1_name,
                'player_2_name': p2_name,
                'player_1_country': p1_country,
                'player_2_country': p2_country,
                'player_1_race': p1_race,
                'player_2_race': p2_race,
                'map_name': map_name or 'Unknown',
                'player_1_mmr_before': p1_mmr_initial or 0,
                'player_2_mmr_before': p2_mmr_initial or 0,
                'player_1_mmr_after': p1_mmr_after or 0,
                'player_2_mmr_after': p2_mmr_after or 0,
                'player_1_rank': p1_rank,
                'player_2_rank': p2_rank
            },
            'notification_data': {
                'players': [p1_uid, p2_uid],
                'admin_name': admin_info.get('player_name', 'Admin') if admin_info else 'Admin',
                'reason': reason,
                'match_id': match_id,
                'resolution': resolution,
                'mmr_change': mmr_change,
                'player_1_name': p1_name,
                'player_2_name': p2_name,
                'player_1_country': p1_country,
                'player_2_country': p2_country,
                'player_1_race': p1_race,
                'player_2_race': p2_race,
                'map_name': map_name or 'Unknown',
                'player_1_mmr_before': p1_mmr_initial or 0,
                'player_2_mmr_before': p2_mmr_initial or 0,
                'player_1_mmr_after': p1_mmr_after or 0,
                'player_2_mmr_after': p2_mmr_after or 0,
                'player_1_rank': p1_rank,
                'player_2_rank': p2_rank
            }
        }
    
    async def _resolve_terminal_match(
        self,
        match_id: int,
        new_result: int,
        resolution: str,
        admin_discord_id: int,
        reason: str,
        match_data: dict,
        p1_uid: int,
        p2_uid: int
    ) -> dict:
        """
        Resolve a terminal match (CONFLICT/COMPLETE) by direct manipulation.
        This bypasses normal flow and manually triggers completion.
        """
        from src.backend.services.matchmaking_service import matchmaker
        from src.backend.services.match_completion_service import match_completion_service
        
        print(f"[AdminService] Resolving terminal match {match_id} (was {match_data.get('status')})")
        
        # Step 1: Get original MMRs from match table (player_1_mmr and player_2_mmr store the initial MMRs)
        # These are the baseline MMRs we'll use for idempotent calculations
        p1_mmr_before = match_data.get('player_1_mmr')
        p2_mmr_before = match_data.get('player_2_mmr')
        
        # Sanity check: if these are None, something is very wrong
        if p1_mmr_before is None or p2_mmr_before is None:
            raise ValueError(f"Match {match_id} missing player_1_mmr or player_2_mmr - cannot resolve")
        
        print(f"[AdminService] Using initial MMRs from match table: P1={p1_mmr_before}, P2={p2_mmr_before}")
        
        existing_mmr_change = match_data.get('mmr_change', 0)
        
        if p1_mmr_before is not None and p2_mmr_before is not None and existing_mmr_change != 0:
            print(f"[AdminService] Match {match_id} was already resolved (mmr_change={existing_mmr_change})")
            print(f"[AdminService] Restoring original MMRs: P1={p1_mmr_before}, P2={p2_mmr_before}")
            
            # Restore both players to their original MMRs before this match
            p1_race = match_data.get('player_1_race')
            p2_race = match_data.get('player_2_race')
            
            await self.data_service.update_player_mmr(p1_uid, p1_race, p1_mmr_before)
            await self.data_service.update_player_mmr(p2_uid, p2_race, p2_mmr_before)
            print(f"[AdminService] Restored MMRs for re-resolution")
        
        # Save original reports before modifying them
        original_p1_report = match_data.get('player_1_report')
        original_p2_report = match_data.get('player_2_report')
        print(f"[AdminService] Saving original reports: P1={original_p1_report}, P2={original_p2_report}")
        
        # Step 2: Remove from processed_matches so we can re-process
        if match_id in match_completion_service.processed_matches:
            match_completion_service.processed_matches.remove(match_id)
            print(f"[AdminService] Removed match {match_id} from processed_matches")
        
        # Step 3: Update match state (result + reset mmr_change)
        await self.data_service.update_match(
            match_id=match_id,
            match_result=new_result
        )
        # Reset mmr_change to 0 so it gets recalculated
        await self.data_service.update_match_mmr_change(match_id, 0)
        
        # Step 4: Update both player reports directly
        await self._update_player_reports_directly(match_id, p1_uid, p2_uid, new_result)
        print(f"[AdminService] Updated match {match_id} state: result={new_result}, reports={new_result}")
        
        # Step 5: Get fresh match data with restored originals
        updated_match_data = self.data_service.get_match(match_id)
        if not updated_match_data:
            raise ValueError(f"Could not retrieve match {match_id} after update")
        
        # Step 6: Calculate MMR change from ORIGINAL MMRs (for idempotency)
        # Skip MMR calculation for invalidated matches (result=-1)
        p1_race = updated_match_data.get('player_1_race')
        p2_race = updated_match_data.get('player_2_race')
        
        if resolution != 'invalidate':
            # Calculate MMR change based on original MMRs and new result
            # This ensures: new_mmr = original_mmr + calculated_change
            # No matter how many times we resolve, it's always from the same baseline
            
            mmr_change = mmr_service.calculate_mmr_change(
                p1_mmr_before,  # Use restored/original MMR
                p2_mmr_before,  # Use restored/original MMR
                new_result
            )
            
            print(f"[AdminService] Calculated MMR change from originals: {mmr_change} (P1={p1_mmr_before}, P2={p2_mmr_before}, result={new_result})")
            
            # Step 7: Apply MMR change to ORIGINAL MMRs (idempotent!)
            p1_new_mmr = int(p1_mmr_before + mmr_change)
            p2_new_mmr = int(p2_mmr_before - mmr_change)
            
            # Apply new MMRs ONLY (don't update game stats - admin is overriding)
            # Game stats should only be updated by the normal match flow, not admin resolutions
            await self.data_service.update_player_mmr(
                p1_uid, p1_race, p1_new_mmr,
                games_played=None,  # Don't change game stats
                games_won=None,
                games_lost=None,
                games_drawn=None
            )
            
            await self.data_service.update_player_mmr(
                p2_uid, p2_race, p2_new_mmr,
                games_played=None,  # Don't change game stats
                games_won=None,
                games_lost=None,
                games_drawn=None
            )
            
            print(f"[AdminService] Applied idempotent MMR: P1 {p1_mmr_before} → {p1_new_mmr}, P2 {p2_mmr_before} → {p2_new_mmr}")
        else:
            # Match invalidated - no MMR changes
            mmr_change = 0
            print(f"[AdminService] Match invalidated (result={new_result}), no MMR changes")
        
        # Step 8: Update match with final values
        await self.data_service.update_match(match_id, match_result=new_result)
        await self.data_service.update_match_mmr_change(match_id, mmr_change)
        
        # Step 9: Clear queue locks
        await self._clear_player_queue_lock(p1_uid)
        await self._clear_player_queue_lock(p2_uid)
        print(f"[AdminService] Cleared queue locks for both players")
        
        # Step 10: Restore original reports in memory
        import polars as pl
        
        self.data_service._matches_1v1_df = self.data_service._matches_1v1_df.with_columns([
            pl.when(pl.col("id") == match_id)
              .then(pl.lit(original_p1_report))
              .otherwise(pl.col("player_1_report"))
              .alias("player_1_report"),
            pl.when(pl.col("id") == match_id)
              .then(pl.lit(original_p2_report))
              .otherwise(pl.col("player_2_report"))
              .alias("player_2_report")
        ])
        print(f"[AdminService] Restored original reports in memory: P1={original_p1_report}, P2={original_p2_report}")
        
        # Step 11: Queue admin resolution write to restore original reports in DB and set updated_at
        # This is an atomic operation that preserves original reports, sets final result, and timestamps
        from src.backend.services.data_access_service import WriteJob, WriteJobType
        import time
        
        admin_resolve_job = WriteJob(
            job_type=WriteJobType.ADMIN_RESOLVE_MATCH,
            data={
                "match_id": match_id,
                "match_result": new_result,
                "p1_report": original_p1_report,
                "p2_report": original_p2_report
            },
            timestamp=time.time()
        )
        await self.data_service._queue_write(admin_resolve_job)
        print(f"[AdminService] Queued ADMIN_RESOLVE_MATCH: result={new_result}, P1={original_p1_report}, P2={original_p2_report}")
        
        # Step 12: Get final match data
        final_match_data = self.data_service.get_match(match_id)
        
        # Step 13: Log admin action
        await self._log_admin_action(
            admin_discord_id=admin_discord_id,
            action_type='resolve_conflict',
            target_match_id=match_id,
            details={
                'resolution': resolution,
                'new_result': new_result,
                'method': 'direct_manipulation',
                'mmr_change': mmr_change,
                'reason': reason
            }
        )
        
        # Return complete data for frontend (no logic needed in frontend)
        admin_info = self.data_service.get_player_info(admin_discord_id)
        p1_info = self.data_service.get_player_info(p1_uid)
        p2_info = self.data_service.get_player_info(p2_uid)
        
        # Get player details
        p1_name = p1_info.get('player_name')
        p2_name = p2_info.get('player_name')
        p1_country = p1_info.get('country')
        p2_country = p2_info.get('country')
        p1_race = final_match_data.get('player_1_race')
        p2_race = final_match_data.get('player_2_race')
        map_name = final_match_data.get('map_name')
        
        # Get MMR details - use match table's stored initial MMRs as source of truth
        # player_1_mmr and player_2_mmr store the initial MMRs when the match started
        p1_mmr_initial = final_match_data.get('player_1_mmr')
        p2_mmr_initial = final_match_data.get('player_2_mmr')
        
        # Calculate "after" MMRs based on initial + change
        # This ensures idempotency: initial + change = after (always the same)
        p1_mmr_after = p1_mmr_initial + mmr_change
        p2_mmr_after = p2_mmr_initial - mmr_change
        
        # Get ranks
        from src.backend.services.app_context import ranking_service
        p1_rank = ranking_service.get_letter_rank(p1_uid, p1_race)
        p2_rank = ranking_service.get_letter_rank(p2_uid, p2_race)
        
        return {
            'success': True,
            'match_id': match_id,
            'resolution': resolution,
            'method': 'direct_manipulation',
            'mmr_change': mmr_change,
            'match_data': {
                'player_1_uid': p1_uid,
                'player_2_uid': p2_uid,
                'player_1_name': p1_name,
                'player_2_name': p2_name,
                'player_1_country': p1_country,
                'player_2_country': p2_country,
                'player_1_race': p1_race,
                'player_2_race': p2_race,
                'map_name': map_name or 'Unknown',
                'player_1_mmr_before': p1_mmr_initial or 0,  # Use initial MMR from match table
                'player_2_mmr_before': p2_mmr_initial or 0,  # Use initial MMR from match table
                'player_1_mmr_after': p1_mmr_after or 0,     # Calculated: initial + change
                'player_2_mmr_after': p2_mmr_after or 0,     # Calculated: initial - change
                'player_1_rank': p1_rank,
                'player_2_rank': p2_rank
            },
            'notification_data': {
                'players': [p1_uid, p2_uid],
                'admin_name': admin_info.get('player_name') if admin_info else 'Admin',
                'reason': reason,
                'match_id': match_id,
                'resolution': resolution,
                'mmr_change': mmr_change,
                'player_1_name': p1_name,
                'player_2_name': p2_name,
                'player_1_country': p1_country,
                'player_2_country': p2_country,
                'player_1_race': p1_race,
                'player_2_race': p2_race,
                'map_name': map_name or 'Unknown',
                'player_1_mmr_before': p1_mmr_initial or 0,
                'player_2_mmr_before': p2_mmr_initial or 0,
                'player_1_mmr_after': p1_mmr_after or 0,
                'player_2_mmr_after': p2_mmr_after or 0,
                'player_1_rank': p1_rank,
                'player_2_rank': p2_rank
            }
        }
    
    async def _update_player_reports_directly(
        self,
        match_id: int,
        p1_uid: int,
        p2_uid: int,
        report_value: int
    ) -> None:
        """
        Directly update both player reports in the DataFrame.
        Bypasses record_match_result's terminal state guard.
        """
        if self.data_service._matches_1v1_df is None:
            raise ValueError("Matches DataFrame not initialized")
        
        import polars as pl
        
        # Update both reports directly in memory
        self.data_service._matches_1v1_df = self.data_service._matches_1v1_df.with_columns([
            pl.when(pl.col("id") == match_id)
              .then(pl.lit(report_value))
              .otherwise(pl.col("player_1_report"))
              .alias("player_1_report"),
            pl.when(pl.col("id") == match_id)
              .then(pl.lit(report_value))
              .otherwise(pl.col("player_2_report"))
              .alias("player_2_report")
        ])
        
        print(f"[AdminService] Updated player_1_report and player_2_report to {report_value} for match {match_id}")
        
        # Queue database writes for both reports
        from src.backend.services.data_access_service import WriteJob, WriteJobType
        import time
        
        for player_uid in [p1_uid, p2_uid]:
            job = WriteJob(
                job_type=WriteJobType.UPDATE_MATCH_REPORT,
                data={
                    "match_id": match_id,
                    "player_discord_uid": player_uid,
                    "report_value": report_value
                },
                timestamp=time.time()
            )
            await self.data_service._queue_write(job)
        
        print(f"[AdminService] Queued database writes for both player reports")
    
    # NOTE: _restore_player_reports method removed - replaced by ADMIN_RESOLVE_MATCH write job
    # which atomically restores reports, sets match_result, and timestamps updated_at
    
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
                # Remove from matchmaker
                await matchmaker.remove_player(discord_uid)
                print(f"[AdminService] Removed player {discord_uid} from matchmaking queue")
                
                # Reset player state to idle
                await self.data_service.set_player_state(discord_uid, "idle")
                
                # Clear queue-locked state so player can re-queue
                await self._clear_player_queue_lock(discord_uid)
                
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
            
            await self.data_service.update_remaining_aborts(
                discord_uid, 
                new_count,
                changed_by=f"admin:{admin_discord_id}"
            )
            
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
    
    async def unblock_player_state(
        self,
        discord_uid: int,
        admin_discord_id: int,
        reason: str
    ) -> dict:
        """
        Reset player state to idle. Use this to fix stuck players.
        
        Args:
            discord_uid: Player to unblock
            admin_discord_id: Admin performing action
            reason: Explanation for audit log
        
        Returns:
            Dict with success status
        """
        try:
            current_state = self.data_service.get_player_state(discord_uid)
            success = await self.data_service.set_player_state(discord_uid, "idle")
            
            if success:
                await self._log_admin_action(
                    admin_discord_id=admin_discord_id,
                    action_type='unblock_player_state',
                    target_player_uid=discord_uid,
                    details={'reason': reason, 'old_state': current_state}
                )
                return {
                    'success': True,
                    'discord_uid': discord_uid,
                    'old_state': current_state
                }
            else:
                return {'success': False, 'error': 'Player not found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def toggle_ban_status(
        self,
        discord_uid: int,
        admin_discord_id: int,
        reason: str
    ) -> dict:
        """
        Toggle the is_banned status for a player.
        Returns dict with old_status, new_status, player_name, notification.
        """
        try:
            # Get current status
            current_banned = self.data_service.get_is_banned(discord_uid)
            new_banned = not current_banned
            
            # Update status
            await self.data_service.set_is_banned(
                discord_uid, 
                new_banned,
                changed_by=f"admin:{admin_discord_id}",
                reason=reason
            )
            
            # Get player info for logging
            player = self.data_service.get_player_info(discord_uid)
            player_name = player.get("player_name", "Unknown") if player else "Unknown"
            
            # Get admin name for notifications
            admin_name = None
            try:
                admin_player = self.data_service.get_player_info(admin_discord_id)
                admin_name = admin_player.get("player_name", "Admin") if admin_player else "Admin"
            except Exception:
                admin_name = "Admin"
            
            # Log admin action
            await self._log_admin_action(
                admin_discord_id=admin_discord_id,
                action_type="toggle_ban",
                target_player_uid=discord_uid,
                details={
                    "reason": reason,
                    "old_status": current_banned,
                    "new_status": new_banned
                }
            )
            
            return {
                "success": True,
                "old_status": current_banned,
                "new_status": new_banned,
                "player_name": player_name,
                "notification": {
                    "player_uid": discord_uid,
                    "admin_name": admin_name,
                    "reason": reason
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
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
        
        try:
            # Get all player IDs from matchmaker before clearing
            async with matchmaker.lock:
                player_ids = [p.discord_user_id for p in matchmaker.players]
                count = len(player_ids)
                matchmaker.players.clear()
                print(f"[AdminService] EMERGENCY: Cleared matchmaker queue ({count} players)")
            
            # Reset player state to idle and clear queue-locked state for all removed players
            for player_id in player_ids:
                await self.data_service.set_player_state(player_id, "idle")
                await self._clear_player_queue_lock(player_id)
            
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
        admin_name = admin_info.get('player_name')
        
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
    
    # ========== LAYER 4: OWNER OPERATIONS ==========
    
    async def toggle_admin_status(
        self,
        discord_uid: int,
        username: str,
        owner_discord_id: int
    ) -> dict:
        """
        Toggle admin status for a user (owner-only operation).
        
        If user is currently an admin, remove them.
        If user is not an admin, add them.
        Cannot modify owner status.
        
        Args:
            discord_uid: Discord UID of user to toggle
            username: Discord username for the admin entry
            owner_discord_id: Discord UID of owner performing action
            
        Returns:
            Dict with success status and details
        """
        try:
            with open('data/misc/admins.json', 'r', encoding='utf-8') as f:
                admins_data = json.load(f)
            
            # Find existing entry
            existing_entry = None
            existing_index = None
            for idx, admin in enumerate(admins_data):
                if admin.get('discord_id') == discord_uid:
                    existing_entry = admin
                    existing_index = idx
                    break
            
            # Check if user is owner (owners cannot be removed)
            if existing_entry and existing_entry.get('role') == 'owner':
                return {
                    'success': False,
                    'error': 'Cannot modify owner status'
                }
            
            # Toggle admin status
            if existing_entry:
                # Remove admin
                admins_data.pop(existing_index)
                action = 'removed'
            else:
                # Add admin
                admins_data.append({
                    'discord_id': discord_uid,
                    'name': username,
                    'role': 'admin'
                })
                action = 'added'
            
            # Write back to file
            with open('data/misc/admins.json', 'w', encoding='utf-8') as f:
                json.dump(admins_data, f, indent=4)
            
            # Log owner action
            await self._log_admin_action(
                admin_discord_id=owner_discord_id,
                action_type='toggle_admin_status',
                details={
                    'target_discord_uid': discord_uid,
                    'target_username': username,
                    'action': action
                }
            )
            
            return {
                'success': True,
                'action': action,
                'discord_uid': discord_uid,
                'username': username
            }
            
        except FileNotFoundError:
            return {
                'success': False,
                'error': 'admins.json not found'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def forward_match_completion_to_admin_channel(
        self,
        embed: "discord.Embed",
        match_id: int,
        content: str = None
    ) -> bool:
        """
        Forward a match completion or abort embed to the admin monitoring channel.
        
        Args:
            embed: The Discord embed to forward (same embed sent to players)
            match_id: The match ID for logging purposes
            content: Optional content string (e.g., role mentions) to send with embed
            
        Returns:
            True if forwarded successfully, False otherwise
        """
        try:
            from src.backend.services.process_pool_health import get_bot_instance
            
            bot = get_bot_instance()
            if not bot:
                print(f"[AdminService] Cannot forward match {match_id} - bot instance not available")
                return False
            
            # Admin monitoring channel ID
            ADMIN_CHANNEL_ID = 1435182864290287636
            
            channel = bot.get_channel(ADMIN_CHANNEL_ID)
            if not channel:
                print(f"[AdminService] Cannot forward match {match_id} - admin channel {ADMIN_CHANNEL_ID} not found")
                return False
            
            # Send the embed to the admin channel with optional content
            await channel.send(content=content, embed=embed)
            print(f"[AdminService] Forwarded match {match_id} result to admin channel {ADMIN_CHANNEL_ID}")
            return True
            
        except Exception as e:
            print(f"[AdminService] Error forwarding match {match_id} to admin channel: {e}")
            import traceback
            traceback.print_exc()
            return False


admin_service = AdminService()

