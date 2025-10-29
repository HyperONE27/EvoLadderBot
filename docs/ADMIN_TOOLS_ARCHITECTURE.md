# Admin Tools Architecture - Complete Implementation Guide

**Created:** October 28, 2025  
**Challenge:** In-memory architecture requires special tools for admin intervention  
**Goal:** Enable admins to inspect, modify, and control the live bot without restarts

---

## The Core Problem: In-Memory State Synchronization

### Why Simple Database Edits Don't Work

**Your architecture:**
```
Database (Postgres/Supabase)
    ↕ (async writes)
In-Memory DataFrames (Polars)
    ↕ (instant reads)
Bot Logic & Discord UI
```

**The issue:**
1. Admin modifies database directly (e.g., SQL query in Supabase dashboard)
2. In-memory DataFrames still have old data
3. Bot continues using stale data
4. Changes don't take effect until bot restart

**Example failure scenario:**
```sql
-- Admin runs in Supabase dashboard:
UPDATE matches_1v1 SET match_result = 1, player_1_report = 1, player_2_report = 1 
WHERE id = 12345;

-- Problem: Bot's _matches_1v1_df still shows match_result = -2
-- Match completion service won't trigger
-- Players never get results notification
-- MMR never updates
```

---

## Solution Architecture: Three-Layer Admin System

### Layer 1: Read-Only Inspection (No State Changes)
**Purpose:** Debug live system, understand current state  
**Safety:** Cannot break anything  
**Implementation:** Simple query functions

### Layer 2: Controlled Modifications (State + Sync)
**Purpose:** Fix issues by modifying both DB and memory  
**Safety:** Atomic operations with rollback  
**Implementation:** Admin service methods

### Layer 3: Emergency Controls (Nuclear Options)
**Purpose:** Force state changes when everything fails  
**Safety:** Use with extreme caution  
**Implementation:** Direct service manipulation

---

## Layer 1: Inspection & Diagnostics

### 1.1 Memory Dump System

#### System State Snapshot
```python
# New file: src/backend/services/admin_service.py

class AdminService:
    """
    Administrative functions for live bot inspection and control.
    
    All methods are designed to work with the in-memory architecture and
    handle synchronization between database and DataFrames.
    """
    
    def __init__(self):
        self.data_service = DataAccessService()
        self.action_log = []  # Track all admin actions
    
    # ========== LAYER 1: READ-ONLY INSPECTION ==========
    
    def get_system_snapshot(self) -> dict:
        """
        Get complete system state snapshot for debugging.
        
        Returns:
            Comprehensive dict with all system state
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
                'size': len(ranking_service._rank_cache) if ranking_service else 0
            }
        }
    
    def _get_memory_stats(self) -> dict:
        """Get memory usage statistics."""
        import psutil
        process = psutil.Process()
        mem = process.memory_info()
        
        return {
            'rss_mb': mem.rss / 1024 / 1024,
            'vms_mb': mem.vms / 1024 / 1024,
            'percent': process.memory_percent(),
            'available_mb': psutil.virtual_memory().available / 1024 / 1024
        }
    
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
        from src.backend.services.process_pool_health import _bot_instance
        
        if _bot_instance and hasattr(_bot_instance, 'process_pool'):
            return {
                'exists': True,
                'workers': _bot_instance.process_pool._max_workers if _bot_instance.process_pool else 0,
                'restart_count': getattr(_bot_instance, '_pool_restart_count', 0)
            }
        return {'exists': False}
    
    def get_conflict_matches(self) -> list:
        """
        Get all matches with conflicting reports (match_result = -2).
        
        Returns:
            List of conflict match dicts with full details
        """
        if self.data_service._matches_1v1_df is None:
            return []
        
        # Filter for conflicts
        conflicts = self.data_service._matches_1v1_df.filter(
            pl.col('match_result') == -2
        )
        
        result = []
        for row in conflicts.iter_rows(named=True):
            # Get player info
            p1_info = self.data_service.get_player_info(row['player_1_discord_uid'])
            p2_info = self.data_service.get_player_info(row['player_2_discord_uid'])
            
            # Get replays
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
    
    def get_player_full_state(self, discord_uid: int) -> dict:
        """
        Get complete state for a player (for debugging stuck states).
        
        Args:
            discord_uid: Player's Discord ID
            
        Returns:
            Dict with all player state information
        """
        from src.backend.services.queue_service import get_queue_service
        from src.backend.services.match_completion_service import match_completion_service
        
        queue_service = get_queue_service()
        
        # Basic player info
        player_info = self.data_service.get_player_info(discord_uid)
        
        # MMRs
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
        
        # Queue status
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
        
        # Active matches
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
        
        # Recent matches
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
            'recent_matches': recent_matches,
            'locks': {
                'has_queue_lock': f"queue_lock:{discord_uid}" in str(match_completion_service)  # Simplified
            }
        }
    
    def get_match_full_state(self, match_id: int) -> dict:
        """
        Get complete state for a match (for debugging completion issues).
        
        Args:
            match_id: Match ID
            
        Returns:
            Dict with all match state information
        """
        from src.backend.services.match_completion_service import match_completion_service
        
        # Match data from DataFrame
        match_data = self.data_service.get_match(match_id)
        
        if not match_data:
            return {'error': 'Match not found in memory'}
        
        # Monitoring status
        is_monitored = match_id in match_completion_service.monitored_matches
        is_processed = match_id in match_completion_service.processed_matches
        has_waiter = match_id in match_completion_service.completion_waiters
        has_lock = match_id in match_completion_service.processing_locks
        
        # Player info
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
```

