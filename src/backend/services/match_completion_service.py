"""
Match completion monitoring service.

This service monitors matches to detect when they are fully completed
and handles the finalization process including notifying both players.
"""

import asyncio
from typing import Dict, Set, Optional
from src.backend.db.db_reader_writer import DatabaseReader
from src.bot.interface.commands.queue_command import (
    active_match_views,
    get_active_match_views_by_match_id,
    unregister_match_views_by_match_id,
)


class MatchCompletionService:
    """Service for monitoring match completion and handling finalization."""
    
    def __init__(self):
        self.db_reader = DatabaseReader()
        self.monitored_matches: Set[int] = set()
        self.monitoring_tasks: Dict[int, asyncio.Task] = {}
        self.processed_matches: Set[int] = set()  # Track already processed matches
        self.completion_waiters: Dict[int, asyncio.Event] = {}  # Track waiting tasks
        self.processing_locks: Dict[int, asyncio.Lock] = {} # Prevents race conditions
    
    def _get_lock(self, match_id: int) -> asyncio.Lock:
        """Get the lock for a given match ID, creating it if it doesn't exist."""
        if match_id not in self.processing_locks:
            self.processing_locks[match_id] = asyncio.Lock()
        return self.processing_locks[match_id]

    def start_monitoring_match(self, match_id: int):
        """Start monitoring a match for completion."""
        if match_id in self.monitored_matches:
            return  # Already monitoring this match
        
        self.monitored_matches.add(match_id)
        task = asyncio.create_task(self._monitor_match_completion(match_id))
        self.monitoring_tasks[match_id] = task
        print(f"🔍 Started monitoring match {match_id} for completion")
    
    def stop_monitoring_match(self, match_id: int):
        """Stop monitoring a match."""
        if match_id in self.monitored_matches:
            self.monitored_matches.discard(match_id)
        
        if match_id in self.monitoring_tasks:
            task = self.monitoring_tasks.pop(match_id)
            if not task.done():
                task.cancel()
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
                
                if p1_report is not None and p2_report is not None:
                    if match_result == -1:
                        # Conflicting reports - manual resolution needed
                        print(f"⚠️ Conflicting reports for match {match_id}, manual resolution required")
                        await self._handle_match_conflict(match_id)
                    elif match_result is not None:
                        # Match is complete and processed
                        print(f"✅ CHECK: Match {match_id} completed successfully")
                        self.processed_matches.add(match_id)  # Mark as processed
                        await self._handle_match_completion(match_id, match_data)
                        
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
                    
                    if p1_report is not None and p2_report is not None:
                        # Both players have reported
                        if match_id in self.processed_matches:
                            print(f"🔍 MONITOR: Match {match_id} already processed, stopping monitoring")
                            break
                            
                        if match_result == -1:
                            # Conflicting reports - manual resolution needed
                            print(f"⚠️ MONITOR: Conflicting reports for match {match_id}, manual resolution required")
                            await self._handle_match_conflict(match_id)
                        elif match_result is not None:
                            # Match is complete and processed
                            print(f"✅ MONITOR: Match {match_id} completed successfully")
                            self.processed_matches.add(match_id)  # Mark as processed
                            await self._handle_match_completion(match_id, match_data)
                            
                            # Notify any waiting tasks
                            if match_id in self.completion_waiters:
                                self.completion_waiters[match_id].set()
                                del self.completion_waiters[match_id]
                            
                            break
                
                # Wait before checking again
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
            # Re-fetch match data to ensure it's the absolute latest
            final_match_data = await self._get_match_final_results(match_id)
            if not final_match_data:
                print(f"❌ Could not get final results for match {match_id} during handling.")
                return

            # Notify/update all player views with the final data
            await self._notify_players_match_complete(match_id, final_match_data)
            
            # Send the final gold embed notification
            await self._send_final_notification(match_id, final_match_data)

        except Exception as e:
            print(f"❌ Error handling match completion for {match_id}: {e}")
    
    async def _handle_match_conflict(self, match_id: int):
        """Handle a match with conflicting reports."""
        try:
            # Update all views to show the conflict state
            await self._notify_players_of_conflict(match_id)
            
            # Send a new follow-up message to all channels
            await self._send_conflict_notification(match_id)

        except Exception as e:
            print(f"❌ Error handling match conflict for {match_id}: {e}")
        finally:
            # Clean up monitoring for this match
            print(f"🧹 CLEANUP: Unregistering and stopping monitoring for conflict match {match_id}")
            unregister_match_views_by_match_id(match_id)
            self.stop_monitoring_match(match_id)
            self.processing_locks.pop(match_id, None)

    async def _notify_players_match_complete(self, match_id: int, final_results: dict):
        """Notify both players that the match is complete by updating their views."""
        try:
            print(f"🔍 NOTIFY: Looking for match views for match {match_id}")
            channel_view_pairs = get_active_match_views_by_match_id(match_id)
            print(f"🔍 NOTIFY: Found {len(channel_view_pairs)} active channel views for match {match_id}")

            for channel_id, match_view in channel_view_pairs:
                print(f"✅ NOTIFY: Updating match view for match {match_id} in channel {channel_id}")

                # Update the match result in the view with final, correct data
                match_view.match_result.match_result = final_results['match_result']
                match_view.match_result.p1_mmr_change = final_results['p1_mmr_change']
                match_view.match_result.p2_mmr_change = final_results['p2_mmr_change']

                # Update the embed
                embed = match_view.get_embed()
                if hasattr(match_view, 'last_interaction') and match_view.last_interaction:
                    await match_view.last_interaction.edit_original_response(
                        embed=embed,
                        view=match_view
                    )
                    print(f"📢 NOTIFY: Updated match view in channel {channel_id} for match {match_id}")
            
        except Exception as e:
            print(f"❌ Error notifying players about match {match_id} completion: {e}")

    async def _send_final_notification(self, match_id: int, final_results: dict):
        """Create and send the final gold embed notification to all relevant channels."""
        try:
            import discord
            from src.backend.db.db_reader_writer import DatabaseReader
            from src.bot.utils.discord_utils import get_flag_emote, get_race_emote
            from src.backend.services.mmr_service import MMRService
            
            db_reader = DatabaseReader()
            mmr_service = MMRService()
            
            match_info = db_reader.get_match_1v1(match_id)
            if not match_info: return

            p1_info = db_reader.get_player_by_discord_uid(match_info['player_1_discord_uid'])
            p1_name = p1_info.get('player_name', str(match_info['player_1_discord_uid']))
            p1_country = p1_info.get('country')
            p1_flag = get_flag_emote(p1_country) if p1_country else get_flag_emote("XX")
            p1_race_emote = get_race_emote(match_info.get('player_1_race', ''))

            p2_info = db_reader.get_player_by_discord_uid(match_info['player_2_discord_uid'])
            p2_name = p2_info.get('player_name', str(match_info['player_2_discord_uid']))
            p2_country = p2_info.get('country')
            p2_flag = get_flag_emote(p2_country) if p2_country else get_flag_emote("XX")
            p2_race_emote = get_race_emote(match_info.get('player_2_race', ''))

            # Get current MMR values from database
            p1_current_mmr = int(match_info.get('player_1_mmr', 0))
            p2_current_mmr = int(match_info.get('player_2_mmr', 0))
            
            # Calculate new MMR values
            p1_mmr_change = final_results.get('p1_mmr_change', 0)
            p2_mmr_change = final_results.get('p2_mmr_change', 0)
            p1_new_mmr = p1_current_mmr + p1_mmr_change
            p2_new_mmr = p2_current_mmr + p2_mmr_change
            
            # Round MMR changes for display
            p1_mmr_rounded = mmr_service.round_mmr_change(p1_mmr_change)
            p2_mmr_rounded = mmr_service.round_mmr_change(p2_mmr_change)
            
            notification_embed = discord.Embed(
                title=f"🏆 Match #{match_id} Result Finalized",
                description=f"**{p1_flag} {p1_race_emote} {p1_name} ({p1_current_mmr} → {int(p1_new_mmr)})** vs **{p2_flag} {p2_race_emote} {p2_name} ({p2_current_mmr} → {int(p2_new_mmr)})**",
                color=discord.Color.gold()
            )
            
            p1_sign = "+" if p1_mmr_rounded >= 0 else ""
            p2_sign = "+" if p2_mmr_rounded >= 0 else ""
            
            notification_embed.add_field(
                name="**MMR Changes:**",
                value=f"• {p1_name}: `{p1_sign}{p1_mmr_rounded} ({p1_current_mmr} → {int(p1_new_mmr)})`\n• {p2_name}: `{p2_sign}{p2_mmr_rounded} ({p2_current_mmr} → {int(p2_new_mmr)})`",
                inline=False
            )
            
            channel_view_pairs = get_active_match_views_by_match_id(match_id)
            notified_channels = set()
            for channel_id, match_view in channel_view_pairs:
                if channel_id not in notified_channels and hasattr(match_view, 'last_interaction') and match_view.last_interaction:
                    try:
                        await match_view.last_interaction.channel.send(embed=notification_embed)
                        print(f"✅ Sent final notification to channel {channel_id}")
                        notified_channels.add(channel_id)
                    except Exception as e:
                        print(f"❌ Error sending final notification to channel {channel_id}: {e}")

        except Exception as e:
            print(f"❌ Error creating final notification for match {match_id}: {e}")
        finally:
            # This is the single point of cleanup
            print(f"🧹 CLEANUP: Unregistering and stopping monitoring for match {match_id}")
            unregister_match_views_by_match_id(match_id)
            self.stop_monitoring_match(match_id)
            self.processing_locks.pop(match_id, None) # Clean up the lock
    
    async def _get_match_final_results(self, match_id: int) -> Optional[dict]:
        """Get the final results for a completed match."""
        try:
            match_data = self.db_reader.get_match_1v1(match_id)
            if not match_data:
                return None
            
            # Convert match result to human-readable format
            match_result = match_data.get('match_result')
            if match_result == 1:
                result_text = "player1_win"
            elif match_result == 2:
                result_text = "player2_win"
            elif match_result == 0:
                result_text = "draw"
            else:
                result_text = "unknown"
            
            # Get MMR changes
            mmr_change = match_data.get('mmr_change', 0)
            p1_mmr_change = mmr_change
            p2_mmr_change = -mmr_change
            
            return {
                'match_result': result_text,
                'p1_mmr_change': p1_mmr_change,
                'p2_mmr_change': p2_mmr_change
            }
            
        except Exception as e:
            print(f"❌ Error getting final results for match {match_id}: {e}")
            return None
    
    async def _notify_players_of_conflict(self, match_id: int):
        """Update the embeds for all players to show the conflict state."""
        try:
            print(f"🔍 CONFLICT: Notifying match views for match {match_id}")
            channel_view_pairs = get_active_match_views_by_match_id(match_id)
            for channel_id, match_view in channel_view_pairs:
                # Set a flag or value on the match_result to indicate conflict
                match_view.match_result.match_result = 'conflict'
                
                embed = match_view.get_embed()
                if hasattr(match_view, 'last_interaction') and match_view.last_interaction:
                    await match_view.last_interaction.edit_original_response(embed=embed, view=match_view)
                    print(f"📢 CONFLICT: Updated match view in channel {channel_id} for match {match_id}")
        except Exception as e:
            print(f"❌ Error notifying players about match conflict for {match_id}: {e}")

    async def _send_conflict_notification(self, match_id: int):
        """Sends a new follow-up message indicating a match conflict."""
        try:
            import discord
            conflict_embed = discord.Embed(
                title="⚠️ Match Result Conflict",
                description="The reported results don't match. Please contact an administrator to resolve this dispute.",
                color=discord.Color.red()
            )
            
            channel_view_pairs = get_active_match_views_by_match_id(match_id)
            notified_channels = set()
            for channel_id, match_view in channel_view_pairs:
                if channel_id not in notified_channels and hasattr(match_view, 'last_interaction') and match_view.last_interaction:
                    try:
                        await match_view.last_interaction.channel.send(embed=conflict_embed)
                        print(f"✅ Sent conflict notification to channel {channel_id}")
                        notified_channels.add(channel_id)
                    except Exception as e:
                        print(f"❌ Error sending conflict notification to channel {channel_id}: {e}")
        except Exception as e:
            print(f"❌ Error creating conflict notification for match {match_id}: {e}")


# Global instance
match_completion_service = MatchCompletionService()
