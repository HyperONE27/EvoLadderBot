"""
Match completion monitoring service.

This service monitors matches to detect when they are fully completed
and handles the finalization process including notifying both players.
"""

import asyncio
import json
import logging
from asyncio import Lock
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Set

from src.backend.core.types import (
    VerificationResult,
    RaceVerificationDetail,
    MapVerificationDetail,
    TimestampVerificationDetail,
    ObserverVerificationDetail
)
from src.backend.core.config import REPLAY_TIMESTAMP_WINDOW_MINUTES
from src.backend.services.leaderboard_service import LeaderboardService


class MatchCompletionService:
    """Service for monitoring match completion and handling finalization."""
    
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MatchCompletionService, cls).__new__(cls)
            cls._instance.monitored_matches = set()
            cls._instance.monitoring_tasks = {}
            cls._instance.processed_matches = set()
            cls._instance.completion_waiters = {}
            cls._instance.processing_locks: Dict[int, Lock] = {}
            # New dictionary to store callbacks
            cls._instance.notification_callbacks: Dict[int, List[Callable]] = {}
            # Track match confirmations: match_id -> set of player_discord_uids
            cls._instance.match_confirmations: Dict[int, Set[int]] = {}
            # Initialize logger
            cls._instance.logger = logging.getLogger(__name__)
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
        
        # Initialize confirmation tracking for this match
        self.match_confirmations[match_id] = set()

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
        self.match_confirmations.pop(match_id, None)

        print(f"🛑 Stopped monitoring match {match_id}")
    
    async def confirm_match(self, match_id: int, player_discord_uid: int) -> bool:
        """
        Record that a player has confirmed the match.
        
        If both players confirm, the auto-abort timer is cancelled.
        
        Args:
            match_id: The ID of the match being confirmed
            player_discord_uid: The Discord UID of the player confirming
            
        Returns:
            True if the confirmation was recorded successfully
        """
        lock = self._get_lock(match_id)
        async with lock:
            # Add player to confirmations set
            if match_id not in self.match_confirmations:
                self.match_confirmations[match_id] = set()
            
            self.match_confirmations[match_id].add(player_discord_uid)
            self.logger.info(f"Player {player_discord_uid} confirmed match {match_id}")
            
            # Check if both players have confirmed
            if len(self.match_confirmations[match_id]) == 2:
                self.logger.info(f"Both players confirmed match {match_id}, cancelling auto-abort timer")
                
                # Cancel the auto-abort timer
                task = self.monitoring_tasks.pop(match_id, None)
                if task:
                    task.cancel()
                    self.logger.info(f"Auto-abort timer cancelled for match {match_id}")
                
                # Clean up confirmations
                self.match_confirmations.pop(match_id, None)
            
            return True
    
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
        """
        Public, lock-acquiring method to check match completion.
        This is the main entry point for external services.
        """
        lock = self._get_lock(match_id)
        async with lock:
            await self._check_match_completion_locked(match_id)

    async def _check_match_completion_locked(self, match_id: int):
        """
        Internal completion check that assumes the lock for the match_id is already held.
        """
        import time
        start_time = time.perf_counter()
        
        try:
            print(f"🔍 CHECK: Manual completion check for match {match_id}")
            # Get match data from DataAccessService (in-memory, instant)
            from src.backend.services.data_access_service import DataAccessService
            data_service = DataAccessService()
            match_data = data_service.get_match(match_id)
            if not match_data:
                raise ValueError(f"[MatchCompletion] Match {match_id} not found in DataAccessService memory")
            
            # Check current status - if already processed, skip
            current_status = match_data.get('status', 'IN_PROGRESS')
            p1_report = match_data.get('player_1_report')
            p2_report = match_data.get('player_2_report')

            is_unconfirmed_abort = current_status == 'ABORTED' and (p1_report == -4 or p2_report == -4)

            if current_status in ('COMPLETE', 'CONFLICT', 'PROCESSING_COMPLETION') or (current_status == 'ABORTED' and not is_unconfirmed_abort):
                print(f"🔍 CHECK: Match {match_id} already in terminal/processing state: {current_status}, skipping notification")
                return True
            
            # Check if both players have reported
            match_result = match_data.get('match_result')
            
            print(f"🔍 CHECK: Match {match_id} status={current_status}, reports: p1={p1_report}, p2={p2_report}, result={match_result}")
            
            # Abort if any report indicates an abort, or if the match_result is definitively -1
            if p1_report in [-3, -4] or p2_report in [-3, -4] or match_result == -1:
                print(f"🚫 Match {match_id} was aborted")
                # Atomically transition to ABORTED state
                data_service.update_match_status(match_id, 'ABORTED')
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
                    # Atomically transition to CONFLICT state
                    data_service.update_match_status(match_id, 'CONFLICT')
                    await self._handle_match_conflict(match_id)
                elif match_result is not None:
                    # Match is complete - atomically transition to PROCESSING_COMPLETION
                    # to prevent concurrent abort/complete operations
                    print(f"✅ CHECK: Match {match_id} ready for completion, transitioning to PROCESSING_COMPLETION")
                    data_service.update_match_status(match_id, 'PROCESSING_COMPLETION')
                    self.processed_matches.add(match_id)  # Mark as processed
                    
                    # Perform completion actions while lock is held
                    await self._handle_match_completion(match_id, match_data)
                    
                    # Atomically transition to COMPLETE state
                    data_service.update_match_status(match_id, 'COMPLETE')
                    print(f"✅ CHECK: Match {match_id} completed successfully")
                    
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
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            if duration_ms > 100:
                print(f"⚠️ [MatchCompletion PERF] check_match_completion for match {match_id} took {duration_ms:.2f}ms")
            elif duration_ms > 50:
                print(f"🟡 [MatchCompletion PERF] check_match_completion for match {match_id} took {duration_ms:.2f}ms")

    async def _monitor_match_completion(self, match_id: int):
        """Monitor a specific match for completion."""
        from src.backend.services.matchmaking_service import matchmaker
        
        try:
            # First, wait for the abort timer to expire
            await asyncio.sleep(matchmaker.ABORT_TIMER_SECONDS)
            
            # After abort timer expires, check if both players confirmed
            lock = self._get_lock(match_id)
            async with lock:
                # Check if match is still being monitored
                if match_id not in self.monitored_matches:
                    print(f"🛑 [DEBUG] Match {match_id} is no longer being monitored, skipping confirmation check")
                    return

                print(f"⏰ [DEBUG] Confirmation timer expired for match {match_id}")
                
                # First, notify frontends that the confirmation window is closed
                # This allows them to disable buttons before the final abort notification arrives
                print(f"📢 [DEBUG] About to notify players of confirmation timeout for match {match_id}")
                await self._notify_players_confirmation_timeout(match_id)
                print(f"✅ [DEBUG] Confirmation timeout notification sent for match {match_id}")
                
                # Get match data from DataAccessService (in-memory, instant)
                from src.backend.services.data_access_service import DataAccessService
                data_service = DataAccessService()
                match_data = data_service.get_match(match_id)
                if not match_data:
                    raise ValueError(f"[MatchCompletion] Match {match_id} not found in DataAccessService memory")
                
                # Check if match has already been resolved
                match_result = match_data.get('match_result')
                if match_result is not None:
                    self.logger.info(f"Match {match_id} already resolved, skipping confirmation check")
                    return
                
                # Check confirmations
                confirmed_players = self.match_confirmations.get(match_id, set())
                if len(confirmed_players) < 2:
                    # Not all players confirmed, handle unconfirmed abort
                    await self._handle_unconfirmed_abort(match_id, match_data)
                    return
            
            # If both players confirmed, continue normal monitoring loop
            while match_id in self.monitored_matches:
                lock = self._get_lock(match_id)
                async with lock:
                    # Get match data from DataAccessService (in-memory, instant)
                    from src.backend.services.data_access_service import DataAccessService
                    data_service = DataAccessService()
                    match_data = data_service.get_match(match_id)
                    if not match_data:
                        raise ValueError(f"[MatchCompletion] Match {match_id} not found in DataAccessService memory")
                    
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
            # self.stop_monitoring_match(match_id) # Cleanup is now handled by terminal state handlers
            self.processing_locks.pop(match_id, None) # Clean up the lock
    
    async def _handle_match_completion(self, match_id: int, match_data: dict):
        """Handle a completed match."""
        import time
        start_time = time.perf_counter()
        
        try:
            from src.backend.services.matchmaking_service import matchmaker
            
            checkpoint1 = time.perf_counter()
            # Calculate and write MMR changes
            await matchmaker._calculate_and_write_mmr(match_id, match_data)
            checkpoint2 = time.perf_counter()
            mmr_time = (checkpoint2-checkpoint1)*1000
            # Cache invalidation is now handled automatically by the database decorator

            checkpoint3 = time.perf_counter()
            # Re-fetch match data to ensure it's the absolute latest
            final_match_data = await self._get_match_final_results(match_id)
            checkpoint4 = time.perf_counter()
            results_time = (checkpoint4-checkpoint3)*1000
            
            if not final_match_data:
                print(f"❌ Could not get final results for match {match_id} during handling.")
                return

            # Mark as processed and notify any waiters
            if match_id not in self.processed_matches:
                self.processed_matches.add(match_id)
                if match_id in self.completion_waiters:
                    self.completion_waiters[match_id].set()
                    del self.completion_waiters[match_id]

            # Release queue lock for both players so they can re-queue
            p1_uid = final_match_data.get('player_1_discord_uid')
            p2_uid = final_match_data.get('player_2_discord_uid')
            if p1_uid and p2_uid:
                await matchmaker.release_queue_lock_for_players([p1_uid, p2_uid])
                print(f"🔓 Released queue locks for players {p1_uid} and {p2_uid} after completion")

            checkpoint5 = time.perf_counter()
            # Notify/update all player views with the final data
            await self._notify_players_match_complete(match_id, final_match_data)
            checkpoint6 = time.perf_counter()
            notify_time = (checkpoint6-checkpoint5)*1000
            
            # Compact performance logging
            print(f"[MC] MMR:{mmr_time:.1f}ms Results:{results_time:.1f}ms Notify:{notify_time:.1f}ms")
            
        except Exception as e:
            print(f"❌ Error handling match completion for {match_id}: {e}")
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            print(f"🏁 [MatchCompletion PERF] Total _handle_match_completion for match {match_id}: {duration_ms:.2f}ms")
            # Ensure cleanup is always performed
            self.stop_monitoring_match(match_id)
    
    async def _handle_match_abort(self, match_id: int, match_data: dict):
        """Handle an aborted match."""
        try:
            print(f"🛑 [DEBUG] _handle_match_abort START for match {match_id}")
            # Import matchmaker for queue lock release
            from src.backend.services.matchmaking_service import matchmaker
            
            # Get the latest match data to ensure we have the report codes
            from src.backend.services.data_access_service import DataAccessService
            data_service = DataAccessService()
            latest_match_data = data_service.get_match(match_id)
            if not latest_match_data:
                latest_match_data = match_data
            
            # Re-fetch to ensure we have the latest state for the final results
            final_match_data = await self._get_match_final_results(match_id)
            if not final_match_data:
                # If we can't get final results, build minimal data from latest match data
                final_match_data = {
                    'match_id': match_id,
                    'player_1_discord_uid': latest_match_data.get('player_1_discord_uid'),
                    'player_2_discord_uid': latest_match_data.get('player_2_discord_uid'),
                    'p1_report': latest_match_data.get('player_1_report'),
                    'p2_report': latest_match_data.get('player_2_report'),
                }

            # Mark as processed (abort) and notify any waiters
            if match_id not in self.processed_matches:
                self.processed_matches.add(match_id)
                if match_id in self.completion_waiters:
                    self.completion_waiters[match_id].set()
                    del self.completion_waiters[match_id]

            # Release queue lock for both players so they can re-queue
            p1_uid = latest_match_data.get('player_1_discord_uid')
            p2_uid = latest_match_data.get('player_2_discord_uid')
            if p1_uid and p2_uid:
                await matchmaker.release_queue_lock_for_players([p1_uid, p2_uid])
                print(f"🔓 Released queue locks for players {p1_uid} and {p2_uid} after abort")

            # Notify all callbacks with abort status and include player report codes
            callbacks = self.notification_callbacks.pop(match_id, [])
            print(f"🛑 [DEBUG] _handle_match_abort: Found {len(callbacks)} callbacks to invoke for match {match_id}")
            print(f"  -> Notifying {len(callbacks)} callbacks for match {match_id} abort.")
            for idx, callback in enumerate(callbacks):
                try:
                    print(f"🛑 [DEBUG] Invoking abort callback {idx} for match {match_id}")
                    await callback(
                        status="abort", 
                        data={
                            "match_id": match_id, 
                            "match_data": final_match_data,
                            "p1_report": latest_match_data.get('player_1_report'),
                            "p2_report": latest_match_data.get('player_2_report'),
                        }
                    )
                    print(f"✅ [DEBUG] Abort callback {idx} completed for match {match_id}")
                except Exception as e:
                    print(f"❌ [DEBUG] Error executing abort callback {idx} for match {match_id}: {e}")
                    print(f"❌ Error executing abort callback for match {match_id}: {e}")

        except Exception as e:
            print(f"❌ [DEBUG] ERROR in _handle_match_abort for match {match_id}: {e}")
            print(f"❌ Error handling match abort for {match_id}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print(f"🛑 [DEBUG] _handle_match_abort FINALLY block for match {match_id}")
            # Clean up monitoring for this match
            self.stop_monitoring_match(match_id)
    
    async def _handle_unconfirmed_abort(self, match_id: int, match_data: dict):
        """
        Handle a match that was not confirmed by all players in time.
        
        This sets player_1_report and/or player_2_report to -4 for players who
        didn't confirm, and match_result to -1 (aborted), WITHOUT decrementing
        abort counters.
        """
        try:
            print(f"🚫 [DEBUG] _handle_unconfirmed_abort START for match {match_id}")
            self.logger.info(f"Handling unconfirmed abort for match {match_id}")
            
            # Get player UIDs
            p1_uid = match_data.get('player_1_discord_uid')
            p2_uid = match_data.get('player_2_discord_uid')
            
            print(f"🚫 [DEBUG] Players: p1={p1_uid}, p2={p2_uid}")
            
            # Determine which players confirmed
            confirmed_players = self.match_confirmations.get(match_id, set())
            
            print(f"🚫 [DEBUG] Confirmed players: {confirmed_players}")
            
            # Set report values: -4 for unconfirmed, None for confirmed
            p1_report = None if p1_uid in confirmed_players else -4
            p2_report = None if p2_uid in confirmed_players else -4
            
            print(f"🚫 [DEBUG] Report codes: p1={p1_report}, p2={p2_report}")
            
            self.logger.info(
                f"Match {match_id} unconfirmed abort: "
                f"p1_report={p1_report}, p2_report={p2_report}"
            )
            
            # Call the new data service method
            from src.backend.services.data_access_service import DataAccessService
            data_service = DataAccessService()
            print(f"🚫 [DEBUG] Calling record_system_abort for match {match_id}")
            await data_service.record_system_abort(match_id, p1_report, p2_report)
            print(f"🚫 [DEBUG] record_system_abort completed for match {match_id}")
            
            # Directly trigger the abort handling to ensure callbacks are invoked
            # This call is now safe because we are already holding the lock
            print(f"🚫 [DEBUG] Calling _check_match_completion_locked for match {match_id}")
            await self._check_match_completion_locked(match_id)
            print(f"🚫 [DEBUG] _check_match_completion_locked completed for match {match_id}")
            
            self.logger.info(f"Successfully recorded unconfirmed abort for match {match_id}")
            print(f"🚫 [DEBUG] _handle_unconfirmed_abort COMPLETE for match {match_id}")
            
        except Exception as e:
            print(f"❌ [DEBUG] ERROR in _handle_unconfirmed_abort for match {match_id}: {e}")
            self.logger.error(f"Error handling unconfirmed abort for match {match_id}: {e}", exc_info=True)

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

    async def _notify_players_confirmation_timeout(self, match_id: int):
        """Notify all registered frontends that the confirmation time has expired."""
        callbacks = self.notification_callbacks.get(match_id, [])
        print(f"🔔 [DEBUG] _notify_players_confirmation_timeout: match {match_id} has {len(callbacks)} callbacks registered")
        self.logger.info(f"  -> Notifying {len(callbacks)} callbacks for match {match_id} confirmation timeout.")
        for idx, callback in enumerate(callbacks):
            try:
                print(f"🔔 [DEBUG] Invoking callback {idx} for confirmation timeout on match {match_id}")
                # This notification does not include a data payload
                await callback(status="confirmation_timeout", data={})
                print(f"✅ [DEBUG] Callback {idx} completed for confirmation timeout on match {match_id}")
            except Exception as e:
                print(f"❌ [DEBUG] Error executing confirmation_timeout callback {idx} for match {match_id}: {e}")
                self.logger.error(f"❌ Error executing confirmation_timeout callback for match {match_id}: {e}")

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
            # Get match data from DataAccessService (in-memory, instant)
            from src.backend.services.data_access_service import DataAccessService
            data_service = DataAccessService()
            match_data = data_service.get_match(match_id)
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
            # Get match data from DataAccessService (in-memory, instant)
            from src.backend.services.data_access_service import DataAccessService
            data_service = DataAccessService()
            match_data = data_service.get_match(match_id)
            if not match_data:
                raise ValueError(f"[MatchCompletion] Match {match_id} not found in DataAccessService memory")

            # This part should be re-evaluated, as it's frontend-specific
            # For now, it's kept for data structure compatibility
            p1_info = data_service.get_player_info(match_data['player_1_discord_uid'])
            p2_info = data_service.get_player_info(match_data['player_2_discord_uid'])

            p1_name = p1_info.get('player_name', str(match_data['player_1_discord_uid']))
            p2_name = p2_info.get('player_name', str(match_data['player_2_discord_uid']))

            result_text_map = {
                1: f"{p1_name} victory",
                2: f"{p2_name} victory",
                0: "Draw",
                -1: "Aborted",
                -2: "Conflict"
            }
            result_text = result_text_map[match_data['match_result']]

            # Calculate MMR changes directly from the match result
            # This ensures we get the correct values even if database writes are still pending
            match_result = match_data['match_result']
            p1_mmr_change = 0
            p2_mmr_change = 0
            
            if match_result in [0, 1, 2]:  # Valid match results (draw, p1 win, p2 win)
                # Calculate MMR changes using the MMR service
                from src.backend.services.mmr_service import MMRService
                mmr_service = MMRService()
                
                p1_current_mmr = match_data['player_1_mmr']
                p2_current_mmr = match_data['player_2_mmr']
                
                if p1_current_mmr is not None and p2_current_mmr is not None:
                    p1_mmr_change = mmr_service.calculate_mmr_change(
                        p1_current_mmr, 
                        p2_current_mmr, 
                        match_result
                    )
                    p2_mmr_change = -p1_mmr_change  # Player 2's change is opposite of player 1's
                    
                    print(f"[MatchCompletion] Calculated MMR changes for match {match_id}: P1={p1_mmr_change:+.1f}, P2={p2_mmr_change:+.1f}")

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
                "p1_mmr_change": p1_mmr_change,
                "p2_mmr_change": p2_mmr_change,
                "p1_report": match_data.get('player_1_report'),
                "p2_report": match_data.get('player_2_report'),
                "result_text": result_text,
                "match_result_raw": match_data['match_result']
            }
            
        except Exception as e:
            print(f"❌ Error getting final results for match {match_id}: {e}")
            return None
    
    # ========== Replay Verification Methods ==========
    
    def start_replay_verification(
        self, 
        match_id: int, 
        replay_data: Dict[str, any], 
        callback: Callable[[VerificationResult], None]
    ) -> None:
        """
        Public entry point to start the replay verification process in the background.
        
        Args:
            match_id: The match ID to verify against
            replay_data: The parsed replay data dictionary
            callback: Async callback function to execute with the verification results
        """
        asyncio.create_task(self._verify_replay_task(match_id, replay_data, callback))
    
    async def verify_replay_data(
        self,
        match_id: int,
        replay_data: Dict[str, any]
    ) -> VerificationResult:
        """
        Performs all replay verification checks and returns the complete result.
        This is a blocking, awaitable method.
        
        Args:
            match_id: The match ID to verify against
            replay_data: The parsed replay data dictionary
            
        Returns:
            VerificationResult with detailed information about all checks
            
        Raises:
            ValueError: If match_id is not found in the database
        """
        from src.backend.services.data_access_service import DataAccessService
        data_service = DataAccessService()
        
        match_details = data_service.get_match(match_id)
        
        if not match_details:
            raise ValueError(f"Match {match_id} not found in database")
        
        self.logger.info(f"Starting verification for match {match_id}")
        
        races_detail = self._verify_races(match_details, replay_data)
        map_detail = self._verify_map(match_details, replay_data)
        timestamp_detail = self._verify_timestamp(match_details, replay_data)
        observers_detail = self._verify_observers(replay_data)
        
        result = VerificationResult(
            races=races_detail,
            map=map_detail,
            timestamp=timestamp_detail,
            observers=observers_detail
        )
        
        all_passed = all([
            races_detail['success'],
            map_detail['success'],
            timestamp_detail['success'],
            observers_detail['success']
        ])
        status_icon = "✅" if all_passed else "⚠️"
        self.logger.info(
            f"{status_icon} Verification for match {match_id}: "
            f"races={races_detail['success']}, map={map_detail['success']}, "
            f"timestamp={timestamp_detail['success']}, observers={observers_detail['success']}"
        )
        
        return result
    
    async def _verify_replay_task(
        self, 
        match_id: int, 
        replay_data: Dict[str, any], 
        callback: Callable[[VerificationResult], None]
    ) -> None:
        """
        DEPRECATED: Background worker with callback pattern.
        Use verify_replay_data() instead for new code.
        
        Args:
            match_id: The match ID to verify against
            replay_data: The parsed replay data dictionary
            callback: Async callback function to execute with the verification results
        """
        try:
            result = await self.verify_replay_data(match_id, replay_data)
            await callback(result)
        except ValueError as e:
            self.logger.error(str(e))
        except Exception as e:
            self.logger.exception(f"Error during replay verification for match_id {match_id}: {e}")
    
    def _verify_races(
        self, 
        match_details: Dict[str, any], 
        replay_details: Dict[str, any]
    ) -> RaceVerificationDetail:
        """
        Checks if races in the replay match the assigned races.
        
        Args:
            match_details: Match data from _matches_1v1_df
            replay_details: Replay data from _replays_df
            
        Returns:
            RaceVerificationDetail with success status and race information
        """
        match_races = {match_details['player_1_race'], match_details['player_2_race']}
        replay_races = {replay_details['player_1_race'], replay_details['player_2_race']}
        
        return RaceVerificationDetail(
            success=(match_races == replay_races),
            expected_races=match_races,
            played_races=replay_races
        )
    
    def _verify_map(
        self, 
        match_details: Dict[str, any], 
        replay_details: Dict[str, any]
    ) -> MapVerificationDetail:
        """
        Checks if the map played matches the assigned map.
        
        Args:
            match_details: Match data from _matches_1v1_df
            replay_details: Replay data from _replays_df
            
        Returns:
            MapVerificationDetail with success status and map information
        """
        match_map = match_details.get('map_played', '')
        replay_map = replay_details.get('map_name', '')
        
        return MapVerificationDetail(
            success=(match_map == replay_map),
            expected_map=match_map,
            played_map=replay_map
        )

    def _verify_timestamp(
        self, 
        match_details: Dict[str, any], 
        replay_details: Dict[str, any]
    ) -> TimestampVerificationDetail:
        """
        Checks if the match was played within 20 minutes of assignment.
        
        The replay_date represents when the player left the game.
        We subtract the game duration to get the approximate start time.
        
        Args:
            match_details: Match data from _matches_1v1_df
            replay_details: Replay data from _replays_df
            
        Returns:
            TimestampVerificationDetail with success status and time difference
        """
        try:
            played_at_value = match_details.get('played_at')
            replay_date_str = replay_details.get('replay_date')
            duration_seconds = int(replay_details.get('duration') or 0)
            
            if not played_at_value or not replay_date_str:
                error_msg = f"Missing timestamp data: played_at={played_at_value}, replay_date={replay_date_str}"
                self.logger.warning(error_msg)
                return TimestampVerificationDetail(
                    success=False,
                    time_difference_minutes=None,
                    error=error_msg
                )

            # Handle played_at being either a string or a datetime object
            if isinstance(played_at_value, datetime):
                played_at = played_at_value
            else:
                played_at = datetime.fromisoformat(str(played_at_value).replace('+00', '+00:00'))

            # If played_at is offset-naive, assume it's UTC and make it offset-aware.
            if played_at.tzinfo is None:
                played_at = played_at.replace(tzinfo=timezone.utc)

            replay_date = datetime.fromisoformat(replay_date_str.replace('+00', '+00:00'))
            if replay_date.tzinfo is None:
                replay_date = replay_date.replace(tzinfo=timezone.utc)
            
            replay_start_time = replay_date - timedelta(seconds=duration_seconds)
            time_difference = replay_start_time - played_at
            time_diff_minutes = time_difference.total_seconds() / 60.0
            time_diff_abs = abs(time_diff_minutes)
            
            is_valid = time_diff_abs <= REPLAY_TIMESTAMP_WINDOW_MINUTES
            
            if not is_valid:
                self.logger.warning(f"Timestamp mismatch: difference={time_diff_minutes:.1f} minutes")
            
            return TimestampVerificationDetail(
                success=is_valid,
                time_difference_minutes=time_diff_minutes,
                error=None
            )
            
        except (ValueError, TypeError, AttributeError) as e:
            error_msg = f"Error parsing timestamps: {e}"
            self.logger.error(error_msg, exc_info=True)
            return TimestampVerificationDetail(
                success=False,
                time_difference_minutes=None,
                error=error_msg
            )
    
    def _verify_observers(self, replay_details: Dict[str, any]) -> ObserverVerificationDetail:
        """
        Checks for unauthorized observers.
        
        Args:
            replay_details: Replay data from _replays_df
            
        Returns:
            ObserverVerificationDetail with success status and observer list
        """
        observers_field = replay_details.get('observers')
        observers_list = []
        
        if observers_field is None:
            pass
        elif isinstance(observers_field, str):
            try:
                observers_list = json.loads(observers_field)
            except json.JSONDecodeError:
                if observers_field and observers_field != '[]':
                    observers_list = [observers_field]
        elif isinstance(observers_field, list):
            observers_list = observers_field
        
        return ObserverVerificationDetail(
            success=(len(observers_list) == 0),
            observers_found=observers_list
        )
    
    # REMOVED FOR DECOUPLING
    # async def _send_conflict_notification(self, match_id: int): ...
    # async def _send_final_notification(self, match_id: int, final_results: dict): ...


# Global instance
match_completion_service = MatchCompletionService()