### 1.2 Formatted Output Functions

```python
def format_system_snapshot(self, snapshot: dict) -> str:
    """
    Format system snapshot as human-readable text.
    
    Returns:
        Multi-line string suitable for Discord embed or log file
    """
    lines = [
        "=== SYSTEM SNAPSHOT ===",
        f"Timestamp: {snapshot['timestamp']}",
        "",
        "Memory:",
        f"  RSS: {snapshot['memory']['rss_mb']:.1f} MB",
        f"  Usage: {snapshot['memory']['percent']:.1f}%",
        "",
        "DataFrames:",
    ]
    
    for df_name, df_stats in snapshot['data_frames'].items():
        lines.append(f"  {df_name}:")
        lines.append(f"    Rows: {df_stats['rows']:,}")
        lines.append(f"    Size: {df_stats['size_mb']:.2f} MB")
    
    lines.extend([
        "",
        "Queue:",
        f"  Players: {snapshot['queue']['size']}",
        "",
        "Matches:",
        f"  Active: {snapshot['matches']['active']}",
        "",
        "Write Queue:",
        f"  Depth: {snapshot['write_queue']['depth']}",
        f"  Completed: {snapshot['write_queue']['total_completed']}",
        f"  Success Rate: {self._calc_success_rate(snapshot['write_queue'])}%",
        "",
        "Process Pool:",
        f"  Workers: {snapshot['process_pool'].get('workers', 0)}",
        f"  Restarts: {snapshot['process_pool'].get('restart_count', 0)}"
    ])
    
    return "\n".join(lines)

def _calc_success_rate(self, write_queue_stats: dict) -> float:
    """Calculate write success rate."""
    completed = write_queue_stats['total_completed']
    queued = write_queue_stats['total_queued']
    if queued == 0:
        return 100.0
    return (completed / queued) * 100

def format_conflict_match(self, conflict: dict) -> str:
    """
    Format conflict match for human reading.
    
    Returns:
        Formatted string suitable for Discord embed
    """
    lines = [
        f"**Match #{conflict['match_id']} - Conflict**",
        f"Map: {conflict['map']} | Server: {conflict['server']}",
        f"Played: <t:{int(conflict['played_at'].timestamp())}:R>",
        "",
        f"**Player 1:** {conflict['player_1']['name']}",
        f"  Race: {conflict['player_1']['race']}",
        f"  Reported: {self._format_report(conflict['player_1']['report'])}",
        f"  Replay: {'✅' if conflict['player_1']['replay'] else '❌'}",
        "",
        f"**Player 2:** {conflict['player_2']['name']}",
        f"  Race: {conflict['player_2']['race']}",
        f"  Reported: {self._format_report(conflict['player_2']['report'])}",
        f"  Replay: {'✅' if conflict['player_2']['replay'] else '❌'}"
    ]
    
    return "\n".join(lines)

def _format_report(self, report: int) -> str:
    """Format report value for display."""
    report_map = {
        0: "Draw",
        1: "I won",
        2: "I lost",
        -1: "Aborted",
        -3: "I aborted"
    }
    return report_map.get(report, f"Unknown ({report})")

def format_player_state(self, state: dict) -> str:
    """Format player state for human reading."""
    info = state['player_info']
    lines = [
        f"=== PLAYER STATE: {info.get('player_name', 'Unknown')} ===",
        f"Discord ID: {info['discord_uid']}",
        f"Country: {info.get('country', 'None')}",
        f"Region: {info.get('region', 'None')}",
        f"Remaining Aborts: {info.get('remaining_aborts', 0)}",
        "",
        "**MMRs:**"
    ]
    
    for race, mmr_data in state['mmrs'].items():
        lines.append(f"  {race}: {mmr_data['mmr']} ({mmr_data['games_played']} games)")
    
    lines.append("")
    lines.append(f"**Queue Status:** {'✅ IN QUEUE' if state['queue_status']['in_queue'] else '❌ Not in queue'}")
    
    if state['queue_status']['details']:
        details = state['queue_status']['details']
        lines.append(f"  Wait time: {details['wait_time']:.0f}s")
        lines.append(f"  Races: {', '.join(details['races'])}")
    
    lines.append("")
    lines.append(f"**Active Matches:** {len(state['active_matches'])}")
    
    for match in state['active_matches']:
        lines.append(f"  Match #{match['match_id']} ({match['status']})")
        lines.append(f"    My report: {self._format_report(match['my_report'])}")
        lines.append(f"    Their report: {self._format_report(match['their_report'])}")
    
    return "\n".join(lines)
```

