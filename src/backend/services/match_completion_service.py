"""
Match completion monitoring service.

This service monitors matches to detect when they are fully completed
and handles the finalization process including notifying both players.
"""

import asyncio
from asyncio import Lock
from typing import Callable, Dict, List, Optional, Set

from src.backend.db.db_reader_writer import DatabaseReader
from src.backend.services.leaderboard_service import LeaderboardService


class MatchCompletionService:
    """Service for monitoring match completion and handling finalization."""
    
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MatchCompletionService, cls).__new__(cls)
            cls._instance.db_reader = DatabaseReader()
            cls._instance.monitored_matches = set()
            cls._instance.monitoring_tasks = {}
            cls._instance.processed_matches = set()
            cls._instance.completion_waiters = {}
            cls._instance.processing_locks: Dict[int, Lock] = {}
            # New dictionary to store callbacks
            cls._instance.notification_callbacks: Dict[int, List[Callable]] = {}
        return cls._instance
    
    def _get_lock(self, match_id: int) -> Lock:
        """Get the lock for a given match ID, creating it if it doesn't exist."""
        if match_id not in self.processing_locks:
            self.processing_locks[match_id] = Lock()
        return self.processing_locks[match_id]

    def start_monitoring_match(self, match_id: int, on_complete_callback: Optional[Callable] = None):
        """
        Start monitoring a match for completion.
        A callback can be provided to be executed upon match completion or conflict.
        """
        if match_id in self.monitored_matches:
            # If a new callback is provided for an already monitored match, add it
            if on_complete_callback:
                if match_id not in self.notification_callbacks:
                    self.notification_callbacks[match_id] = []
                self.notification_callbacks[match_id].append(on_complete_callback)
            return

        self.monitored_matches.add(match_id)
        
        if on_complete_callback:
            if match_id not in self.notification_callbacks:
                self.notification_callbacks[match_id] = []
            self.notification_callbacks[match_id].append(on_complete_callback)

        task = asyncio.create_task(self._monitor_match_completion(match_id))
        self.monitoring_tasks[match_id] = task
        print(f"👁️ Started monitoring match {match_id}")
    
    def stop_monitoring_match(self, match_id: int):
        """Stop monitoring a match."""
        if match_id not in self.monitored_matches:
            return
        
        self.monitored_matches.remove(match_id)
        
        task = self.monitoring_tasks.pop(match_id, None)
        if task:
            task.cancel()
        
        # Clean up callbacks and locks
        self.notification_callbacks.pop(match_id, None)
        self.processing_locks.pop(match_id, None)

        print(f"🛑 Stopped monitoring match {match_id}")
    
    async def wait_for_match_completion(self, match_id: int, timeout: int = 30) -> Optional[dict]:
        """
        Wait for a match to be fully completed and return the final results.
        
        Args:
            match_id: The ID of the match to wait for
            timeout: Maximum time to wait in seconds
            
        Returns:
            Dictionary with final match results or None if timeout/error
        """
        try:
            # Check if match is already completed
            if match_id in self.processed_matches:
                print(f"🔍 WAIT: Match {match_id} already processed, getting results")
                return await self._get_match_final_results(match_id)
            
            # Create an event to wait for completion
            if match_id not in self.completion_waiters:
                self.completion_waiters[match_id] = asyncio.Event()
            
            completion_event = self.completion_waiters[match_id]
            
            # Wait for completion with timeout
            try:
                await asyncio.wait_for(completion_event.wait(), timeout=timeout)
                print(f"✅ WAIT: Match {match_id} completed, returning results")
                return await self._get_match_final_results(match_id)
            except asyncio.TimeoutError:
                print(f"⏰ WAIT: Match {match_id} completion timed out after {timeout} seconds")
                return None
                
        except Exception as e:
            print(f"❌ Error waiting for match {match_id} completion: {e}")
            return None

    async def check_match_completion(self, match_id: int):
        """Manually check if a match is complete and handle it."""
        
        lock = self._get_lock(match_id)
        async with lock:
            try:
                # Prevent duplicate processing
                if match_id in self.processed_matches:
                    print(f"🔍 CHECK: Match {match_id} already processed, skipping")
                    return True
                    
                print(f"🔍 CHECK: Manual completion check for match {match_id}")
                match_data = self.db_reader.get_match_1v1(match_id)
                if not match_data:
                    print(f"❌ Match {match_id} not found for completion check")
                    return
                
                # Check if both players have reported
                p1_report = match_data.get('player_1_report')
                p2_report = match_data.get('player_2_report')
                match_result = match_data.get('match_result')
                
                print(f"🔍 CHECK: Match {match_id} reports: p1={p1_report}, p2={p2_report}, result={match_result}")
                
                # Abort if any report is -3 (initiator) or both are -1/-3 with match_result=-1
                if (p1_report == -3 or p2_report == -3) or (match_result == -1 and (p1_report in (-3, -1) and p2_report in (-3, -1))):
                    print(f"🚫 Match {match_id} was aborted")
                    self.processed_matches.add(match_id)  # Mark as processed
                    await self._handle_match_abort(match_id, match_data)
                    
                    # Notify any waiting tasks
                    if match_id in self.completion_waiters:
                        self.completion_waiters[match_id].set()
                        del self.completion_waiters[match_id]
                    
                    return True
                
                if p1_report is not None and p2_report is not None:
                    if match_result == -2:
                        # Conflicting reports - manual resolution needed
                        print(f"⚠️ Conflicting reports for match {match_id}, manual resolution required")
                        await self._handle_match_conflict(match_id)
                    elif match_result is not None:
                        # Match is complete and processed
                        print(f"✅ CHECK: Match {match_id} completed successfully")
                        self.processed_matches.add(match_id)  # Mark as processed
                        await self._handle_match_completion(match_id, match_data)
                        
                        # Invalidate leaderboard cache since MMR values changed
                        LeaderboardService.invalidate_cache()
                        
                        # Notify any waiting tasks
                        if match_id in self.completion_waiters:
                            self.completion_waiters[match_id].set()
                            del self.completion_waiters[match_id]
                        
                        return True
                else:
                    print(f"📝 CHECK: Match {match_id} still waiting for reports: p1={p1_report}, p2={p2_report}")
                
                return False
            except Exception as e:
                print(f"❌ Error checking match completion for {match_id}: {e}")
                return False
    
    async def _monitor_match_completion(self, match_id: int):
        """Monitor a specific match for completion."""
        try:
            while match_id in self.monitored_matches:
                # Check if match is complete
                lock = self._get_lock(match_id)
                async with lock:
                    match_data = self.db_reader.get_match_1v1(match_id)
                    if not match_data:
                        print(f"❌ Match {match_id} not found, stopping monitoring")
                        break
                    
                    # Check if both players have reported
                    p1_report = match_data.get('player_1_report')
                    p2_report = match_data.get('player_2_report')
                    match_result = match_data.get('match_result')
                    
                    # Check for aborts (-3 initiator, -1 other)
                    if (p1_report == -3 or p2_report == -3) or (match_result == -1 and (p1_report in (-3, -1) and p2_report in (-3, -1))):
                        await self._handle_match_abort(match_id, match_data)
                        break
                    
                    if p1_report is not None and p2_report is not None:
                        # If both reports are in, process the result
                        if match_data.get('player_1_report') == match_data.get('player_2_report'):
                            await self._handle_match_completion(match_id, match_data)
                        else:
                            await self._handle_match_conflict(match_id)
                        
                        # Match is processed, break the loop
                        break
            
                await asyncio.sleep(5)  # Check every 5 seconds
                
        except asyncio.CancelledError:
            print(f"🛑 Match {match_id} monitoring cancelled")
        except Exception as e:
            print(f"❌ Error monitoring match {match_id}: {e}")
        finally:
            # Clean up
            self.stop_monitoring_match(match_id)
            self.processing_locks.pop(match_id, None) # Clean up the lock
    
    async def _handle_match_completion(self, match_id: int, match_data: dict):
        """Handle a completed match."""
        try:
            from src.backend.services.matchmaking_service import matchmaker
            
            # Calculate and write MMR changes
            await matchmaker._calculate_and_write_mmr(match_id, match_data)

            # Re-fetch match data to ensure it's the absolute latest
            final_match_data = await self._get_match_final_results(match_id)
            if not final_match_data:
                print(f"❌ Could not get final results for match {match_id} during handling.")
                return

            # Mark as processed and notify any waiters
            if match_id not in self.processed_matches:
                self.processed_matches.add(match_id)
                if match_id in self.completion_waiters:
                    self.completion_waiters[match_id].set()
                    del self.completion_waiters[match_id]

            # Notify/update all player views with the final data
            await self._notify_players_match_complete(match_id, final_match_data)
            
        except Exception as e:
            print(f"❌ Error handling match completion for {match_id}: {e}")
    
    async def _handle_match_abort(self, match_id: int, match_data: dict):
        """Handle an aborted match."""
        try:
            # Re-fetch to ensure we have the latest state
            final_match_data = await self._get_match_final_results(match_id)
            if not final_match_data:
                final_match_data = match_data

            # Mark as processed (abort) and notify any waiters
            if match_id not in self.processed_matches:
                self.processed_matches.add(match_id)
                if match_id in self.completion_waiters:
                    self.completion_waiters[match_id].set()
                    del self.completion_waiters[match_id]

            # Notify all callbacks with abort status
            callbacks = self.notification_callbacks.pop(match_id, [])
            print(f"  -> Notifying {len(callbacks)} callbacks for match {match_id} abort.")
            for callback in callbacks:
                try:
                    await callback(status="abort", data={"match_id": match_id, "match_data": final_match_data})
                except Exception as e:
                    print(f"❌ Error executing abort callback for match {match_id}: {e}")

        except Exception as e:
            print(f"❌ Error handling match abort for {match_id}: {e}")
        finally:
            # Clean up monitoring for this match
            self.stop_monitoring_match(match_id)

    async def _handle_match_conflict(self, match_id: int):
        """Handle a match with conflicting reports."""
        try:
            # Update all views to show the conflict state
            await self._notify_players_of_conflict(match_id)

            # Mark as processed (conflict) and notify any waiters
            if match_id not in self.processed_matches:
                self.processed_matches.add(match_id)
                if match_id in self.completion_waiters:
                    self.completion_waiters[match_id].set()
                    del self.completion_waiters[match_id]
            
            # Send a new follow-up message to all channels
            # await self._send_conflict_notification(match_id) # REMOVED

        except Exception as e:
            print(f"❌ Error handling match conflict for {match_id}: {e}")
        finally:
            # Clean up monitoring for this match
            print(f"🧹 CLEANUP: Unregistering and stopping monitoring for conflict match {match_id}")
            # unregister_match_views_by_match_id(match_id) # REMOVED
            self.stop_monitoring_match(match_id)
            self.processing_locks.pop(match_id, None)

    async def _notify_players_match_complete(self, match_id: int, final_results: dict):
        """Notify all registered frontends that the match is complete."""
        callbacks = self.notification_callbacks.pop(match_id, [])
        print(f"  -> Notifying {len(callbacks)} callbacks for match {match_id} completion.")
        for callback in callbacks:
            try:
                # The callback itself is a coroutine
                await callback(status="complete", data=final_results)
            except Exception as e:
                print(f"❌ Error executing completion callback for match {match_id}: {e}")
        
        # Release queue lock for both players so they can queue again
        await self._release_queue_lock_for_completed_match(match_id, final_results)

    async def _release_queue_lock_for_completed_match(self, match_id: int, final_results: dict):
        """Release queue lock for both players when a match is completed."""
        try:
            # Get both players' Discord UIDs from the match data
            p1_discord_uid = final_results.get('player_1_discord_uid')
            p2_discord_uid = final_results.get('player_2_discord_uid')
            
            if p1_discord_uid and p2_discord_uid:
                # Use the matchmaker's release_queue_lock_for_players method
                from src.backend.services.matchmaking_service import matchmaker
                player_ids = [p1_discord_uid, p2_discord_uid]
                await matchmaker.release_queue_lock_for_players(player_ids)
                print(f"🔓 Released queue lock for completed match {match_id}")
            else:
                print(f"⚠️ Could not get player IDs for match {match_id} - skipping queue lock release")
        except Exception as e:
            print(f"❌ Error releasing queue lock for match {match_id}: {e}")

    async def _notify_players_of_conflict(self, match_id: int):
        """Notify all registered frontends of a match result conflict."""
        callbacks = self.notification_callbacks.pop(match_id, [])
        print(f"  -> Notifying {len(callbacks)} callbacks for match {match_id} conflict.")
        for callback in callbacks:
            try:
                await callback(status="conflict", data={"match_id": match_id})
            except Exception as e:
                print(f"❌ Error executing conflict callback for match {match_id}: {e}")
        
        # Release queue lock for both players so they can queue again after conflict
        await self._release_queue_lock_for_conflict_match(match_id)

    async def _release_queue_lock_for_conflict_match(self, match_id: int):
        """Release queue lock for both players when a match has a conflict."""
        try:
            # Get match data to find both players
            match_data = self.db_reader.get_match_1v1(match_id)
            if match_data:
                p1_discord_uid = match_data.get('player_1_discord_uid')
                p2_discord_uid = match_data.get('player_2_discord_uid')
                
                if p1_discord_uid and p2_discord_uid:
                    # Use the matchmaker's release_queue_lock_for_players method
                    from src.backend.services.matchmaking_service import matchmaker
                    player_ids = [p1_discord_uid, p2_discord_uid]
                    await matchmaker.release_queue_lock_for_players(player_ids)
                    print(f"🔓 Released queue lock for conflict match {match_id}")
                else:
                    print(f"⚠️ Could not get player IDs for conflict match {match_id} - skipping queue lock release")
            else:
                print(f"⚠️ Could not get match data for conflict match {match_id} - skipping queue lock release")
        except Exception as e:
            print(f"❌ Error releasing queue lock for conflict match {match_id}: {e}")

    async def _get_match_final_results(self, match_id: int) -> Optional[dict]:
        """
        Retrieves all necessary data for the final match result notification
        and calculates MMR changes.
        """
        try:
            match_data = self.db_reader.get_match_1v1(match_id)
            if not match_data:
                return None
            
            # This part should be re-evaluated, as it's frontend-specific
            # For now, it's kept for data structure compatibility
            p1_info = self.db_reader.get_player_by_discord_uid(match_data['player_1_discord_uid'])
            p2_info = self.db_reader.get_player_by_discord_uid(match_data['player_2_discord_uid'])

            p1_name = p1_info.get('player_name', str(match_data['player_1_discord_uid']))
            p2_name = p2_info.get('player_name', str(match_data['player_2_discord_uid']))

            result_text_map = {
                1: f"{p1_name} victory",
                2: f"{p2_name} victory",
                0: "Draw",
                -1: "Aborted",
                -2: "Conflict"
            }
            result_text = result_text_map.get(match_data['match_result'], "Undetermined")

            return {
                "match_id": match_id,
                "p1_info": p1_info,
                "p2_info": p2_info,
                "p1_name": p1_name,
                "p2_name": p2_name,
                "player_1_discord_uid": match_data['player_1_discord_uid'],
                "player_2_discord_uid": match_data['player_2_discord_uid'],
                "p1_race": match_data.get('player_1_race'),
                "p2_race": match_data.get('player_2_race'),
                "p1_current_mmr": match_data['player_1_mmr'],
                "p2_current_mmr": match_data['player_2_mmr'],
                "p1_mmr_change": match_data.get('mmr_change', 0),
                "p2_mmr_change": -match_data.get('mmr_change', 0),
                "p1_report": match_data.get('player_1_report'),
                "p2_report": match_data.get('player_2_report'),
                "result_text": result_text,
                "match_result_raw": match_data['match_result']
            }
            
        except Exception as e:
            print(f"❌ Error getting final results for match {match_id}: {e}")
            return None
    
    # REMOVED FOR DECOUPLING
    # async def _send_conflict_notification(self, match_id: int): ...
    # async def _send_final_notification(self, match_id: int, final_results: dict): ...


# Global instance
match_completion_service = MatchCompletionService()
