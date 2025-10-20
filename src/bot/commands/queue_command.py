import asyncio
import json
import discord
from discord import app_commands
from src.bot.components.error_embed import ErrorEmbedException, create_error_view_from_exception
from src.bot.components.confirm_restart_cancel_buttons import ConfirmRestartCancelButtons
from src.bot.components.cancel_embed import create_cancel_embed
from functools import partial
from typing import Callable, Dict, Optional
from src.backend.services.matchmaking_service import matchmaker, Player, QueuePreferences, MatchResult
from src.backend.services.user_info_service import get_user_info
from src.backend.db.db_reader_writer import get_timestamp
from src.bot.utils.discord_utils import send_ephemeral_response, get_current_unix_timestamp, format_discord_timestamp, get_flag_emote, get_race_emote
from src.backend.services.command_guard_service import CommandGuardError
from src.bot.components.command_guard_embeds import create_command_guard_error_embed
from src.backend.services.replay_service import ReplayRaw, parse_replay_data_blocking
from src.backend.services.match_completion_service import match_completion_service
from src.backend.services.app_context import (
    races_service as race_service,
    maps_service,
    regions_service,
    user_info_service,
    db_writer,
    db_reader,
    command_guard_service as guard_service,
    replay_service,
    mmr_service
)
import logging
import time
from contextlib import suppress
from src.bot.components.replay_details_embed import ReplayDetailsEmbed
from src.bot.config import GLOBAL_TIMEOUT
from src.backend.services.performance_service import FlowTracker


class QueueSearchingViewManager:
    """Manage active queue searching views safely across async tasks."""

    def __init__(self) -> None:
        self._views: Dict[int, "QueueSearchingView"] = {}
        self._lock = asyncio.Lock()

    async def has_view(self, user_id: int) -> bool:
        async with self._lock:
            return user_id in self._views

    async def get_view(self, user_id: int) -> Optional["QueueSearchingView"]:
        async with self._lock:
            return self._views.get(user_id)

    async def register(self, user_id: int, view: "QueueSearchingView") -> None:
        previous: Optional["QueueSearchingView"] = None
        async with self._lock:
            previous = self._views.get(user_id)
            self._views[user_id] = view
        if previous and previous is not view:
            previous.deactivate()

    async def unregister(
        self,
        user_id: int,
        *,
        deactivate: bool = True,
        view: Optional["QueueSearchingView"] = None,
    ) -> Optional["QueueSearchingView"]:
        async with self._lock:
            current = self._views.get(user_id)
            if current is None or (view is not None and current is not view):
                return None
            self._views.pop(user_id, None)
        if deactivate and current:
            current.deactivate()
        return current


class MatchFoundViewManager:
    """Manage active match found views safely across async tasks."""

    def __init__(self) -> None:
        # {match_id: [(channel_id, view)]}
        self._views: Dict[int, list[tuple[int, "MatchFoundView"]]] = {}
        self._lock = asyncio.Lock()

    async def register(self, match_id: int, channel_id: int, view: "MatchFoundView") -> None:
        async with self._lock:
            if match_id not in self._views:
                self._views[match_id] = []
            
            # Remove any stale view for the same channel
            self._views[match_id] = [
                (cid, v) for cid, v in self._views[match_id] if cid != channel_id
            ]
            self._views[match_id].append((channel_id, view))
            channel_to_match_view_map[channel_id] = view

    async def unregister(self, match_id: int, channel_id: int) -> None:
        async with self._lock:
            if match_id in self._views:
                self._views[match_id] = [
                    (cid, v) for cid, v in self._views[match_id] if cid != channel_id
                ]
                if not self._views[match_id]:
                    del self._views[match_id]
            channel_to_match_view_map.pop(channel_id, None)

    async def get_views_by_match_id(self, match_id: int) -> list[tuple[int, "MatchFoundView"]]:
        async with self._lock:
            return self._views.get(match_id, [])


queue_searching_view_manager = QueueSearchingViewManager()
match_found_view_manager = MatchFoundViewManager()
channel_to_match_view_map: Dict[int, "MatchFoundView"] = {}

logger = logging.getLogger(__name__)


# Register Command
def register_queue_command(tree: app_commands.CommandTree):
    """Register the queue command"""
    @tree.command(
        name="queue",
        description="Join the matchmaking queue"
    )
    async def queue(interaction: discord.Interaction):
        await queue_command(interaction)
    
    return queue


# UI Elements
async def queue_command(interaction: discord.Interaction):
    """Handle the /queue slash command"""
    flow = FlowTracker("queue_command", user_id=interaction.user.id)
    
    try:
        # Guard checks
        flow.checkpoint("guard_checks_start")
        player = guard_service.ensure_player_record(interaction.user.id, interaction.user.name)
        guard_service.require_queue_access(player)
        flow.checkpoint("guard_checks_complete")
    except CommandGuardError as exc:
        flow.complete("guard_check_failed")
        error_embed = create_command_guard_error_embed(exc)
        await send_ephemeral_response(interaction, embed=error_embed)
        return

    # Check for existing queue/match
    flow.checkpoint("check_existing_queue_start")
    is_in_match_view = any(
        v.match_result.player_1_discord_id == interaction.user.id or v.match_result.player_2_discord_id == interaction.user.id
        for v in channel_to_match_view_map.values()
    )

    # Prevent multiple queue attempts or queuing while a match is active
    if await queue_searching_view_manager.has_view(interaction.user.id) or is_in_match_view:
        flow.complete("already_queued")
        error = ErrorEmbedException(
            title="Queueing Not Allowed",
            description="You are already in a queue or an active match."
        )
        error_view = create_error_view_from_exception(error)
        await send_ephemeral_response(interaction, embed=error_view.embed, view=error_view)
        return
    
    flow.checkpoint("check_existing_queue_complete")
    
    # Get user's saved preferences from database
    flow.checkpoint("load_preferences_start")
    user_preferences = db_reader.get_preferences_1v1(interaction.user.id)
    
    if user_preferences:
        # Parse saved preferences from database
        try:
            default_races = json.loads(user_preferences.get('last_chosen_races', '[]'))
            default_maps = json.loads(user_preferences.get('last_chosen_vetoes', '[]'))
        except (json.JSONDecodeError, TypeError):
            # Fallback to empty defaults if parsing fails
            default_races = []
            default_maps = []
    else:
        # No saved preferences, use empty defaults
        default_races = []
        default_maps = []
    
    flow.checkpoint("load_preferences_complete")
    
    # Create view
    flow.checkpoint("create_view_start")
    view = await QueueView.create(
        discord_user_id=interaction.user.id,
        default_races=default_races,
        default_maps=default_maps,
    )
    flow.checkpoint("create_view_complete")
    
    # Build embed
    flow.checkpoint("build_embed_start")
    embed = view.get_embed()
    flow.checkpoint("build_embed_complete")
    
    # Send response
    flow.checkpoint("send_response_start")
    await send_ephemeral_response(interaction, embed=embed, view=view)
    flow.checkpoint("send_response_complete")
    
    flow.complete("success")


class MapVetoSelect(discord.ui.Select):
    """Multiselect dropdown for map vetoes"""
    
    def __init__(self, default_values=None):
        # Get map options from ladder service
        maps = maps_service.get_maps()
        
        options = []
        for map_data in maps:
            options.append(
                discord.SelectOption(
                    label=map_data["short_name"],
                    value=map_data["short_name"],
                    default=map_data["short_name"] in (default_values or [])
                )
            )
        
        super().__init__(
            placeholder="Select maps to veto (max 4)...",
            min_values=0,
            max_values=4,
            options=options,
            row=3
        )
    
    async def callback(self, interaction: discord.Interaction):
        self.view.vetoed_maps = self.values
        await self.view.persist_preferences()
        await self.view.update_embed(interaction)