---

## Layer 2: Controlled Modifications (WITH SYNC)

### 2.1 Match Conflict Resolution

```python
# Continue in AdminService class

# ========== LAYER 2: CONTROLLED MODIFICATIONS ==========

async def resolve_match_conflict(
    self,
    match_id: int,
    resolution: str,  # 'player_1_win', 'player_2_win', 'draw', 'invalidate'
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
    
    # Validate match exists and is a conflict
    match_data = self.data_service.get_match(match_id)
    if not match_data:
        return {'success': False, 'error': 'Match not found'}
    
    if match_data.get('match_result') != -2:
        return {'success': False, 'error': 'Match is not in conflict state'}
    
    # Map resolution to match_result value
    resolution_map = {
        'player_1_win': 1,
        'player_2_win': 2,
        'draw': 0,
        'invalidate': -1  # Treat as aborted (no MMR change)
    }
    
    if resolution not in resolution_map:
        return {'success': False, 'error': 'Invalid resolution'}
    
    new_result = resolution_map[resolution]
    
    try:
        # Step 1: Update in-memory DataFrame
        if self.data_service._matches_1v1_df is not None:
            self.data_service._matches_1v1_df = self.data_service._matches_1v1_df.with_columns([
                pl.when(pl.col("id") == match_id)
                  .then(pl.lit(new_result))
                  .otherwise(pl.col("match_result"))
                  .alias("match_result"),
                pl.when(pl.col("id") == match_id)
                  .then(pl.lit('PROCESSING_COMPLETION'))  # Trigger completion
                  .otherwise(pl.col("status"))
                  .alias("status")
            ])
            print(f"[AdminService] Updated match {match_id} in memory: result={new_result}")
        
        # Step 2: Update database
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self.data_service._db_writer.adapter.execute_write,
            "UPDATE matches_1v1 SET match_result = :result WHERE id = :match_id",
            {'result': new_result, 'match_id': match_id}
        )
        print(f"[AdminService] Updated match {match_id} in database: result={new_result}")
        
        # Step 3: Calculate MMR if not invalidated
        if resolution != 'invalidate':
            print(f"[AdminService] Triggering MMR calculation for match {match_id}")
            mmr_change = await matchmaker._calculate_and_write_mmr(match_id, match_data)
            print(f"[AdminService] MMR calculated: {mmr_change:+} (player 1 perspective)")
        else:
            mmr_change = 0
            print(f"[AdminService] Match invalidated, no MMR change")
        
        # Step 4: Trigger completion notification
        print(f"[AdminService] Triggering completion notification for match {match_id}")
        asyncio.create_task(match_completion_service.check_match_completion(match_id))
        
        # Step 5: Log admin action
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
        
        return {
            'success': True,
            'match_id': match_id,
            'resolution': resolution,
            'mmr_change': mmr_change
        }
        
    except Exception as e:
        print(f"[AdminService] ERROR resolving conflict for match {match_id}: {e}")
        return {'success': False, 'error': str(e)}

async def adjust_player_mmr(
    self,
    discord_uid: int,
    race: str,
    new_mmr: int,
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
        new_mmr: New MMR value
        admin_discord_id: Admin performing action
        reason: Explanation for audit log
        
    Returns:
        Dict with success status and details
    """
    try:
        # Get current MMR
        current_mmr = self.data_service.get_player_mmr(discord_uid, race)
        if current_mmr is None:
            return {'success': False, 'error': 'Player/race not found'}
        
        # Step 1: Update in-memory DataFrame
        if self.data_service._mmrs_1v1_df is not None:
            self.data_service._mmrs_1v1_df = self.data_service._mmrs_1v1_df.with_columns([
                pl.when(
                    (pl.col("discord_uid") == discord_uid) &
                    (pl.col("race") == race)
                )
                .then(pl.lit(new_mmr))
                .otherwise(pl.col("mmr"))
                .alias("mmr")
            ])
            print(f"[AdminService] Updated MMR in memory: {discord_uid}/{race}: {current_mmr} -> {new_mmr}")
        
        # Step 2: Update database
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self.data_service._db_writer.adapter.execute_write,
            "UPDATE mmrs_1v1 SET mmr = :mmr WHERE discord_uid = :uid AND race = :race",
            {'mmr': new_mmr, 'uid': discord_uid, 'race': race}
        )
        print(f"[AdminService] Updated MMR in database")
        
        # Step 3: Invalidate leaderboard cache
        from src.backend.services.leaderboard_service import LeaderboardService
        LeaderboardService.invalidate_cache()
        print(f"[AdminService] Invalidated leaderboard cache")
        
        # Step 4: Invalidate ranking cache
        from src.backend.services.app_context import ranking_service
        ranking_service.invalidate_player_rank(discord_uid, race)
        print(f"[AdminService] Invalidated ranking cache for player")
        
        # Step 5: Log admin action
        await self._log_admin_action(
            admin_discord_id=admin_discord_id,
            action_type='adjust_mmr',
            target_player_uid=discord_uid,
            details={
                'race': race,
                'old_mmr': current_mmr,
                'new_mmr': new_mmr,
                'change': new_mmr - current_mmr,
                'reason': reason
            }
        )
        
        return {
            'success': True,
            'discord_uid': discord_uid,
            'race': race,
            'old_mmr': current_mmr,
            'new_mmr': new_mmr,
            'change': new_mmr - current_mmr
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
    from src.backend.services.queue_service import get_queue_service
    
    queue_service = get_queue_service()
    if not queue_service:
        return {'success': False, 'error': 'Queue service not available'}
    
    try:
        was_in_queue = await queue_service.remove_player(discord_uid)
        
        if was_in_queue:
            # Log admin action
            await self._log_admin_action(
                admin_discord_id=admin_discord_id,
                action_type='force_remove_queue',
                target_player_uid=discord_uid,
                details={'reason': reason}
            )
            
            return {
                'success': True,
                'discord_uid': discord_uid,
                'was_in_queue': True
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
        # Get current count
        current = self.data_service.get_remaining_aborts(discord_uid)
        
        # Update in-memory and database
        await self.data_service.update_remaining_aborts(discord_uid, new_count)
        
        # Log admin action
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
        
        return {
            'success': True,
            'discord_uid': discord_uid,
            'old_count': current,
            'new_count': new_count
        }
        
    except Exception as e:
        print(f"[AdminService] ERROR resetting aborts: {e}")
        return {'success': False, 'error': str(e)}

async def _log_admin_action(
    self,
    admin_discord_id: int,
    action_type: str,
    target_player_uid: int = None,
    target_match_id: int = None,
    details: dict = None
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
    import json
    
    # Get admin name
    admin_info = self.data_service.get_player_info(admin_discord_id)
    admin_name = admin_info.get('player_name', 'Unknown') if admin_info else 'Unknown'
    
    # Insert into admin_actions table
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        self.data_service._db_writer.adapter.execute_write,
        """
        INSERT INTO admin_actions (
            admin_discord_uid, admin_username, action_type,
            target_player_uid, target_match_id, action_details, reason
        ) VALUES (
            :admin_uid, :admin_name, :action_type,
            :target_player, :target_match, :details, :reason
        )
        """,
        {
            'admin_uid': admin_discord_id,
            'admin_name': admin_name,
            'action_type': action_type,
            'target_player': target_player_uid,
            'target_match': target_match_id,
            'details': json.dumps(details or {}),
            'reason': details.get('reason', '') if details else ''
        }
    )
    
    print(f"[AdminService] Logged admin action: {action_type} by {admin_name}")
```

### 2.2 Emergency Memory Refresh

```python
async def force_reload_dataframe(
    self,
    dataframe_name: str,  # 'players', 'mmrs_1v1', 'matches_1v1', 'replays'
    admin_discord_id: int,
    reason: str
) -> dict:
    """
    Force reload a DataFrame from database (for emergency de-sync fixes).
    
    **WARNING:** This is expensive and blocks write operations briefly.
    Only use when memory state is known to be corrupt.
    
    Args:
        dataframe_name: Which DataFrame to reload
        admin_discord_id: Admin performing action
        reason: Explanation for audit log
        
    Returns:
        Dict with success status
    """
    valid_dfs = ['players', 'mmrs_1v1', 'matches_1v1', 'preferences_1v1', 'replays']
    
    if dataframe_name not in valid_dfs:
        return {'success': False, 'error': f'Invalid dataframe. Valid: {valid_dfs}'}
    
    try:
        print(f"[AdminService] WARNING: Force reloading {dataframe_name} DataFrame")
        
        # This is dangerous - temporarily pause writes
        # (In production, would need more sophisticated locking)
        
        loop = asyncio.get_running_loop()
        
        if dataframe_name == 'players':
            players_data = await loop.run_in_executor(
                None,
                self.data_service._db_reader.get_all_players
            )
            if players_data:
                self.data_service._players_df = pl.DataFrame(players_data, infer_schema_length=None)
        
        elif dataframe_name == 'mmrs_1v1':
            mmrs_data = await loop.run_in_executor(
                None,
                self.data_service._db_reader.get_leaderboard_1v1,
                None, None, None, 0
            )
            if mmrs_data:
                self.data_service._mmrs_1v1_df = pl.DataFrame(mmrs_data, infer_schema_length=None)
            
            # Invalidate caches
            from src.backend.services.leaderboard_service import LeaderboardService
            LeaderboardService.invalidate_cache()
        
        elif dataframe_name == 'matches_1v1':
            matches_data = await loop.run_in_executor(
                None,
                self.data_service._db_reader.adapter.execute_query,
                "SELECT * FROM matches_1v1 ORDER BY played_at DESC",
                {}
            )
            if matches_data:
                self.data_service._matches_1v1_df = pl.DataFrame(matches_data, infer_schema_length=None)
        
        # Log admin action
        await self._log_admin_action(
            admin_discord_id=admin_discord_id,
            action_type='force_reload_dataframe',
            details={
                'dataframe': dataframe_name,
                'reason': reason
            }
        )
        
        print(f"[AdminService] Successfully reloaded {dataframe_name}")
        
        return {
            'success': True,
            'dataframe': dataframe_name,
            'rows': len(getattr(self.data_service, f'_{dataframe_name}_df'))
        }
        
    except Exception as e:
        print(f"[AdminService] ERROR reloading DataFrame: {e}")
        return {'success': False, 'error': str(e)}
```