class JoinQueueButton(discord.ui.Button):
    """Join queue button"""
    
    def __init__(self):
        super().__init__(
            label="Join Queue",
            emoji="🚀",
            style=discord.ButtonStyle.secondary,
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Validate that at least one race is selected
        if not self.view.get_selected_race_codes():
            # Create error exception with restart button only
            error = ErrorEmbedException(
                title="No Race Selected",
                description="You must select at least one race before joining the queue.",
                reset_target=self.view  # Reset to the same queue view
            )
            
            # Create error view with only restart button enabled
            error_view = create_error_view_from_exception(error)
            # Override the error view to only include restart button
            error_view.clear_items()
            restart_buttons = ConfirmRestartCancelButtons.create_buttons(
                reset_target=self.view,
                include_confirm=False,
                include_restart=True,
                include_cancel=False
            )
            for button in restart_buttons:
                error_view.add_item(button)
            
            await interaction.response.edit_message(
                embed=error_view.embed,
                view=error_view
            )
            return
        
        # Get user info
        user_info = get_user_info(interaction)
        user_id = user_info["id"]

        # Prevent multiple queue attempts or queuing while a match is active
        if await queue_searching_view_manager.has_view(user_id) or interaction.user.id in match_results:
            error = ErrorEmbedException(
                title="Queueing Not Allowed",
                description="You cannot queue more than once, or while a match is active."
            )
            error_view = create_error_view_from_exception(error)
            await interaction.response.edit_message(embed=error_view.embed, view=error_view)
            return
        
        # Create queue preferences
        preferences = QueuePreferences(
            selected_races=self.view.get_selected_race_codes(),
            vetoed_maps=self.view.vetoed_maps,
            discord_user_id=user_id,
            user_id="Player" + str(user_id)  # TODO: Get actual user ID from database
        )
        
        # Create player and add to matchmaking queue
        player = Player(
            discord_user_id=user_id,
            user_id=preferences.user_id,
            preferences=preferences
        )
        
        # Add player to matchmaker
        print(f"🎮 Adding player to matchmaker: {player.user_id}")
        await matchmaker.add_player(player)
        
        # Show searching state
        searching_view = QueueSearchingView(
            original_view=self.view,
            selected_races=self.view.get_selected_race_codes(),
            vetoed_maps=self.view.vetoed_maps,
            player=player
        )
        await queue_searching_view_manager.register(user_id, searching_view)
        
        searching_view.start_status_updates()
        
        await interaction.response.edit_message(
            embed=searching_view.build_searching_embed(),
            view=searching_view
        )
        
        # Store the interaction so we can update the message when match is found
        searching_view.set_interaction(interaction)


class ClearSelectionsButton(discord.ui.Button):
    """Clear all selections button"""
    
    def __init__(self):
        super().__init__(
            label="Clear All Selections",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,  # Red
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Clear all selections
        self.view.selected_bw_race = None
        self.view.selected_sc2_race = None
        self.view.vetoed_maps = []
        
        # Update the view with cleared selections
        await self.view.persist_preferences()
        await self.view.update_embed(interaction)


class CancelQueueSetupButton(discord.ui.Button):
    """Cancel button that shows cancel embed"""
    
    def __init__(self):
        super().__init__(
            label="Cancel",
            emoji="✖️",
            style=discord.ButtonStyle.danger,
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Create and show the cancel embed
        cancel_view = create_cancel_embed()
        await interaction.response.edit_message(
            content="",
            embed=cancel_view.embed,
            view=cancel_view
        )


class QueueView(discord.ui.View):
    """Main queue view with race and map veto selections"""
    
    def __init__(self, discord_user_id: int, default_races=None, default_maps=None):
        super().__init__(timeout=GLOBAL_TIMEOUT)
        self.discord_user_id = discord_user_id
        default_races = default_races or []
        self.selected_bw_race = next((race for race in default_races if race.startswith("bw_")), None)
        self.selected_sc2_race = next((race for race in default_races if race.startswith("sc2_")), None)
        self.vetoed_maps = default_maps or []
        self.add_item(JoinQueueButton())
        self.add_item(ClearSelectionsButton())
        self.add_item(CancelQueueSetupButton())
        self.add_item(BroodWarRaceSelect(default_value=self.selected_bw_race))
        self.add_item(StarCraftRaceSelect(default_value=self.selected_sc2_race))
        self.add_item(MapVetoSelect(default_values=default_maps))


    @classmethod
    async def create(cls, discord_user_id: int, default_races=None, default_maps=None) -> "QueueView":
        view = cls(discord_user_id, default_races=default_races, default_maps=default_maps)
        # Don't persist preferences immediately - only when user makes changes
        return view

    def get_selected_race_codes(self) -> list[str]:
        races: list[str] = []
        if self.selected_bw_race:
            races.append(self.selected_bw_race)
        if self.selected_sc2_race:
            races.append(self.selected_sc2_race)
        return races

    async def persist_preferences(self) -> None:
        races_payload = json.dumps(self.get_selected_race_codes())
        # Sort vetoed maps alphabetically before saving to DB
        sorted_vetoes = sorted(self.vetoed_maps)
        vetoes_payload = json.dumps(sorted_vetoes)

        loop = asyncio.get_running_loop()

        def _write_preferences() -> None:
            try:
                db_writer.update_preferences_1v1(
                    discord_uid=self.discord_user_id,
                    last_chosen_races=races_payload,
                    last_chosen_vetoes=vetoes_payload,
                )
            except Exception as exc:  # pragma: no cover — log and continue
                logger.error("Failed to update 1v1 preferences for user %s: %s", self.discord_user_id, exc)

        await loop.run_in_executor(None, _write_preferences)
    
    def get_embed(self):
        """Get the embed for this view without requiring an interaction"""
        embed = discord.Embed(
            title="🎮 Matchmaking Queue",
            description="Configure your queue preferences",
            color=discord.Color.blue()
        )
        
        # Add race selection info
        selected_codes = self.get_selected_race_codes()
        if selected_codes:
            details = []
            for code in selected_codes:
                label = race_service.get_race_group_label(code)
                name = race_service.get_race_name(code)
                # Get race emote for display
                race_emote = get_race_emote(code)
                # Simplify the label (remove BW/SC2 suffix)
                if label == "Brood War":
                    simplified_label = "Brood War"
                elif label == "StarCraft II":
                    simplified_label = "StarCraft II"
                else:
                    simplified_label = label
                details.append(f"- {simplified_label}: {race_emote} {name}")
            race_list = "\n".join(details)
            embed.add_field(
                name="Selected Races",
                value=race_list,
                inline=False
            )
        else:
            embed.add_field(
                name="Selected Races",
                value="None selected",
                inline=False
            )
        
        # Add map veto info
        veto_count = len(self.vetoed_maps)
        if self.vetoed_maps:
            # Sort maps according to the service's defined order
            map_order = maps_service.get_map_short_names()
            sorted_maps = [map_name for map_name in map_order if map_name in self.vetoed_maps]
            # Add Discord number emotes
            number_emotes = [":one:", ":two:", ":three:", ":four:"]
            map_list = "\n".join([f"{number_emotes[i]} {map_name}" for i, map_name in enumerate(sorted_maps)])
            embed.add_field(
                name=f"Vetoed Maps ({veto_count}/4)",
                value=map_list,
                inline=False
            )
        else:
            embed.add_field(
                name="Vetoed Maps (0/4)",
                value="No vetoes",
                inline=False
            )
        
        return embed
    
    async def update_embed(self, interaction: discord.Interaction):
        """Update the embed with current selections"""
        embed = self.get_embed()
        new_view = await QueueView.create(
            discord_user_id=self.discord_user_id,
            default_races=self.get_selected_race_codes(),
            default_maps=self.vetoed_maps,
        )
        await interaction.response.edit_message(embed=embed, view=new_view)


class QueueSearchingView(discord.ui.View):
    """View shown while searching for a match"""
    
    def __init__(self, original_view, selected_races, vetoed_maps, player):
        super().__init__(timeout=GLOBAL_TIMEOUT)
        self.original_view = original_view
        self.selected_bw_race = next((code for code in selected_races if code.startswith("bw_")), None)
        self.selected_sc2_race = next((code for code in selected_races if code.startswith("sc2_")), None)
        self.vetoed_maps = vetoed_maps
        self.player = player
        self.last_interaction = None
        self.is_active = True
        self.status_task: Optional[asyncio.Task] = None
        self.match_task: Optional[asyncio.Task] = None
        self.status_lock = asyncio.Lock()
        self.last_interaction = None
        
        # Add cancel button
        self.add_item(CancelQueueButton(original_view, player))
        
        # Start async match checking
        self.match_task = asyncio.create_task(self.periodic_match_check())
    
    def start_status_updates(self) -> None:
        if self.status_task is None:
            self.status_task = asyncio.create_task(self.periodic_status_update())

    async def periodic_status_update(self):
        while self.is_active:
            if not await queue_searching_view_manager.has_view(self.player.discord_user_id):
                break
            await asyncio.sleep(15)
            if not self.is_active or self.last_interaction is None:
                continue
            async with self.status_lock:
                if not self.is_active:
                    continue
                try:
                    await self.last_interaction.edit_original_response(
                        embed=self.build_searching_embed(),
                        view=self
                    )
                except Exception:
                    pass

    def build_searching_embed(self) -> discord.Embed:
        stats = matchmaker.get_queue_snapshot()
        next_wave_epoch = int(time.time() - (time.time() % matchmaker.MATCH_INTERVAL_SECONDS) + matchmaker.MATCH_INTERVAL_SECONDS)
        embed = discord.Embed(
            title="🔍 Searching...",
            description=(
                "The queue is searching for a game.\n\n"
                f"- Search interval: {matchmaker.MATCH_INTERVAL_SECONDS} seconds\n"
                f"- Next match wave: <t:{next_wave_epoch}:R>\n"
                f"- Unique players seen in the last 15 minutes: {stats['active_population']}\n"
                "- Current players queueing:\n"
                f"  - Brood War: {stats['bw_only']}\n"
                f"  - StarCraft II: {stats['sc2_only']}\n"
                f"  - Both: {stats['both_races']}"
            ),
            color=discord.Color.blue()
        )
        return embed
    
    async def periodic_match_check(self):
        """Periodically check for matches and update the view"""
        while self.is_active:
            if not await queue_searching_view_manager.has_view(self.player.discord_user_id):
                break
            if self.player.discord_user_id in match_results:
                # Match found! Update the view
                match_result = match_results[self.player.discord_user_id]
                is_player1 = match_result.player_1_discord_id == self.player.discord_user_id
                
                # Create match found view
                match_view = MatchFoundView(match_result, is_player1)
                
                # Register the view for replay detection
                if self.last_interaction:
                    channel_id = self.last_interaction.channel_id
                    await match_view.register_for_replay_detection(channel_id)
                    # Store the interaction reference for later updates
                    match_view.last_interaction = self.last_interaction
                
                # Update the message if we have a stored interaction
                if self.last_interaction:
                    try:
                        await self.last_interaction.edit_original_response(
                            embed=match_view.get_embed(),
                            view=match_view
                        )
                    except:
                        pass  # Interaction might be expired
                
                # Clean up
                del match_results[self.player.discord_user_id]
                await queue_searching_view_manager.unregister(self.player.discord_user_id, view=self)
                break
            
            # Wait 1 second before checking again
            await asyncio.sleep(1)

    async def on_timeout(self):
        """Handle view timeout"""
        # Clean up this view from the manager
        await queue_searching_view_manager.unregister(self.player.discord_user_id, view=self)
        
        # Remove player from matchmaker if they are still in queue
        if await matchmaker.is_player_in_queue(self.player.discord_user_id):
            await matchmaker.remove_player(self.player.discord_user_id)
            print(f"🚪 Player {self.player.user_id} timed out and was removed from queue.")

    def deactivate(self) -> None:
        if not self.is_active:
            return
        self.is_active = False
        if self.status_task:
            self.status_task.cancel()
            self.status_task = None
        if self.match_task:
            self.match_task.cancel()
            self.match_task = None
    
    def set_interaction(self, interaction: discord.Interaction):
        """Store the interaction so we can update the message later"""
        self.last_interaction = interaction


class CancelQueueButton(discord.ui.Button):
    """Cancel button to exit the queue and return to original view"""
    
    def __init__(self, original_view, player):
        super().__init__(
            label="Cancel Queue",
            emoji="✖️",
            style=discord.ButtonStyle.danger,
            row=0
        )
        self.original_view = original_view
        self.player = player
    
    async def callback(self, interaction: discord.Interaction):
        parent_view = self.view

        # If a match has already been found, show the match instead of cancelling
        existing_match = match_results.get(self.player.discord_user_id)
        if existing_match:
            print(f"⚠️ Cancel ignored: match already assigned to {self.player.user_id}")

            # Determine player role in the match
            is_player1 = existing_match.player_1_discord_id == self.player.discord_user_id
            match_view = MatchFoundView(existing_match, is_player1)

            # Register replay detection if possible
            channel_id = interaction.channel_id
            if channel_id is not None:
                await match_view.register_for_replay_detection(channel_id)
            match_view.last_interaction = interaction

            # Stop the searching view heartbeat
            if isinstance(parent_view, QueueSearchingView):
                parent_view.deactivate()

            # Remove this searching view from the manager
            await queue_searching_view_manager.unregister(self.player.discord_user_id, view=parent_view)

            # Prevent duplicate notifications for this player
            match_results.pop(self.player.discord_user_id, None)

            await interaction.response.edit_message(
                embed=match_view.get_embed(),
                view=match_view
            )
            return

        # No match yet—proceed with cancelling the queue entry
        print(f"🚪 Removing player from matchmaker: {self.player.user_id}")
        await matchmaker.remove_player(self.player.discord_user_id)
        
        await queue_searching_view_manager.unregister(self.player.discord_user_id, view=parent_view)
        
        # Return to the original queue view with its embed
        await interaction.response.edit_message(
            embed=self.original_view.get_embed(),
            view=self.original_view
        )


# Global dictionary to store match results by Discord user ID
match_results = {}

async def wait_for_match_completion(match_id: int, timeout: int = 30) -> Optional[dict]:
    """
    Wait for a match to be fully completed and return the final results.
    
    Args:
        match_id: The ID of the match to wait for
        timeout: Maximum time to wait in seconds (default: 30)
    
    Returns:
        Dictionary with final match results or None if timeout/error
    """
    try:
        # Wait for the match completion service to process the match
        final_results = await match_completion_service.wait_for_match_completion(match_id, timeout)
        
        if final_results:
            print(f"✅ Match {match_id} completed with results: {final_results}")
            return final_results
        else:
            print(f"⏰ Match {match_id} completion timed out after {timeout} seconds")
            return None
            
    except Exception as e:
        print(f"❌ Error waiting for match {match_id} completion: {e}")
        return None

def handle_match_result(match_result: MatchResult, register_completion_callback: Callable[[Callable], None]):
    """Handle when a match is found"""
    print(f"🎉 Match #{match_result.match_id}: {match_result.player_1_user_id} vs {match_result.player_2_user_id} | {match_result.map_choice} @ {match_result.server_choice}")
    
    # Store match results for both players
    match_results[match_result.player_1_discord_id] = match_result
    match_results[match_result.player_2_discord_id] = match_result
    
    # Attach the register callback so views can subscribe to completion notifications
    setattr(match_result, 'register_completion_callback', register_completion_callback)


# Set the match callback
matchmaker.set_match_callback(handle_match_result)

class MatchFoundView(discord.ui.View):
    """View shown when a match is found"""
    
    def __init__(self, match_result: MatchResult, is_player1: bool):
        super().__init__(timeout=None)  # No timeout - let match completion service handle cleanup
        self.match_result = match_result
        self.is_player1 = is_player1
        self.selected_result = match_result.match_result
        self.confirmation_status = match_result.match_result_confirmation_status
        self.channel_id = None  # Will be set when the view is sent
        self.last_interaction = None  # Store reference to last interaction for updates
        self.edit_lock = asyncio.Lock()
        
        # Register this view's notification handler with the backend
        if hasattr(match_result, "register_completion_callback"):
            match_result.register_completion_callback(self.handle_completion_notification)

        # Add match result reporting dropdown (moved to row 0)
        self.result_select = MatchResultSelect(match_result, is_player1, self)
        self.add_item(self.result_select)
        
        # Add abort button (moved to row 0)
        self.abort_button = MatchAbortButton(self)
        self.add_item(self.abort_button)

        # Add confirmation dropdown
        self.confirm_select = MatchResultConfirmSelect(self)
        self.add_item(self.confirm_select)

        # Start a background task to disable the abort button when the timer expires
        self.abort_deadline = get_current_unix_timestamp() + matchmaker.ABORT_TIMER_SECONDS
        self.abort_disable_task = asyncio.create_task(self.disable_abort_after_delay())

        # Update dropdown states based on initial data
        self._update_dropdown_states()
    
    async def disable_abort_after_delay(self):
        """A background task to disable the abort button after the deadline."""
        await asyncio.sleep(matchmaker.ABORT_TIMER_SECONDS)

        # Double-check if the button should still be active
        if self.abort_button.disabled or self.match_result.match_result in ["aborted", "conflict", "player1_win", "player2_win", "draw"]:
            return

        self.abort_button.disabled = True

        # Try to update the message
        async with self.edit_lock:
            if self.last_interaction:
                try:
                    # Update the embed to notify the user
                    embed = self.get_embed() # Get the current embed state
                    embed.add_field(name="⚠️ Abort Window Closed", value="The time to abort this match has expired.", inline=False)
                    await self.last_interaction.edit_original_response(embed=embed, view=self)
                except discord.HTTPException as e:
                    print(f"Failed to edit message to disable abort button: {e}")
    
    def _update_dropdown_states(self):
        """Update the state of the dropdowns based on the current view state"""
        # If a replay has been uploaded, enable result selection
        if self.match_result.replay_uploaded == "Yes":
            self.result_select.disabled = False
            self.result_select.placeholder = "Report match result..."
            if self.selected_result:
                # Result has been selected but not confirmed, enable confirmation dropdown
                self.confirm_select.disabled = False
                self.confirm_select.placeholder = "Confirm your selection..."
                
                # Update confirmation dropdown options
                if self.selected_result == "player1_win":
                    result_label = f"{self.result_select.p1_name} victory"
                elif self.selected_result == "player2_win":
                    result_label = f"{self.result_select.p2_name} victory"
                else:
                    result_label = "Draw"
                
                self.confirm_select.options = [
                    discord.SelectOption(
                        label=f"Confirm: {result_label}",
                        value="confirm"
                    )
                ]
                
            # Set default value for result dropdown
            for option in self.result_select.options:
                if option.value == self.selected_result:
                    option.default = True
                else:
                    option.default = False
            else:
                # No result selected yet, disable confirmation dropdown
                self.confirm_select.disabled = True
                self.confirm_select.placeholder = "Select result first..."
                
                # Clear any default selections
                for option in self.result_select.options:
                    option.default = False
        else:
            # No replay uploaded yet, disable both dropdowns
            self.result_select.disabled = True
            self.result_select.placeholder = "Upload replay file to enable result reporting"
            self.confirm_select.disabled = True
            self.confirm_select.placeholder = "Upload replay file first"
    
    def get_embed(self) -> discord.Embed:
        """Get the match found embed"""
        # Get player 1 info
        p1_info = db_reader.get_player_by_discord_uid(self.match_result.player_1_discord_id)
        p1_name = p1_info.get('player_name') if p1_info else None
        p1_country = p1_info.get('country') if p1_info else None
        p1_display_name = p1_name if p1_name else str(self.match_result.player_1_discord_id)
        p1_flag = get_flag_emote(p1_country) if p1_country else get_flag_emote("XX")
        
        # Get player 2 info
        p2_info = db_reader.get_player_by_discord_uid(self.match_result.player_2_discord_id)
        p2_name = p2_info.get('player_name') if p2_info else None
        p2_country = p2_info.get('country') if p2_info else None
        p2_display_name = p2_name if p2_name else str(self.match_result.player_2_discord_id)
        p2_flag = get_flag_emote(p2_country) if p2_country else get_flag_emote("XX")
        
        # Get race information from match result
        p1_race = self.match_result.player_1_race
        p2_race = self.match_result.player_2_race
        
        # Get race emotes
        p1_race_emote = get_race_emote(p1_race)
        p2_race_emote = get_race_emote(p2_race)
        
        # Get MMR values from database
        match_data = db_reader.get_match_1v1(self.match_result.match_id)
        p1_mmr = int(match_data.get('player_1_mmr', 0)) if match_data else 0
        p2_mmr = int(match_data.get('player_2_mmr', 0)) if match_data else 0
        
        # Create title with new format including races and MMR
        title = f"Match #{self.match_result.match_id}: {p1_flag} {p1_race_emote} {p1_display_name} ({p1_mmr}) vs {p2_flag} {p2_race_emote} {p2_display_name} ({p2_mmr})"
        
        # Get race names for display using races service
        p1_race_name = race_service.get_race_name(p1_race)
        p2_race_name = race_service.get_race_name(p2_race)
        
        # Get server information with region using regions service
        server_display = regions_service.format_server_with_region(self.match_result.server_choice)
        
        # Build player information with alt IDs
        p1_info_line = f"- Player 1: {p1_flag} {p1_race_emote} {p1_display_name} ({p1_race_name})"
        if p1_info:
            alt_ids_1 = []
            if p1_info.get('alt_player_name_1'):
                alt_ids_1.append(p1_info.get('alt_player_name_1'))
            if p1_info.get('alt_player_name_2'):
                alt_ids_1.append(p1_info.get('alt_player_name_2'))
            if alt_ids_1:
                p1_info_line += f"\n  - a.k.a. {', '.join(alt_ids_1)}"
        
        p2_info_line = f"- Player 2: {p2_flag} {p2_race_emote} {p2_display_name} ({p2_race_name})"
        if p2_info:
            alt_ids_2 = []
            if p2_info.get('alt_player_name_1'):
                alt_ids_2.append(p2_info.get('alt_player_name_1'))
            if p2_info.get('alt_player_name_2'):
                alt_ids_2.append(p2_info.get('alt_player_name_2'))
            if alt_ids_2:
                p2_info_line += f"\n  - a.k.a. {', '.join(alt_ids_2)}"
        
        embed = discord.Embed(
            title=title,
            description="",  # Empty description as requested
            color=discord.Color.teal()
        )
        
        # Player Information section
        embed.add_field(
            name="**Player Information:**",
            value=f"{p1_info_line}\n{p2_info_line}",
            inline=False
        )
        
        # Match Information section
        map_short_name = self.match_result.map_choice
        map_name = maps_service.get_map_name(map_short_name) or map_short_name

        # Determine map link based on server region
        map_link: Optional[str] = None
        server_code = self.match_result.server_choice
        if server_code:
            region_info = regions_service.get_game_region_for_server(server_code)
            if region_info:
                region_name = (region_info.get("name") or "").lower()
                if "americas" in region_name:
                    map_link = maps_service.get_map_battlenet_link(map_short_name, "americas")
                elif "europe" in region_name:
                    map_link = maps_service.get_map_battlenet_link(map_short_name, "europe")
                elif "asia" in region_name:
                    map_link = maps_service.get_map_battlenet_link(map_short_name, "asia")

        if not map_link:
            # Fallback to Americas link if specific region not available
            map_link = maps_service.get_map_battlenet_link(map_short_name, "americas")

        map_author = maps_service.get_map_author(map_short_name) or "Unknown"
        map_link_display = map_link if map_link else "Unavailable"
        
        embed.add_field(
            name="**Match Information:**",
            value=(
                f"- Map: `{map_name}`\n"
                f"  - Map Link: `{map_link_display}`\n"
                f"  - Author: `{map_author}`\n"
                f"- Server: `{server_display}`\n"
                f"- In-Game Channel: `{self.match_result.in_game_channel}`"
            ),
            inline=False
        )
        
        # Match Result section
        
        if self.match_result.match_result == 'conflict':
            result_display = "Conflict"
            mmr_display = "- MMR Awarded: :x: Report Conflict Detected"
        elif self.match_result.match_result == 'aborted':
            # Pull fresh data so we know who initiated the abort
            match_data = db_reader.get_match_1v1(self.match_result.match_id)
            p1_report = match_data.get("player_1_report") if match_data else None
            p2_report = match_data.get("player_2_report") if match_data else None

            if p1_report == -3:
                aborted_by = p1_display_name
            elif p2_report == -3:
                aborted_by = p2_display_name
            else:
                aborted_by = "Unknown"

            result_display = f"Aborted by {aborted_by}"
            mmr_display = "- MMR Awarded: `+/-0` (Match aborted)"
        elif self.match_result.match_result:
            # Convert to human-readable format
            if self.match_result.match_result == "player1_win":
                result_display = f"{p1_display_name} victory"
            elif self.match_result.match_result == "player2_win":
                result_display = f"{p2_display_name} victory"
            else:  # draw or other value
                print(f"⚠️ EMBED: Unexpected match_result value: '{self.match_result.match_result}'")
                result_display = "Draw"
            
            # Always show MMR field - calculate MMR changes
            p1_mmr_change = getattr(self.match_result, 'p1_mmr_change', None)
            p2_mmr_change = getattr(self.match_result, 'p2_mmr_change', None)
            
            if p1_mmr_change is not None and p2_mmr_change is not None:
                # Round MMR changes to integers using MMR service
                p1_mmr_rounded = mmr_service.round_mmr_change(p1_mmr_change)
                p2_mmr_rounded = mmr_service.round_mmr_change(p2_mmr_change)
                
                # Format MMR changes with proper signs
                p1_sign = "+" if p1_mmr_rounded >= 0 else ""
                p2_sign = "+" if p2_mmr_rounded >= 0 else ""
                
                mmr_display = f"- MMR Awarded: `{p1_display_name}: {p1_sign}{p1_mmr_rounded}`, `{p2_display_name}: {p2_sign}{p2_mmr_rounded}`"
            else:
                # MMR changes not calculated yet - always show TBD
                mmr_display = f"- MMR Awarded: `{p1_display_name}: TBD`, `{p2_display_name}: TBD`"
        else:
            result_display = "Not selected"
            mmr_display = f"- MMR Awarded: `{p1_display_name}: TBD`, `{p2_display_name}: TBD`"
            
        embed.add_field(
            name="**Match Result:**",
            value= (
                f"- Result: `{result_display}`\n"
                f"{mmr_display}"
            ),
            inline=False
        )
        
        # Replay section
        replay_status_value = (
            f"- Replay Uploaded: `{self.match_result.replay_uploaded}`\n"
            f"- Replay Uploaded At: {format_discord_timestamp(self.match_result.replay_upload_time)}"
            if self.match_result.replay_uploaded == "Yes"
            else f"- Replay Uploaded: `{self.match_result.replay_uploaded}`"
        )
        embed.add_field(name="**Replay Status:**", value=replay_status_value, inline=False)

        # Abort validity section
        # Get abort timer deadline (current time + ABORT_TIMER_SECONDS)
        current_time = get_current_unix_timestamp()
        
        # Get remaining aborts for both players
        p1_aborts = user_info_service.get_remaining_aborts(self.match_result.player_1_discord_id)
        p2_aborts = user_info_service.get_remaining_aborts(self.match_result.player_2_discord_id)
        
        abort_validity_value = (
            f"You can use the button below to abort the match if you are unable to play.\n"
            f"Aborting matches has no MMR penalty, but you have a limited number per month.\n" 
            f"Abusing this feature (e.g., dodging opponents/matchups, repeatedly aborting at\n"
            f"the last second, deliberately wasting the time of others, etc.) will result in a ban.\n"
            f"You can only abort the match before <t:{self.abort_deadline}:T> (<t:{self.abort_deadline}:R>)."
        )
        embed.add_field(name="**Can't play? Need to leave?**", value=abort_validity_value, inline=False)
        
        return embed

    async def register_for_replay_detection(self, channel_id: int):
        """Register this view to receive replay file uploads"""
        self.channel_id = channel_id
        await match_found_view_manager.register(
            self.match_result.match_id, channel_id, self
        )
    
    async def handle_completion_notification(self, status: str, data: dict):
        """This is the callback that the backend will invoke."""
        if status == "complete":
            # Update the view's internal state with the final results
            result_raw = data.get('match_result_raw')
            result_map = {
                1: "player1_win",
                2: "player2_win",
                0: "draw",
                -1: "aborted",
                -2: "conflict"
            }
            mapped_result = result_map.get(result_raw)

            self.match_result.match_result = mapped_result
            self.match_result.p1_mmr_change = data.get('p1_mmr_change')
            self.match_result.p2_mmr_change = data.get('p2_mmr_change')
            if mapped_result:
                self.match_result.match_result_confirmation_status = "Confirmed"
            
            # Disable components and update the original embed
            self.disable_all_components()
            async with self.edit_lock:
                if self.last_interaction:
                    await self.last_interaction.edit_original_response(
                        embed=self.get_embed(),
                        view=self
                    )
            
            # Send the final gold embed as a follow-up
            await self._send_final_notification_embed(data)
            
        elif status == "abort":
            # Update the view's internal state to reflect the abort
            self.match_result.match_result = "aborted"
            self.match_result.match_result_confirmation_status = "Aborted"

            # Immediately disable all components to prevent further actions
            self.disable_all_components()

            # Update the embed with the abort information
            async with self.edit_lock:
                if self.last_interaction:
                    try:
                        await self.last_interaction.edit_original_response(
                            embed=self.get_embed(),
                            view=self
                        )
                    except discord.HTTPException:
                        pass  # Non-critical if this fails, the main state is updated

            # Send a follow-up notification to ensure the user sees the final state
            await self._send_abort_notification_embed()
            
            # The view's work is done
            self.stop()
            
        elif status == "conflict":
            # Update the view's state to reflect the conflict
            self.match_result.match_result = "conflict"
            
            # Disable components and update the original embed
            self.disable_all_components()
            async with self.edit_lock:
                if self.last_interaction:
                    await self.last_interaction.edit_original_response(
                        embed=self.get_embed(),
                        view=self
                    )

            # Send the conflict embed as a follow-up
            await self._send_conflict_notification_embed()

        # The view's work is done
        self.stop()
        
    async def _send_final_notification_embed(self, final_results: dict):
        """Creates and sends the final gold embed notification."""
        if not self.last_interaction:
            return

        p1_info = final_results['p1_info']
        p2_info = final_results['p2_info']
        p1_name = final_results['p1_name']
        p2_name = final_results['p2_name']

        p1_flag = get_flag_emote(p1_info.get('country', 'XX'))
        p2_flag = get_flag_emote(p2_info.get('country', 'XX'))
        p1_race_emote = get_race_emote(final_results['p1_race'])
        p2_race_emote = get_race_emote(final_results['p2_race'])

        p1_current_mmr = final_results['p1_current_mmr']
        p2_current_mmr = final_results['p2_current_mmr']
        p1_mmr_change = final_results['p1_mmr_change']
        p2_mmr_change = final_results['p2_mmr_change']
        p1_new_mmr = p1_current_mmr + p1_mmr_change
        p2_new_mmr = p2_current_mmr + p2_mmr_change

        p1_mmr_rounded = mmr_service.round_mmr_change(p1_mmr_change)
        p2_mmr_rounded = mmr_service.round_mmr_change(p2_mmr_change)

        notification_embed = discord.Embed(
            title=f"🏆 Match #{self.match_result.match_id} Result Finalized",
            description=f"**{p1_flag} {p1_race_emote} {p1_name} ({int(p1_current_mmr)} → {int(p1_new_mmr)})** vs **{p2_flag} {p2_race_emote} {p2_name} ({int(p2_current_mmr)} → {int(p2_new_mmr)})**",
            color=discord.Color.gold()
        )

        p1_sign = "+" if p1_mmr_rounded >= 0 else ""
        p2_sign = "+" if p2_mmr_rounded >= 0 else ""

        notification_embed.add_field(
            name="**MMR Changes:**",
            value=f"- {p1_name}: `{p1_sign}{p1_mmr_rounded} ({int(p1_current_mmr)} → {int(p1_new_mmr)})`\n- {p2_name}: `{p2_sign}{p2_mmr_rounded} ({int(p2_current_mmr)} → {int(p2_new_mmr)})`",
            inline=False
        )
        
        try:
            await self.last_interaction.followup.send(embed=notification_embed, ephemeral=False)
        except discord.HTTPException as e:
            print(f"Error sending final notification for match {self.match_result.match_id}: {e}")

    async def _send_conflict_notification_embed(self):
        """Sends a new follow-up message indicating a match conflict."""
        if not self.last_interaction:
            return
            
        conflict_embed = discord.Embed(
            title="⚠️ Match Result Conflict",
            description="The reported results for this match do not agree. Please contact an administrator to resolve this dispute.",
            color=discord.Color.red()
        )
        try:
            await self.last_interaction.followup.send(embed=conflict_embed, ephemeral=False)
        except discord.HTTPException as e:
            print(f"Error sending conflict notification for match {self.match_result.match_id}: {e}")

    async def _send_abort_notification_embed(self):
        """Sends a follow-up message indicating the match was aborted."""
        if not self.last_interaction:
            return

        match_data = db_reader.get_match_1v1(self.match_result.match_id)
        if not match_data:
            return

        p1_info = db_reader.get_player_by_discord_uid(match_data['player_1_discord_uid'])
        p2_info = db_reader.get_player_by_discord_uid(match_data['player_2_discord_uid'])

        p1_name = p1_info.get('player_name') if p1_info else str(match_data['player_1_discord_uid'])
        p2_name = p2_info.get('player_name') if p2_info else str(match_data['player_2_discord_uid'])

        aborted_by = "Unknown"
        if match_data.get("player_1_report") == -3:
            aborted_by = p1_name
        elif match_data.get("player_2_report") == -3:
            aborted_by = p2_name
            
        p1_flag = get_flag_emote(p1_info.get('country', 'XX')) if p1_info else '🏳️'
        p2_flag = get_flag_emote(p2_info.get('country', 'XX')) if p2_info else '🏳️'
        p1_race_emote = get_race_emote(match_data.get('player_1_race'))
        p2_race_emote = get_race_emote(match_data.get('player_2_race'))

        p1_current_mmr = match_data['player_1_mmr']
        p2_current_mmr = match_data['player_2_mmr']

        abort_embed = discord.Embed(
            title=f"🛑 Match #{self.match_result.match_id} Aborted",
            description=f"**{p1_flag} {p1_race_emote} {p1_name} ({int(p1_current_mmr)})** vs **{p2_flag} {p2_race_emote} {p2_name} ({int(p2_current_mmr)})**",
            color=discord.Color.red()
        )

        abort_embed.add_field(
            name="**MMR Changes:**",
            value=f"- {p1_name}: `+0 ({int(p1_current_mmr)})`\n- {p2_name}: `+0 ({int(p2_current_mmr)})`",
            inline=False
        )
        
        abort_embed.add_field(
            name="**Reason:**",
            value=f"The match was aborted by **{aborted_by}**. No MMR changes were applied.",
            inline=False
        )

        try:
            await self.last_interaction.followup.send(embed=abort_embed, ephemeral=False)
        except discord.HTTPException as e:
            print(f"Error sending abort notification for match {self.match_result.match_id}: {e}")

    def disable_all_components(self):
        """Disables all components in the view."""
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

    async def on_timeout(self):
        pass # Timeout is now handled by the match completion service


class MatchAbortButton(discord.ui.Button):
    """Button to abort the match"""
    
    def __init__(self, parent_view):
        self.parent_view = parent_view
        self.awaiting_confirmation = False  # Track confirmation state
        viewer_id = (
            parent_view.match_result.player_1_discord_id
            if parent_view.is_player1
            else parent_view.match_result.player_2_discord_id
        )
        remaining_aborts = user_info_service.get_remaining_aborts(viewer_id)
        label_text = f"Abort Match ({remaining_aborts} left this month)"
        
        is_disabled = remaining_aborts == 0
        
        super().__init__(
            emoji="🛑",
            label=label_text,
            style=discord.ButtonStyle.danger,
            row=0,
            disabled=is_disabled
        )
    
    async def callback(self, interaction: discord.Interaction):
        player_discord_uid = interaction.user.id
        
        # If not yet in confirmation state, show confirmation prompt
        if not self.awaiting_confirmation:
            remaining_aborts = user_info_service.get_remaining_aborts(player_discord_uid)
            self.label = f"Confirm Abort ({remaining_aborts} remaining)"
            self.style = discord.ButtonStyle.danger  # Keep danger style
            self.awaiting_confirmation = True
            
            # Update the view to show the confirmation button
            async with self.parent_view.edit_lock:
                await interaction.response.edit_message(
                    embed=self.parent_view.get_embed(),
                    view=self.parent_view
                )
            return
        
        # If already in confirmation state, proceed with abort
        # Atomically abort the match
        success = matchmaker.abort_match(
            self.parent_view.match_result.match_id,
            player_discord_uid
        )
        
        if success:
            # The backend will now handle notifications.
            # We just need to update the UI to a disabled state.
            
            # Update button label
            remaining_aborts = user_info_service.get_remaining_aborts(player_discord_uid)
            self.label = f"Match Aborted ({remaining_aborts} left this month)"

            self.parent_view.disable_all_components()

            # Stop the abort disable task as the match is now aborted
            if self.parent_view.abort_disable_task and not self.parent_view.abort_disable_task.done():
                self.parent_view.abort_disable_task.cancel()
            
            # Update the embed to show abort status temporarily
            # The backend will send the final authoritative state
            async with self.parent_view.edit_lock:
                await interaction.response.edit_message(
                    embed=self.parent_view.get_embed(), 
                    view=self.parent_view
                )
        else:
            await interaction.response.send_message("❌ Failed to abort match. It might have been already completed or aborted by the other player.")


class MatchResultConfirmSelect(discord.ui.Select):
    """Confirmation dropdown for match result"""
    
    def __init__(self, parent_view):
        self.parent_view = parent_view
        
        # Create placeholder option (will be replaced when result is selected)
        options = [
            discord.SelectOption(
                label="Awaiting selection...",
                value="placeholder"
            )
        ]
        
        super().__init__(
            placeholder="Select result first...",
            min_values=1,
            max_values=1,
            options=options,
            disabled=True,
            row=2
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Persist the confirmation status
        self.parent_view.match_result.match_result_confirmation_status = "Confirmed"
        
        # Set the selected option as default for persistence
        for option in self.options:
            option.default = (option.value == self.values[0])
        
        # Disable both dropdowns and abort button after confirmation
        self.parent_view.result_select.disabled = True
        self.parent_view.confirm_select.disabled = True
        self.parent_view.abort_button.disabled = True
        self.parent_view.last_interaction = interaction

        # Stop the abort disable task as a result has been confirmed
        if self.parent_view.abort_disable_task and not self.parent_view.abort_disable_task.done():
            self.parent_view.abort_disable_task.cancel()

        # Update the message to show the final state before backend processing
        async with self.parent_view.edit_lock:
            await interaction.response.edit_message(
                embed=self.parent_view.get_embed(), view=self.parent_view
            )

        # Now, send the report to the backend for final processing.
        # The completion handler will send the final embed update.
        await self.parent_view.result_select.record_player_report(
            self.parent_view.selected_result
        )


class MatchResultSelect(discord.ui.Select):
    """Dropdown for reporting match results"""
    
    def __init__(self, match_result: MatchResult, is_player1: bool, parent_view):
        self.match_result = match_result
        self.is_player1 = is_player1
        self.parent_view = parent_view
        
        # Get player names from database
        p1_info = db_reader.get_player_by_discord_uid(match_result.player_1_discord_id)
        self.p1_name = p1_info.get('player_name') if p1_info else str(match_result.player_1_user_id)
        
        p2_info = db_reader.get_player_by_discord_uid(match_result.player_2_discord_id)
        self.p2_name = p2_info.get('player_name') if p2_info else str(match_result.player_2_user_id)
        
        # Create options for the dropdown
        options = [
            discord.SelectOption(
                label=f"{self.p1_name} victory",
                value="player1_win"
            ),
            discord.SelectOption(
                label=f"{self.p2_name} victory", 
                value="player2_win"
            ),
            discord.SelectOption(
                label="Draw",
                value="draw"
            )
        ]
        
        super().__init__(
            placeholder="Report match result...",
            min_values=1,
            max_values=1,
            options=options,
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Check if replay is uploaded before allowing result selection
        if self.parent_view.match_result.replay_uploaded != "Yes":
            await interaction.response.send_message("❌ Please upload a replay file before reporting match results.")
            return
        
        # Store the selected result in parent view and persist it
        self.parent_view.selected_result = self.values[0]
        self.parent_view.match_result.match_result = self.values[0]
        
        # Set default value for result dropdown (for persistence)
        for option in self.options:
            option.default = (option.value == self.values[0])
        
        # Get result label for confirmation dropdown
        if self.values[0] == "player1_win":
            result_label = f"{self.p1_name} victory"
        elif self.values[0] == "player2_win":
            result_label = f"{self.p2_name} victory"
        else:
            result_label = "Draw"
        
        # Enable and update confirmation dropdown
        self.parent_view.confirm_select.disabled = False
        self.parent_view.confirm_select.options = [
            discord.SelectOption(
                label=f"Confirm: {result_label}",
                value="confirm"
            )
        ]
        self.parent_view.confirm_select.placeholder = "Confirm your selection..."
        
        # Update the message (DO NOT call _update_dropdown_states() as it would reset our changes)
        self.parent_view.last_interaction = interaction
        async with self.parent_view.edit_lock:
            await interaction.response.edit_message(
                embed=self.parent_view.get_embed(), view=self.parent_view
            )
    
    async def record_player_report(self, result: str):
        """Record a player's individual report for the match"""
        # Convert result to report value format
        if result == "player1_win":
            report_value = 1
        elif result == "player2_win":
            report_value = 2
        else:
            report_value = 0
        
        try:
            current_player_id = self.parent_view.match_result.player_1_discord_id if self.is_player1 else self.parent_view.match_result.player_2_discord_id
            success = matchmaker.record_match_result(self.match_result.match_id, current_player_id, report_value)
            
            if success:
                print(f"📝 Player report recorded for match {self.match_result.match_id}. Waiting for backend notification.")
            else:
                print(f"❌ Failed to record player report for match {self.match_result.match_id}")
        except Exception as e:
            print(f"❌ Error recording player report: {e}")
    
    async def update_embed_with_mmr_changes(self):
        """Update the embed to show MMR changes"""
        try:
            # Update the original message with new embed
            if hasattr(self.parent_view, 'last_interaction') and self.parent_view.last_interaction:
                embed = self.parent_view.get_embed()
                await self.parent_view.last_interaction.edit_original_response(
                    embed=embed,
                    view=self.parent_view
                )
            
        except Exception as e:
            print(f"❌ Error updating embed with MMR changes: {e}")
    
    # Removed handle_disagreement - no longer needed with individual reporting
    
    def get_selected_label(self):
        """Get the label for the selected result"""
        if self.values[0] == "player1_win":
            return f"{self.match_result.player_1_user_id} Won"
        elif self.values[0] == "player2_win":
            return f"{self.match_result.player_2_user_id} Won"
        else:
            return "Draw"
    
    async def notify_other_player_result(self, original_embed, result_embed):
        """Notify the other player about the match result"""
        # Notify both players about the result
        for player_id in [self.parent_view.match_result.player_1_discord_id, self.parent_view.match_result.player_2_discord_id]:
            other_view = await queue_searching_view_manager.get_view(player_id)
            if other_view and hasattr(other_view, 'last_interaction') and other_view.last_interaction:
                    try:
                        # Disable the dropdown in the other player's view
                        for item in other_view.children:
                            if isinstance(item, MatchResultSelect):
                                item.disabled = True
                                item.placeholder = f"Selected: {item.get_selected_label()}"
                        
                        # Update the other player's message
                        await other_view.last_interaction.edit_original_response(
                            embeds=[original_embed, result_embed],
                            view=other_view
                        )
                    except:
                        pass  # Interaction might be expired
    
    async def notify_other_player_disagreement(self, original_embed, disagreement_embed):
        """Notify the other player about the disagreement"""
        # Notify both players about the disagreement
        for player_id in [self.parent_view.match_result.player_1_discord_id, self.parent_view.match_result.player_2_discord_id]:
            other_view = await queue_searching_view_manager.get_view(player_id)
            if other_view and hasattr(other_view, 'last_interaction') and other_view.last_interaction:
                    try:
                        # Disable the dropdown in the other player's view
                        for item in other_view.children:
                            if isinstance(item, MatchResultSelect):
                                item.disabled = True
                                item.placeholder = f"Selected: {item.get_selected_label()}"
                        
                        # Update the other player's message
                        await other_view.last_interaction.edit_original_response(
                            embeds=[original_embed, disagreement_embed],
                            view=other_view
                        )
                    except:
                        pass  # Interaction might be expired
    
    async def record_player_report(self, result: str):
        """Record a player's individual report for the match"""
        # Convert result to report value format
        if result == "player1_win":
            report_value = 1
        elif result == "player2_win":
            report_value = 2
        else:
            report_value = 0
        
        try:
            current_player_id = self.parent_view.match_result.player_1_discord_id if self.is_player1 else self.parent_view.match_result.player_2_discord_id
            success = matchmaker.record_match_result(self.match_result.match_id, current_player_id, report_value)
            
            if success:
                print(f"📝 Player report recorded for match {self.match_result.match_id}. Waiting for backend notification.")
            else:
                print(f"❌ Failed to record player report for match {self.match_result.match_id}")
        except Exception as e:
            print(f"❌ Error recording player report: {e}")
    
    async def update_embed_with_mmr_changes(self):
        """Update the embed to show MMR changes"""
        try:
            # Update the original message with new embed
            if hasattr(self.parent_view, 'last_interaction') and self.parent_view.last_interaction:
                embed = self.parent_view.get_embed()
                await self.parent_view.last_interaction.edit_original_response(
                    embed=embed,
                    view=self.parent_view
                )
            
        except Exception as e:
            print(f"❌ Error updating embed with MMR changes: {e}")
    
    # Removed handle_disagreement_silent - no longer needed with individual reporting


class BroodWarRaceSelect(discord.ui.Select):
    def __init__(self, default_value: Optional[str] = None):
        options = [
            discord.SelectOption(
                label=label,
                value=value,
                description=description,
                default=value == default_value,
            )
            for label, value, description in race_service.get_race_dropdown_groups()["brood_war"]
        ]
        super().__init__(
            placeholder="Select your Brood War race (max 1)",
            min_values=0,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_bw_race = self.values[0] if self.values else None
        await self.view.persist_preferences()
        await self.view.update_embed(interaction)


class StarCraftRaceSelect(discord.ui.Select):
    def __init__(self, default_value: Optional[str] = None):
        options = [
            discord.SelectOption(
                label=label,
                value=value,
                description=description,
                default=value == default_value,
            )
            for label, value, description in race_service.get_race_dropdown_groups()["starcraft2"]
        ]
        super().__init__(
            placeholder="Select your StarCraft II race (max 1)",
            min_values=0,
            max_values=1,
            options=options,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_sc2_race = self.values[0] if self.values else None
        await self.view.persist_preferences()
        await self.view.update_embed(interaction)


async def on_message(message: discord.Message, bot=None):
    """
    Listen for SC2Replay file uploads in channels with active match views.
    Uses multiprocessing to parse replays without blocking the event loop.
    
    Args:
        message: The Discord message containing the replay attachment
        bot: The bot instance (required to access the process pool)
    """
    # Ignore bot messages
    if message.author.bot:
        return
    
    # Check if there are any attachments
    if not message.attachments:
        return
    
    # Check if any attachment is an SC2Replay file
    replay_attachment = None
    
    for attachment in message.attachments:
        if replay_service.is_sc2_replay(attachment.filename):
            replay_attachment = attachment
            break  # Take the first SC2Replay file and ignore the rest
    
    if not replay_attachment:
        return
    
    # Find the corresponding match view from the channel map
    match_view = channel_to_match_view_map.get(message.channel.id)
    
    if not match_view:
        return
    
    try:
        # Download the replay file
        replay_bytes = await replay_attachment.read()
        
        print(f"[Main Process] Replay uploaded by {message.author.name} "
              f"(size: {len(replay_bytes)} bytes). Offloading to worker process...")
        
        # --- MULTIPROCESSING INTEGRATION ---
        # Get the current asyncio event loop
        loop = asyncio.get_running_loop()
        
        # Offload the blocking parsing function to the process pool
        # The 'await' here does NOT block the bot. It pauses this
        # function and lets the event loop run other tasks.
        try:
            if bot and hasattr(bot, 'process_pool'):
                replay_info = await loop.run_in_executor(
                    bot.process_pool, parse_replay_data_blocking, replay_bytes
                )
            else:
                # Fallback to synchronous parsing if process pool is not available
                # This shouldn't happen in production, but provides a safety net
                print("[WARN] Process pool not available, falling back to synchronous parsing")
                replay_info = parse_replay_data_blocking(replay_bytes)
                
        except Exception as e:
            # This will catch any exception from the worker process
            print(f"[FATAL] Replay parsing in worker process failed: {type(e).__name__}: {e}")
            error_embed = ReplayDetailsEmbed.get_error_embed(
                "A critical error occurred while parsing the replay. "
                "The file may be corrupted. Please notify an admin."
            )
            await message.channel.send(embed=error_embed)
            return
        
        print(f"[Main Process] Received result from worker process")
        
        # Check if parsing failed
        if replay_info.get("error"):
            error_message = replay_info["error"]
            print(f"[Main Process] Worker process reported parsing error: {error_message}")
            
            # Send the red error embed
            error_embed = ReplayDetailsEmbed.get_error_embed(error_message)
            await message.channel.send(embed=error_embed)
            
            # Update the match view to show "Replay Invalid"
            match_view.match_result.replay_uploaded = "Replay Invalid"
            match_view._update_dropdown_states()
            if match_view.last_interaction:
                with suppress(discord.NotFound, discord.InteractionResponded):
                    await match_view.last_interaction.edit_original_response(
                        embed=match_view.get_embed(), view=match_view
                    )
            
            print(f"❌ Failed to parse replay for match {match_view.match_result.match_id}: {error_message}")
            return
        
        # Use the new method that accepts pre-parsed data
        result = replay_service.store_upload_from_parsed_dict(
            match_view.match_result.match_id,
            message.author.id,
            replay_bytes,
            replay_info
        )
        
        if result.get("success"):
            unix_epoch = result.get("unix_epoch")
            match_view.match_result.replay_uploaded = "Yes"
            match_view.match_result.replay_upload_time = unix_epoch
            
            # Send replay details embed as a new message
            replay_data = result.get("replay_data")
            if replay_data:
                replay_embed = ReplayDetailsEmbed.get_success_embed(replay_data)
                await message.channel.send(embed=replay_embed)
            
            # Update all views for the match
            match_views = await match_found_view_manager.get_views_by_match_id(match_view.match_result.match_id)
            for _, view in match_views:
                view.match_result.replay_uploaded = "Yes"
                view.match_result.replay_upload_time = unix_epoch
                view._update_dropdown_states()
                if view.last_interaction:
                    with suppress(discord.NotFound, discord.InteractionResponded):
                        await view.last_interaction.edit_original_response(
                            embed=view.get_embed(), view=view
                        )
            
            print(f"✅ Replay file stored for match {match_view.match_result.match_id} (player: {message.author.id})")
        else:
            # Handle failure, including parsing errors
            error_message = result.get("error")
            if error_message:
                # Send the red error embed
                error_embed = ReplayDetailsEmbed.get_error_embed(error_message)
                await message.channel.send(embed=error_embed)

                # Update the match view to show "Replay Invalid"
                match_view.match_result.replay_uploaded = "Replay Invalid"
                match_view._update_dropdown_states()
                if match_view.last_interaction:
                    with suppress(discord.NotFound, discord.InteractionResponded):
                        await match_view.last_interaction.edit_original_response(
                            embed=match_view.get_embed(), view=match_view
                        )
            
            print(f"❌ Failed to store replay for match {match_view.match_result.match_id}: {error_message}")

    except Exception as e:
        print(f"❌ Error processing replay file: {e}")