---

## Layer 3: Emergency Controls (Nuclear Options)

### 3.1 System-Wide Operations

```python
# ========== LAYER 3: EMERGENCY CONTROLS ==========

async def emergency_clear_queue(
    self,
    admin_discord_id: int,
    reason: str
) -> dict:
    """
    Emergency: Clear entire matchmaking queue.
    
    **WARNING:** Removes all players from queue immediately.
    Use only if queue is in corrupted state.
    
    Args:
        admin_discord_id: Admin performing action
        reason: Explanation for audit log
        
    Returns:
        Dict with count of removed players
    """
    from src.backend.services.queue_service import get_queue_service
    
    queue_service = get_queue_service()
    if not queue_service:
        return {'success': False, 'error': 'Queue service not available'}
    
    try:
        count = await queue_service.clear_queue()
        
        # Log admin action
        await self._log_admin_action(
            admin_discord_id=admin_discord_id,
            action_type='emergency_clear_queue',
            details={
                'players_removed': count,
                'reason': reason
            }
        )
        
        print(f"[AdminService] EMERGENCY: Cleared entire queue ({count} players)")
        
        return {
            'success': True,
            'players_removed': count
        }
        
    except Exception as e:
        print(f"[AdminService] ERROR clearing queue: {e}")
        return {'success': False, 'error': str(e)}

async def emergency_stop_match_monitoring(
    self,
    match_id: int,
    admin_discord_id: int,
    reason: str
) -> dict:
    """
    Emergency: Stop monitoring a match (for stuck monitors).
    
    **WARNING:** Stops completion service from processing match.
    Use only if match monitor is stuck in infinite loop.
    
    Args:
        match_id: Match to stop monitoring
        admin_discord_id: Admin performing action
        reason: Explanation for audit log
        
    Returns:
        Dict with success status
    """
    from src.backend.services.match_completion_service import match_completion_service
    
    try:
        match_completion_service.stop_monitoring_match(match_id)
        
        # Log admin action
        await self._log_admin_action(
            admin_discord_id=admin_discord_id,
            action_type='emergency_stop_monitoring',
            target_match_id=match_id,
            details={'reason': reason}
        )
        
        print(f"[AdminService] EMERGENCY: Stopped monitoring match {match_id}")
        
        return {
            'success': True,
            'match_id': match_id
        }
        
    except Exception as e:
        print(f"[AdminService] ERROR stopping monitor: {e}")
        return {'success': False, 'error': str(e)}

async def emergency_restart_process_pool(
    self,
    admin_discord_id: int,
    reason: str
) -> dict:
    """
    Emergency: Restart the replay parsing process pool.
    
    **WARNING:** Cancels all in-progress replay parsing tasks.
    Use only if process pool is completely unresponsive.
    
    Args:
        admin_discord_id: Admin performing action
        reason: Explanation for audit log
        
    Returns:
        Dict with success status
    """
    from src.backend.services.process_pool_health import _bot_instance
    
    if not _bot_instance:
        return {'success': False, 'error': 'Bot instance not available'}
    
    try:
        success = await _bot_instance._restart_process_pool()
        
        # Log admin action
        await self._log_admin_action(
            admin_discord_id=admin_discord_id,
            action_type='emergency_restart_process_pool',
            details={'reason': reason}
        )
        
        print(f"[AdminService] EMERGENCY: Restarted process pool")
        
        return {
            'success': success,
            'workers': _bot_instance.process_pool._max_workers if success else 0
        }
        
    except Exception as e:
        print(f"[AdminService] ERROR restarting process pool: {e}")
        return {'success': False, 'error': str(e)}
```

---

## Discord Command Interface

### Admin Command Registration

```python
# New file: src/bot/commands/admin_command.py

import discord
from discord import app_commands
from typing import Optional
import json

from src.backend.services.admin_service import AdminService
from src.bot.utils.discord_utils import send_ephemeral_response


# Admin role check
ADMIN_ROLE_IDS = [int(id) for id in os.getenv("ADMIN_ROLE_IDS", "").split(",") if id]
ADMIN_USER_IDS = [int(id) for id in os.getenv("ADMIN_USER_IDS", "").split(",") if id]

def is_admin(user: discord.User) -> bool:
    """Check if user is an admin."""
    if user.id in ADMIN_USER_IDS:
        return True
    
    if hasattr(user, 'roles'):
        return any(role.id in ADMIN_ROLE_IDS for role in user.roles)
    
    return False

def admin_only(func):
    """Decorator to restrict commands to admins."""
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        if not is_admin(interaction.user):
            await send_ephemeral_response(
                interaction,
                embed=discord.Embed(
                    title="🚫 Access Denied",
                    description="This command is restricted to administrators.",
                    color=discord.Color.red()
                )
            )
            return
        return await func(interaction, *args, **kwargs)
    return wrapper


# Admin service singleton
admin_service = AdminService()


# ========== COMMANDS ==========

def register_admin_commands(tree: app_commands.CommandTree):
    """Register all admin commands."""
    
    # Main admin group
    admin_group = app_commands.Group(name="admin", description="Admin tools")
    
    # Layer 1: Inspection commands
    @admin_group.command(name="snapshot", description="Get system state snapshot")
    @admin_only
    async def admin_snapshot(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        snapshot = admin_service.get_system_snapshot()
        formatted = admin_service.format_system_snapshot(snapshot)
        
        # Send as file if too long
        if len(formatted) > 1900:
            file = discord.File(
                io.BytesIO(formatted.encode()),
                filename=f"snapshot_{int(time.time())}.txt"
            )
            await interaction.followup.send(
                content="System snapshot:",
                file=file,
                ephemeral=True
            )
        else:
            embed = discord.Embed(
                title="System Snapshot",
                description=f"```\n{formatted}\n```",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    @admin_group.command(name="conflicts", description="List all match conflicts")
    @admin_only
    async def admin_conflicts(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        conflicts = admin_service.get_conflict_matches()
        
        if not conflicts:
            embed = discord.Embed(
                title="No Conflicts",
                description="No matches with conflicting reports found.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Create embeds for each conflict (max 10)
        embeds = []
        for conflict in conflicts[:10]:
            formatted = admin_service.format_conflict_match(conflict)
            embed = discord.Embed(
                title=f"Match #{conflict['match_id']}",
                description=formatted,
                color=discord.Color.orange()
            )
            embeds.append(embed)
        
        await interaction.followup.send(embeds=embeds, ephemeral=True)
    
    @admin_group.command(name="player", description="View player state")
    @app_commands.describe(discord_id="Player's Discord ID")
    @admin_only
    async def admin_player(interaction: discord.Interaction, discord_id: str):
        await interaction.response.defer(ephemeral=True)
        
        try:
            uid = int(discord_id)
            state = admin_service.get_player_full_state(uid)
            formatted = admin_service.format_player_state(state)
            
            embed = discord.Embed(
                title="Player State",
                description=formatted,
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.followup.send(
                content="Invalid Discord ID (must be numeric)",
                ephemeral=True
            )
    
    @admin_group.command(name="match", description="View match state")
    @app_commands.describe(match_id="Match ID")
    @admin_only
    async def admin_match(interaction: discord.Interaction, match_id: int):
        await interaction.response.defer(ephemeral=True)
        
        state = admin_service.get_match_full_state(match_id)
        
        if 'error' in state:
            await interaction.followup.send(
                content=f"Error: {state['error']}",
                ephemeral=True
            )
            return
        
        # Format match state
        formatted = json.dumps(state, indent=2, default=str)
        
        file = discord.File(
            io.BytesIO(formatted.encode()),
            filename=f"match_{match_id}.json"
        )
        await interaction.followup.send(
            content=f"Match #{match_id} state:",
            file=file,
            ephemeral=True
        )
    
    # Layer 2: Modification commands
    @admin_group.command(name="resolve", description="Resolve match conflict")
    @app_commands.describe(
        match_id="Match ID with conflict",
        winner="Who wins? (1=player1, 2=player2, 0=draw, -1=invalidate)",
        reason="Reason for resolution"
    )
    @admin_only
    async def admin_resolve(
        interaction: discord.Interaction,
        match_id: int,
        winner: int,
        reason: str
    ):
        await interaction.response.defer(ephemeral=True)
        
        # Map winner to resolution
        winner_map = {
            1: 'player_1_win',
            2: 'player_2_win',
            0: 'draw',
            -1: 'invalidate'
        }
        
        if winner not in winner_map:
            await interaction.followup.send(
                content="Invalid winner (must be 1, 2, 0, or -1)",
                ephemeral=True
            )
            return
        
        result = await admin_service.resolve_match_conflict(
            match_id=match_id,
            resolution=winner_map[winner],
            admin_discord_id=interaction.user.id,
            reason=reason
        )
        
        if result['success']:
            embed = discord.Embed(
                title="✅ Conflict Resolved",
                description=f"Match #{match_id} resolved as **{winner_map[winner]}**\n"
                           f"MMR Change: {result['mmr_change']:+}\n"
                           f"Reason: {reason}",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="❌ Resolution Failed",
                description=f"Error: {result.get('error', 'Unknown error')}",
                color=discord.Color.red()
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @admin_group.command(name="adjust_mmr", description="Adjust player MMR")
    @app_commands.describe(
        discord_id="Player's Discord ID",
        race="Race (e.g., bw_terran)",
        new_mmr="New MMR value",
        reason="Reason for adjustment"
    )
    @admin_only
    async def admin_adjust_mmr(
        interaction: discord.Interaction,
        discord_id: str,
        race: str,
        new_mmr: int,
        reason: str
    ):
        await interaction.response.defer(ephemeral=True)
        
        try:
            uid = int(discord_id)
            
            result = await admin_service.adjust_player_mmr(
                discord_uid=uid,
                race=race,
                new_mmr=new_mmr,
                admin_discord_id=interaction.user.id,
                reason=reason
            )
            
            if result['success']:
                embed = discord.Embed(
                    title="✅ MMR Adjusted",
                    description=f"Player <@{uid}> | {race}\n"
                               f"Old MMR: {result['old_mmr']}\n"
                               f"New MMR: {result['new_mmr']}\n"
                               f"Change: {result['change']:+}\n"
                               f"Reason: {reason}",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Adjustment Failed",
                    description=f"Error: {result.get('error', 'Unknown error')}",
                    color=discord.Color.red()
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.followup.send(
                content="Invalid Discord ID",
                ephemeral=True
            )
    
    # Register the group
    tree.add_command(admin_group)
```

---

## Implementation Priority

### Phase 1: Immediate (Pre-Launch) ✅
1. Create `AdminService` class with Layer 1 functions
2. Add snapshot, conflicts, player state viewers
3. Test memory dumps and formatting
4. **Estimated time:** 4-6 hours

### Phase 2: Launch Day (Week 1) 🔥
1. Implement conflict resolution (resolve_match_conflict)
2. Add admin command interface
3. Create admin_actions table for audit log
4. **Estimated time:** 6-8 hours

### Phase 3: Post-Launch (Week 2-3) 📊
1. Add MMR adjustment tools
2. Implement queue management commands
3. Add force reload functions
4. **Estimated time:** 4-6 hours

### Phase 4: As Needed (Month 1+) 🚀
1. Emergency controls (if needed)
2. Advanced diagnostics
3. Bulk operations
4. **Estimated time:** Variable

---

## Database Schema Addition

```sql
-- Add to your schema
CREATE TABLE admin_actions (
    id                  SERIAL PRIMARY KEY,
    admin_discord_uid   BIGINT NOT NULL,
    admin_username      TEXT NOT NULL,
    action_type         TEXT NOT NULL,
    target_player_uid   BIGINT,
    target_match_id     INTEGER,
    action_details      JSONB NOT NULL,
    reason              TEXT,
    performed_at        TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (admin_discord_uid) REFERENCES players(discord_uid)
);

CREATE INDEX idx_admin_actions_performed_at ON admin_actions(performed_at DESC);
CREATE INDEX idx_admin_actions_admin ON admin_actions(admin_discord_uid);
CREATE INDEX idx_admin_actions_target_player ON admin_actions(target_player_uid);
CREATE INDEX idx_admin_actions_target_match ON admin_actions(target_match_id);
CREATE INDEX idx_admin_actions_type ON admin_actions(action_type);
```

---

## Environment Configuration

```env
# In Railway/local .env
ADMIN_ROLE_IDS=123456789012345678,234567890123456789
ADMIN_USER_IDS=345678901234567890
```

---

## Safety Guidelines

### Before Modifying State:
1. ✅ Get current state snapshot
2. ✅ Verify issue exists
3. ✅ Document reason
4. ✅ Test in staging first (if possible)
5. ✅ Have rollback plan

### After Modification:
1. ✅ Verify change took effect (check snapshot)
2. ✅ Monitor for side effects (5-10 minutes)
3. ✅ Document outcome
4. ✅ Check audit log was written

### Never:
- ❌ Modify database directly without using AdminService
- ❌ Skip audit logging
- ❌ Use emergency controls unless absolutely necessary
- ❌ Modify state during active matchmaking wave

---

## Common Admin Scenarios & Solutions

### Scenario 1: Match Conflict
**Problem:** Players disagree on match result  
**Solution:** `/admin conflicts` → `/admin resolve`  
**Time:** 2-3 minutes

### Scenario 2: Player Stuck in Queue
**Problem:** Player can't leave queue  
**Solution:** `/admin player {id}` → verify → `/admin remove_queue`  
**Time:** 1-2 minutes

### Scenario 3: Wrong MMR After Bug
**Problem:** MMR incorrectly calculated  
**Solution:** `/admin player {id}` → calculate correct → `/admin adjust_mmr`  
**Time:** 3-5 minutes

### Scenario 4: System Acting Weird
**Problem:** Unclear what's wrong  
**Solution:** `/admin snapshot` → analyze → specific fix  
**Time:** 5-10 minutes

### Scenario 5: Memory Out of Sync with DB
**Problem:** Bot shows old data  
**Solution:** `/admin force_reload {dataframe}` (nuclear option)  
**Time:** 30 seconds
**Warning:** Should rarely be needed

---

## Testing Checklist

### Layer 1 (Inspection):
- [ ] System snapshot shows all data
- [ ] Conflict list displays correctly
- [ ] Player state shows queue/match status
- [ ] Match state shows all details
- [ ] Formatted output is readable

### Layer 2 (Modifications):
- [ ] Conflict resolution updates database
- [ ] Conflict resolution updates memory
- [ ] Conflict resolution triggers MMR calc
- [ ] Conflict resolution notifies players
- [ ] MMR adjustment invalidates caches
- [ ] Audit log records all actions

### Layer 3 (Emergency):
- [ ] Queue clear works
- [ ] Process pool restart works
- [ ] DataFrame reload works
- [ ] All emergency actions log properly

---

## Summary

You've identified the core challenge: **in-memory state requires synchronized modifications**.

**The solution:**
1. **Never modify database directly** - Use AdminService
2. **AdminService handles sync** - Updates DB + memory + caches
3. **Three layers** - Inspection (safe) → Modifications (controlled) → Emergency (nuclear)
4. **Full audit trail** - All admin actions logged
5. **Discord commands** - Easy interface for admins

**This architecture lets admins:**
- ✅ View live system state (memory dumps)
- ✅ Resolve conflicts with one command
- ✅ Fix player issues without restart
- ✅ Adjust MMR safely
- ✅ Emergency controls if needed
- ✅ Full audit trail

**Implementation time:** 
- Phase 1 (inspection): 4-6 hours
- Phase 2 (conflict resolution): 6-8 hours
- **Total for launch-critical tools: 10-14 hours**

Want me to start implementing the AdminService class?

