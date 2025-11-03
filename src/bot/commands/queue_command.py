import asyncio
import json
import logging
from functools import partial
from typing import Callable, Dict, Optional

import discord
from discord import app_commands

from src.backend.db.db_reader_writer import get_timestamp
from src.bot.config import QUEUE_SEARCHING_HEARTBEAT_SECONDS
from src.backend.services.app_context import (
    command_guard_service as guard_service,
    maps_service,
    mmr_service,
    notification_service,
    queue_service,
    races_service as race_service,
    regions_service,
    replay_service,
    user_info_service,
)
from src.backend.services.command_guard_service import CommandGuardError
from src.backend.services.match_completion_service import match_completion_service
from src.backend.services.matchmaking_service import MatchResult, Player, QueuePreferences, matchmaker
from src.backend.services.replay_service import ReplayRaw, parse_replay_data_blocking
from src.backend.services.user_info_service import get_user_info
from src.bot.components.cancel_embed import create_cancel_embed
from src.bot.components.command_guard_embeds import create_command_guard_error_embed
from src.bot.components.confirm_restart_cancel_buttons import ConfirmRestartCancelButtons
from src.bot.utils.message_helpers import (
    queue_interaction_defer,
    queue_interaction_edit,
    queue_followup,
    queue_channel_send,
    queue_message_edit,
    queue_edit_original
)
from src.bot.components.error_embed import ErrorEmbedException, create_error_view_from_exception
from src.bot.utils.command_decorators import dm_only, auto_apply_dm_guard
from src.bot.utils.discord_utils import (
    format_discord_timestamp,
    get_current_unix_timestamp,
    get_flag_emote,
    get_race_emote,
    send_ephemeral_response,
    get_rank_emote,
    get_globe_emote,
    followup_ephemeral_response
)
import time
from contextlib import suppress

from src.backend.services.performance_service import FlowTracker
from src.bot.components.replay_details_embed import ReplayDetailsEmbed
from src.bot.config import GLOBAL_TIMEOUT
from src.backend.core.config import EXPECTED_GAME_PRIVACY, EXPECTED_GAME_SPEED, EXPECTED_GAME_DURATION, EXPECTED_LOCKED_ALLIANCES


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
@dm_only
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

    # Check player state atomically (single source of truth)
    flow.checkpoint("check_player_state_start")
    from src.backend.services.app_context import data_access_service
    player_state = data_access_service.get_player_state(interaction.user.id)
    if player_state != "idle":
        flow.complete("already_queued")
        error = ErrorEmbedException(
            title="Queueing Not Allowed",
            description="You are already in a queue or an active match."
        )
        error_view = create_error_view_from_exception(error)
        await send_ephemeral_response(interaction, embed=error_view.embed, view=error_view)
        return
    
    flow.checkpoint("check_player_state_complete")
    
    # Get user's saved preferences from DataAccessService (in-memory, instant)
    flow.checkpoint("load_preferences_start")
    from src.backend.services.data_access_service import DataAccessService
    data_service = DataAccessService()
    user_preferences = data_service.get_player_preferences(interaction.user.id)
    
    if user_preferences:
        # Parse saved preferences from database
        try:
            default_races = json.loads(user_preferences['last_chosen_races'])
            default_maps = json.loads(user_preferences['last_chosen_vetoes'])
        except (json.JSONDecodeError, TypeError, KeyError):
            # If parsing fails or keys don't exist, use empty defaults
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
                    value=map_data["name"],
                    default=map_data["name"] in (default_values or [])
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
        flow = FlowTracker("join_queue_button", user_id=interaction.user.id)
        
        flow.checkpoint("defer_interaction_start")
        # Defer the interaction immediately to prevent timeouts
        await queue_interaction_defer(interaction)
        flow.checkpoint("defer_interaction_complete")

        flow.checkpoint("validate_race_selection")
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
            
            flow.complete("validation_failed_no_race")
            await followup_ephemeral_response(
                interaction,
                embed=error_view.embed,
                view=error_view,
            )
            return
        
        flow.checkpoint("get_user_info")
        # Get user info
        user_info = get_user_info(interaction)
        user_id = user_info["id"]

        flow.checkpoint("check_duplicate_queue")
        # Check player state atomically (single source of truth)
        from src.backend.services.app_context import data_access_service
        player_state = data_access_service.get_player_state(user_id)
        if player_state != "idle":
            flow.complete("already_queued")
            error = ErrorEmbedException(
                title="Queueing Not Allowed",
                description="You cannot queue more than once, or while a match is active."
            )
            error_view = create_error_view_from_exception(error)
            await followup_ephemeral_response(interaction, embed=error_view.embed, view=error_view)
            return
        
        flow.checkpoint("persist_preferences")
        # Persist current preferences before joining queue
        await self.view.persist_preferences()
        
        flow.checkpoint("create_queue_preferences")
        # Create queue preferences
        preferences = QueuePreferences(
            selected_races=self.view.get_selected_race_codes(),
            vetoed_maps=self.view.vetoed_maps,
            discord_user_id=user_id,
            user_id="Player" + str(user_id)  # TODO: Get actual user ID from database
        )
        
        flow.checkpoint("create_player_object")
        # Create player and add to matchmaking queue
        player = Player(
            discord_user_id=user_id,
            user_id=preferences.user_id,
            preferences=preferences
        )
        
        flow.checkpoint("set_queueing_state")
        # Optimistically set player state to queueing BEFORE adding to matchmaker
        # This provides more durable queue protection
        from src.backend.services.app_context import data_access_service
        await data_access_service.set_player_state(user_id, "queueing")
        
        flow.checkpoint("add_player_to_matchmaker_start")
        # Try to add player to matchmaker
        try:
            print(f"🎮 Adding player to matchmaker: {player.user_id}")
            await matchmaker.add_player(player)
            flow.checkpoint("add_player_to_matchmaker_complete")
        except Exception as e:
            # Rollback state change on failure
            flow.checkpoint("add_player_failed_rollback")
            await data_access_service.set_player_state(user_id, "idle")
            print(f"❌ Failed to add player to matchmaker: {e}")
            raise
        
        flow.checkpoint("create_searching_view")
        # Show searching state
        searching_view = QueueSearchingView(
            original_view=self.view,
            selected_races=self.view.get_selected_race_codes(),
            vetoed_maps=self.view.vetoed_maps,
            player=player
        )
        
        flow.checkpoint("register_view_manager")
        await queue_searching_view_manager.register(user_id, searching_view)
        
        flow.checkpoint("start_status_updates")
        searching_view.start_status_updates()
        
        flow.checkpoint("build_and_send_embed_start")
        await queue_edit_original(
            interaction,
            embed=searching_view.build_searching_embed(),
            view=searching_view
        )
        flow.checkpoint("build_and_send_embed_complete")
        
        # Store the interaction so we can update the message when match is found
        searching_view.set_interaction(interaction)
        
        # Capture channel and message ID for persistent tracking
        flow.checkpoint("capture_message_context")
        searching_view.channel = interaction.channel
        original_message = await interaction.original_response()
        searching_view.message_id = original_message.id
        flow.checkpoint("capture_message_context_complete")
        
        flow.complete("success")


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
        await queue_interaction_edit(
            interaction,
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

        try:
            # Use DataAccessService for async write
            from src.backend.services.data_access_service import DataAccessService
            data_service = DataAccessService()
            
            # Call async method directly
            await data_service.update_player_preferences(
                discord_uid=self.discord_user_id,
                last_chosen_races=races_payload,
                last_chosen_vetoes=vetoes_payload
            )
        except Exception as exc:  # pragma: no cover — log and continue
            logger.error("Failed to update 1v1 preferences for user %s: %s", self.discord_user_id, exc)
    
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
            # Convert full names to short names for display
            short_names = []
            for full_name in self.vetoed_maps:
                short_name = maps_service.get_short_name_by_full_name(full_name)
                short_names.append(short_name)
            
            # Sort maps according to the service's defined order
            map_order = maps_service.get_map_short_names()
            sorted_maps = [map_name for map_name in map_order if map_name in short_names]
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
        await queue_interaction_edit(interaction, embed=embed, view=new_view)


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
        self.channel: Optional[discord.TextChannel] = None
        self.message_id: Optional[int] = None
        
        # Add cancel button
        self.add_item(CancelQueueButton(original_view, player))
        
        # Start async match listener (push-based notifications)
        self.match_task = asyncio.create_task(self._listen_for_match())
    
    def start_status_updates(self) -> None:
        if self.status_task is None:
            self.status_task = asyncio.create_task(self.periodic_status_update())

    async def periodic_status_update(self):
        while self.is_active:
            if not await queue_searching_view_manager.has_view(self.player.discord_user_id):
                break
            await asyncio.sleep(QUEUE_SEARCHING_HEARTBEAT_SECONDS)
            if not self.is_active or self.last_interaction is None:
                continue
            async with self.status_lock:
                if not self.is_active:
                    continue
                try:
                    await queue_edit_original(
                        self.last_interaction,
                        embed=self.build_searching_embed(),
                        view=self
                    )
                except Exception:
                    pass

    def build_searching_embed(self) -> discord.Embed:
        stats = matchmaker.get_queue_snapshot()
        next_wave_epoch = matchmaker.get_next_matchmaking_time()
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
    
    async def _listen_for_match(self):
        """
        Listen for match notifications (push-based, not polling).
        
        This method blocks until a match is found and published by the notification service.
        It provides instant notification without the overhead and delay of polling.
        """
        flow = FlowTracker(f"listen_for_match", user_id=self.player.discord_user_id)
        
        flow.checkpoint("subscribe_to_notifications")
        # Subscribe to notifications and get our personal queue
        notification_queue = await notification_service.subscribe(self.player.discord_user_id)
        
        try:
            flow.checkpoint("waiting_for_match")
            # Block here until a match is published (instant notification!)
            match_result = await notification_queue.get()
            flow.checkpoint("match_notification_received")
            
            flow.checkpoint("process_match_result_start")
            # Match found! Update the view immediately
            is_player1 = match_result.player_1_discord_id == self.player.discord_user_id
            
            flow.checkpoint("edit_searching_message_to_confirmation")
            # Step 1: Edit the original "Searching..." message to show match found confirmation
            if not self.last_interaction:
                raise RuntimeError(f"Cannot display match view: no interaction stored for player {self.player.discord_user_id}")
            
            # Create a nice confirmation embed
            opponent_name = match_result.player_2_user_id if is_player1 else match_result.player_1_user_id
            opponent_display = f"vs {opponent_name}"
            
            confirmation_embed = discord.Embed(
                title="🎉 Match Found!",
                description=f"Your match is ready. Full details below.",
                color=discord.Color.green()
            )
            
            await queue_edit_original(
                self.last_interaction,
                content=None,
                embed=confirmation_embed,
                view=None
            )
            flow.checkpoint("searching_message_edited")
            
            flow.checkpoint("create_match_found_view")
            # Step 2: Create match found view
            match_view = MatchFoundView(match_result, is_player1)
            
            # Step 3: Generate the match embed
            loop = asyncio.get_running_loop()
            embed = await loop.run_in_executor(None, match_view.get_embed)
            flow.checkpoint("generate_match_embed_complete")
            
            # Step 4: Send a new message with the match view
            flow.checkpoint("send_new_match_message")
            new_match_message = await queue_channel_send(self.channel, embed=embed, view=match_view)
            flow.checkpoint("new_match_message_sent")
            
            # Step 5: Update the match view with the new message's ID and channel
            match_view.channel = new_match_message.channel
            match_view.original_message_id = new_match_message.id
            
            # Register for replay detection
            await match_view.register_for_replay_detection(self.last_interaction.channel_id)
            
            flow.checkpoint("update_match_view_complete")
            print(f"[Match Notification] Successfully displayed match view for player {self.player.discord_user_id}")
            
            flow.checkpoint("cleanup_start")
            # Clean up
            await queue_searching_view_manager.unregister(self.player.discord_user_id, view=self)
            flow.checkpoint("cleanup_complete")
            
            flow.complete("match_displayed_successfully")
            
        finally:
            # Always unsubscribe when done, even if an error occurred
            await notification_service.unsubscribe(self.player.discord_user_id)

    async def on_timeout(self):
        """Handle view timeout"""
        # Reset player state when queue times out
        # BUT: Don't clobber match states if player already got matched
        from src.backend.services.app_context import data_access_service
        current_state = data_access_service.get_player_state(self.player.discord_user_id)
        if not current_state.startswith("in_match:"):
            await data_access_service.set_player_state(self.player.discord_user_id, "idle")
        
        # Also remove from matchmaker
        await matchmaker.remove_player(self.player.discord_user_id)
        
        # Clean up notification subscription
        await notification_service.unsubscribe(self.player.discord_user_id)
        
        # Cancel the match listener task
        if self.match_task:
            self.match_task.cancel()
        
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

        # Proceed with cancelling the queue entry
        print(f"🚪 Removing player from matchmaker: {self.player.user_id}")
        await matchmaker.remove_player(self.player.discord_user_id)
        
        # Reset player state to idle
        # BUT: Don't clobber match states if player already got matched
        from src.backend.services.app_context import data_access_service
        current_state = data_access_service.get_player_state(self.player.discord_user_id)
        if not current_state.startswith("in_match:"):
            await data_access_service.set_player_state(self.player.discord_user_id, "idle")
        
        # Clean up the notification subscription and cancel the listener task
        await notification_service.unsubscribe(self.player.discord_user_id)
        
        # Stop the searching view's match listener task
        if isinstance(parent_view, QueueSearchingView) and parent_view.match_task:
            parent_view.match_task.cancel()
            parent_view.deactivate()
        
        await queue_searching_view_manager.unregister(self.player.discord_user_id, view=parent_view)
        
        # Return to the original queue view with its embed
        await queue_interaction_edit(
            interaction,
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
    """
    Handle when a match is found - publish via notification service.
    
    This callback is invoked by the matchmaker when a match is created.
    It uses the notification service to instantly push the result to both players.
    """
    print(f"🎉 Match #{match_result.match_id}: {match_result.player_1_user_id} vs {match_result.player_2_user_id} | {match_result.map_choice} @ {match_result.server_choice}")
    
    # Attach the register callback so views can subscribe to completion notifications
    setattr(match_result, 'register_completion_callback', register_completion_callback)
    
    # Publish match notification immediately via the notification service
    # This triggers instant push-based notifications to both players
    asyncio.create_task(notification_service.publish_match_found(match_result))


# Set the match callback
matchmaker.set_match_callback(handle_match_result)

class MatchFoundView(discord.ui.View):
    """View shown when a match is found"""
    
    def __init__(self, match_result: MatchResult, is_player1: bool):
        super().__init__(timeout=3600)  # 1-hour timeout for the view
        self.match_result = match_result
        self.is_player1 = is_player1
        self.selected_result = match_result.match_result
        self.confirmation_status = match_result.match_result_confirmation_status
        self.edit_lock = asyncio.Lock()
        self.confirmation_window_closed = False
        
        # Message tracking - initialized to None, set externally after message is sent
        self.channel: Optional[discord.TextChannel] = None
        self.original_message_id: Optional[int] = None

        # Performance tracking
        self.view_creation_time = time.time()
        
        # Register this view's notification handler with the backend
        if hasattr(match_result, "register_completion_callback"):
            match_result.register_completion_callback(self.handle_completion_notification)

        # Add match result reporting dropdown (moved to row 0)
        self.result_select = MatchResultSelect(match_result, is_player1, self)
        self.add_item(self.result_select)
        
        # Add confirm button (moved to row 0, before abort button)
        self.confirm_button = MatchConfirmButton(self)
        self.add_item(self.confirm_button)
        
        # Add abort button (moved to row 0)
        self.abort_button = MatchAbortButton(self)
        self.add_item(self.abort_button)

        # Add confirmation dropdown
        self.confirm_select = MatchResultConfirmSelect(self)
        self.add_item(self.confirm_select)

        # The abort deadline is for display purposes only now
        self.abort_deadline = get_current_unix_timestamp() + matchmaker.ABORT_TIMER_SECONDS

        # Update dropdown states based on initial data
        self._update_dropdown_states()
    
    async def _edit_original_message(self, embed: discord.Embed, view: discord.ui.View = None) -> bool:
        """
        Edit the original match message using the stored message ID.
        This uses the bot's permanent token, not the temporary interaction token.
        
        Returns True if successful, False otherwise.
        """
        if not self.channel or not self.original_message_id:
            return False
        
        try:
            # Fetch the original message by ID using the bot's permanent token
            message = await self.channel.fetch_message(self.original_message_id)
            
            # Edit it using the bot's permanent token (never expires!)
            await queue_message_edit(message, embed=embed, view=view or self)
            return True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            print(f"Failed to edit original message: {e}")
            return False
    
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
        import time
        from src.backend.services.app_context import leaderboard_service
        start_time = time.perf_counter()
        
        # Get player 1 info from DataAccessService (sub-millisecond, in-memory)
        checkpoint1 = time.perf_counter()
        from src.backend.services.data_access_service import DataAccessService
        data_service = DataAccessService()
        p1_info = data_service.get_player_info(self.match_result.player_1_discord_id)
        
        p1_name = p1_info.get('player_name') if p1_info else None
        p1_country = p1_info.get('country') if p1_info else None
        p1_display_name = p1_name if p1_name else str(self.match_result.player_1_discord_id)
        p1_flag = get_flag_emote(p1_country) if p1_country else get_flag_emote("XX")
        
        # Get player 2 info from DataAccessService (sub-millisecond, in-memory)
        p2_info = data_service.get_player_info(self.match_result.player_2_discord_id)
        
        checkpoint2 = time.perf_counter()
        print(f"⏱️ [MatchEmbed PERF] Player info lookup: {(checkpoint2-checkpoint1)*1000:.2f}ms")
        
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
        
        checkpoint3 = time.perf_counter()
        # Use cached ranks from MatchResult (no dynamic calculation needed)
        p1_rank = self.match_result.player_1_rank or "u_rank"
        p2_rank = self.match_result.player_2_rank or "u_rank"
        checkpoint4 = time.perf_counter()
        print(f"  [MatchEmbed PERF] Rank lookup: {(checkpoint4-checkpoint3)*1000:.2f}ms")
        
        # Get rank emotes
        p1_rank_emote = get_rank_emote(p1_rank)
        p2_rank_emote = get_rank_emote(p2_rank)
        
        checkpoint5 = time.perf_counter()
        # Get MMR values from DataAccessService (in-memory, sub-millisecond)
        p1_mmr, p2_mmr = data_service.get_match_mmrs(self.match_result.match_id)
        checkpoint6 = time.perf_counter()
        print(f"  [MatchEmbed PERF] Match data lookup: {(checkpoint6-checkpoint5)*1000:.2f}ms")
        
        # Create title with new format: rank, flag, race, name, MMR
        title = f"Match #{self.match_result.match_id}:\n{p1_rank_emote} {p1_flag} {p1_race_emote} {p1_display_name} ({p1_mmr}) vs {p2_rank_emote} {p2_flag} {p2_race_emote} {p2_display_name} ({p2_mmr})"
        
        # Get race names for display using races service
        p1_race_name = race_service.get_race_name(p1_race)
        p2_race_name = race_service.get_race_name(p2_race)
        
        # Get server information with region using regions service
        server_display = regions_service.format_server_with_region(self.match_result.server_choice)

        # Build player information with alt IDs and rank letters: rank, flag, race, name, race_name
        p1_info_line = f"- {p1_rank_emote} {p1_flag} {p1_race_emote} {p1_display_name} ({p1_race_name})"
        p2_info_line = f"- {p2_rank_emote} {p2_flag} {p2_race_emote} {p2_display_name} ({p2_race_name})"

        if p1_info:
            alt_ids_1 = []
            if p1_info.get('alt_player_name_1'):
                alt_ids_1.append(p1_info.get('alt_player_name_1'))
            if p1_info.get('alt_player_name_2'):
                alt_ids_1.append(p1_info.get('alt_player_name_2'))
            if alt_ids_1:
                p1_info_line += f"\n  - (a.k.a. {', '.join(alt_ids_1)})"
        if p2_info:
            alt_ids_2 = []
            if p2_info.get('alt_player_name_1'):
                alt_ids_2.append(p2_info.get('alt_player_name_1'))
            if p2_info.get('alt_player_name_2'):
                alt_ids_2.append(p2_info.get('alt_player_name_2'))
            if alt_ids_2:
                p2_info_line += f"\n  - (a.k.a. {', '.join(alt_ids_2)})"

        embed = discord.Embed(
            title=title,
            description="",  # Empty description as requested
            color=discord.Color.teal()
        )

        embed.add_field(name="\u3164", value="\u3164", inline=False)
        
        # Player Information section
        embed.add_field(
            name="**👥 Player Information:**",
            value=f"{p1_info_line}\n{p2_info_line}",
            inline=False
        )
        
        # Match Information section
        map_name = self.match_result.map_choice
        
        # Determine map link based on server region
        map_link: Optional[str] = None
        server_code = self.match_result.server_choice
        if server_code:
            region_info = regions_service.get_game_region_for_server(server_code)
            if region_info:
                region_name = region_info["name"].lower()
                if "americas" in region_name:
                    map_link = maps_service.get_map_battlenet_link(map_name, "americas")
                elif "europe" in region_name:
                    map_link = maps_service.get_map_battlenet_link(map_name, "europe")
                elif "asia" in region_name:
                    map_link = maps_service.get_map_battlenet_link(map_name, "asia")

        if not map_link:
            # Fallback to Americas link if specific region not available
            map_link = maps_service.get_map_battlenet_link(map_name, "americas")

        map_author = maps_service.get_map_author(map_name)
        map_link_display = map_link if map_link else "Unavailable"
        
        embed.add_field(
            name="**🌐 Match Information and Settings:**",
            value=(
                f"- Map: `{map_name}`\n"
                f"  - Map Link: `{map_link_display}`\n"
                f"  - Author: `{map_author}`"
            ),
            inline=False
        )

        embed.add_field(
            name="",
            value=(
                f"- Server: `{server_display}`\n"
                f"- In-Game Channel: `{self.match_result.in_game_channel}`\n"
                f"- Locked Alliances: `{EXPECTED_LOCKED_ALLIANCES}`"
            ),
            inline=True
        )

        embed.add_field(
            name="",
            value=(
                f"- Game Privacy: `{EXPECTED_GAME_PRIVACY}`\n"
                f"- Game Speed: `{EXPECTED_GAME_SPEED}`\n"
                f"- Game Duration: `{EXPECTED_GAME_DURATION}`"
            ),
            inline=True
        )

        embed.add_field(name="", value="", inline=False)
        

        # Match Result section
        
        if self.match_result.match_result == 'conflict':
            result_display = "Conflict"
            mmr_display = "- MMR Awarded: :x: Report Conflict Detected"
        elif self.match_result.match_result == 'aborted':
            result_display = "Aborted"
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
            name="**📊 Match Result:**",
            value= (
                f"- Result: `{result_display}`\n"
                f"{mmr_display}"
            ),
            inline=True
        )
        
        # Replay section
        replay_status_value = (
            f"- Replay Uploaded: `{self.match_result.replay_uploaded}`\n"
            f"- Replay Uploaded At: {format_discord_timestamp(self.match_result.replay_upload_time)}"
            if self.match_result.replay_uploaded == "Yes"
            else f"- Replay Uploaded: `{self.match_result.replay_uploaded}`"
        )
        embed.add_field(name="**🎞️ Replay Status:**", value=replay_status_value, inline=True)

        # Abort validity section
        # Get abort timer deadline (current time + ABORT_TIMER_SECONDS)
        current_time = get_current_unix_timestamp()
        
        checkpoint7 = time.perf_counter()
        # Get remaining aborts for both players
        p1_aborts = user_info_service.get_remaining_aborts(self.match_result.player_1_discord_id)
        p2_aborts = user_info_service.get_remaining_aborts(self.match_result.player_2_discord_id)
        checkpoint8 = time.perf_counter()
        print(f"  [MatchEmbed PERF] Abort count lookup: {(checkpoint8-checkpoint7)*1000:.2f}ms")
        
        embed.add_field(name="\u3164", value="\u3164", inline=False)

        abort_validity_value = (
            f"You can use the 🛑 **Abort Match** button if you are unable to play.\n"
            f"Aborting matches has no MMR penalty, but you have a limited number per month.\n" 
            f"**Abusing this feature (e.g., dodging matchups/opponents, repeatedly aborting at "
            f"the last second, wasting the time of others, etc.) will result in a BAN.**\n"
            f"You can only abort the match before <t:{self.abort_deadline}:T> (<t:{self.abort_deadline}:R>)."
        )
        embed.add_field(name="**💨 Can't play? Need to leave? Abort the match!**", value=abort_validity_value, inline=False)

        embed.add_field(name="\u3164", value="\u3164", inline=False)

        embed.add_field(
            name="⚠️ YOU MUST CONFIRM THE MATCH BELOW, BEFORE IT STARTS! ⚠️",
            value=(
                f"Press ✅ **Confirm Match** as soon as you see this. "
                f"This tells the system you are here and ready to play. "
                f"If you do not confirm, you will automatically be dropped from the match by <t:{self.abort_deadline}:T> (<t:{self.abort_deadline}:R>). "
                f"**Dropping too many matches will result in a BAN.**"
            ),
            inline=True
        )
    
        embed.add_field(name="**ℹ️ To report the match result, upload a replay.**", value="The dropdown menus below will unlock and allow you to report the match result, once you upload a replay.", inline=True)

        total_time = (time.perf_counter() - start_time) * 1000
        if total_time > 100:
            print(f"⚠️ [ME] Total:{total_time:.1f}ms")
        elif total_time > 50:
            print(f"🟡 [ME] Total:{total_time:.1f}ms")
        
        return embed

    async def register_for_replay_detection(self, channel_id: int):
        """Register this view to receive replay file uploads"""
        self.channel_id = channel_id
        await match_found_view_manager.register(
            self.match_result.match_id, channel_id, self
        )
    
    async def handle_completion_notification(self, status: str, data: dict):
        """This is the callback that the backend will invoke."""
        print(f"📬 [DEBUG] MatchFoundView.handle_completion_notification RECEIVED: status={status}, match_id={self.match_result.match_id}, data_keys={list(data.keys())}")
        flow = FlowTracker(f"match_completion_notification_{status}", 
                          user_id=self.match_result.player_1_discord_id if self.is_player1 else self.match_result.player_2_discord_id)
        
        flow.checkpoint("notification_received")
        
        if status == "complete":
            print(f"📬 [DEBUG] Processing 'complete' status for match {self.match_result.match_id}")
            flow.checkpoint("process_complete_status")
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
            
            flow.checkpoint("disable_components")
            # Disable components and update the original embed
            self.disable_all_components()
            
            flow.checkpoint("update_embed_start")
            async with self.edit_lock:
                # Edit the original message using bot token (never expires!)
                embed = self.get_embed()
                await self._edit_original_message(embed, self)
            flow.checkpoint("update_embed_complete")
            
            flow.checkpoint("send_final_embed_start")
            # Send the final gold embed as a follow-up
            await self._send_final_notification_embed(data)
            flow.checkpoint("send_final_embed_complete")
            
            # The view's work is done for a completed match
            self.stop()
            flow.complete("success")
            
        elif status == "abort":
            print(f"📬 [DEBUG] Processing 'abort' status for match {self.match_result.match_id}")
            flow.checkpoint("process_abort_status")
            # Update the view's internal state to reflect the abort
            self.match_result.match_result = "aborted"
            self.match_result.match_result_confirmation_status = "Aborted"
            print(f"📬 [DEBUG] Updated match_result to 'aborted' for match {self.match_result.match_id}")

            flow.checkpoint("disable_components")
            # Immediately disable all components to prevent further actions
            self.disable_all_components()
            print(f"📬 [DEBUG] Disabled all components for match {self.match_result.match_id}")

            flow.checkpoint("update_abort_embed_start")
            # Update the embed with the abort information using bot token (persistent)
            async with self.edit_lock:
                embed = self.get_embed()
                await self._edit_original_message(embed, self)
            print(f"📬 [DEBUG] Updated embed with abort info for match {self.match_result.match_id}")
            flow.checkpoint("update_abort_embed_complete")

            flow.checkpoint("send_abort_embed_start")
            # Send a follow-up notification to ensure the user sees the final state
            # Pass the report codes from the data payload
            print(f"📬 [DEBUG] About to send abort notification embed for match {self.match_result.match_id}")
            await self._send_abort_notification_embed(
                p1_report=data.get('p1_report'),
                p2_report=data.get('p2_report')
            )
            print(f"📬 [DEBUG] Abort notification embed sent for match {self.match_result.match_id}")
            flow.checkpoint("send_abort_embed_complete")
            
            # The view's work is done for an aborted match
            self.stop()
            flow.complete("success")
            
        elif status == "conflict":
            print(f"📬 [DEBUG] Processing 'conflict' status for match {self.match_result.match_id}")
            flow.checkpoint("process_conflict_status")
            # Update the view's state to reflect the conflict
            self.match_result.match_result = "conflict"
            
            flow.checkpoint("disable_components")
            # Disable components and update the original embed
            self.disable_all_components()
            
            flow.checkpoint("update_conflict_embed_start")
            async with self.edit_lock:
                embed = self.get_embed()
                await self._edit_original_message(embed, self)
            flow.checkpoint("update_conflict_embed_complete")

            flow.checkpoint("send_conflict_embed_start")
            # Send the conflict embed as a follow-up
            await self._send_conflict_notification_embed()
            flow.checkpoint("send_conflict_embed_complete")
            
            # The view's work is done for a conflict
            self.stop()
            flow.complete("success")

        elif status == "confirmation_timeout":
            flow.checkpoint("process_confirmation_timeout")
            # The backend has confirmed the confirmation window is closed.
            # Disable the abort and confirm buttons.
            self.abort_button.disabled = True
            self.confirm_button.disabled = True
            self.confirmation_window_closed = True
            
            flow.checkpoint("update_timeout_embed_start")
            # Update the embed to show the abort window is closed
            async with self.edit_lock:
                embed = self.get_embed()
                await self._edit_original_message(embed, self)
            print(f"📬 [DEBUG] Updated embed to show timeout for match {self.match_result.match_id}")
            flow.checkpoint("update_timeout_embed_complete")
            print(f"📬 [DEBUG] 'confirmation_timeout' processing COMPLETE for match {self.match_result.match_id}")
            flow.complete("success")
            
        # The view's work is done
        self.stop()
        
    async def _send_final_notification_embed(self, final_results: dict):
        """Creates and sends the final gold embed notification."""
        if not self.channel:
            return

        p1_info = final_results['p1_info']
        p2_info = final_results['p2_info']
        p1_name = final_results['p1_name']
        p2_name = final_results['p2_name']

        p1_flag = get_flag_emote(p1_info['country'])
        p2_flag = get_flag_emote(p2_info['country'])
        p1_race = final_results['p1_race']
        p2_race = final_results['p2_race']
        p1_race_emote = get_race_emote(p1_race)
        p2_race_emote = get_race_emote(p2_race)

        # Get rank emotes for both players
        from src.backend.services.app_context import ranking_service
        
        p1_rank = ranking_service.get_letter_rank(final_results['player_1_discord_uid'], p1_race)
        p2_rank = ranking_service.get_letter_rank(final_results['player_2_discord_uid'], p2_race)
        
        p1_rank_emote = get_rank_emote(p1_rank)
        p2_rank_emote = get_rank_emote(p2_rank)

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
            description=f"**{p1_rank_emote} {p1_flag} {p1_race_emote} {p1_name} ({int(p1_current_mmr)} → {int(p1_new_mmr)})** vs **{p2_rank_emote} {p2_flag} {p2_race_emote} {p2_name} ({int(p2_current_mmr)} → {int(p2_new_mmr)})**",
            color=discord.Color.gold()
        )

        p1_sign = "+" if p1_mmr_rounded >= 0 else ""
        p2_sign = "+" if p2_mmr_rounded >= 0 else ""

        # Build dynamic result field based on match outcome
        match_result_raw = final_results['match_result_raw']
        if match_result_raw == 1:
            # Player 1 won
            result_value = f"🏆 **{p1_rank_emote} {p1_flag} {p1_race_emote} {p1_name}**"
        elif match_result_raw == 2:
            # Player 2 won
            result_value = f"🏆 **{p2_rank_emote} {p2_flag} {p2_race_emote} {p2_name}**"
        elif match_result_raw == 0:
            # Draw
            result_value = f"⚖️ **Draw**"
        else:
            # Aborted or Conflict
            result_value = final_results['result_text']

        notification_embed.add_field(name="", value="\u3164", inline=False)

        notification_embed.add_field(
            name="**Result:**",
            value=result_value,
            inline=True
        )

        notification_embed.add_field(
            name="**MMR Changes:**",
            value=f"- {p1_name}: `{p1_sign}{p1_mmr_rounded} ({int(p1_current_mmr)} → {int(p1_new_mmr)})`\n- {p2_name}: `{p2_sign}{p2_mmr_rounded} ({int(p2_current_mmr)} → {int(p2_new_mmr)})`",
            inline=True
        )
        
        try:
            await queue_channel_send(self.channel, embed=notification_embed)
        except discord.HTTPException as e:
            print(f"Error sending final notification for match {self.match_result.match_id}: {e}")

    async def _send_conflict_notification_embed(self):
        """Sends a rich follow-up message indicating a match conflict with full details."""
        if not self.channel:
            return
        
        # Get match data from DataAccessService (in-memory, instant)
        from src.backend.services.data_access_service import DataAccessService
        data_service = DataAccessService()
        match_data = data_service.get_match(self.match_result.match_id)
        if not match_data:
            print(f"❌ [DEBUG] Match {self.match_result.match_id} not found in DataAccessService for conflict notification")
            return
        
        p1_uid = match_data['player_1_discord_uid']
        p2_uid = match_data['player_2_discord_uid']
        p1_info = data_service.get_player_info(p1_uid)
        p2_info = data_service.get_player_info(p2_uid)
        
        p1_name = p1_info.get('player_name') if p1_info else str(p1_uid)
        p2_name = p2_info.get('player_name') if p2_info else str(p2_uid)
        
        p1_report = match_data.get("player_1_report")
        p2_report = match_data.get("player_2_report")
        
        # Get visual elements
        p1_flag = get_flag_emote(p1_info['country']) if p1_info else '🏳️'
        p2_flag = get_flag_emote(p2_info['country']) if p2_info else '🏳️'
        p1_race = match_data.get('player_1_race')
        p2_race = match_data.get('player_2_race')
        p1_race_emote = get_race_emote(p1_race)
        p2_race_emote = get_race_emote(p2_race)
        
        # Get rank emotes for both players
        from src.backend.services.app_context import ranking_service
        
        p1_rank = ranking_service.get_letter_rank(p1_uid, p1_race)
        p2_rank = ranking_service.get_letter_rank(p2_uid, p2_race)
        
        p1_rank_emote = get_rank_emote(p1_rank)
        p2_rank_emote = get_rank_emote(p2_rank)
        
        p1_current_mmr = match_data['player_1_mmr']
        p2_current_mmr = match_data['player_2_mmr']
        map_name = match_data.get('map_name', 'Unknown')
        
        # Decode what each player reported
        # Report codes: 1 = Player 1 won, 2 = Player 2 won, 0 = Draw, -3 = Abort, -4 = No response
        def decode_report(report_code: int, p1_name: str, p2_name: str) -> str:
            if report_code == 1:
                return f"{p1_name} won"
            elif report_code == 2:
                return f"{p2_name} won"
            elif report_code == 0:
                return "Draw"
            elif report_code == -3:
                return "Abort"
            elif report_code == -4:
                return "No response"
            else:
                return f"Unknown ({report_code})"
        
        p1_reported = decode_report(p1_report, p1_name, p2_name) if p1_report is not None else "No response"
        p2_reported = decode_report(p2_report, p1_name, p2_name) if p2_report is not None else "No response"
        
        conflict_embed = discord.Embed(
            title=f"⚠️ Match #{self.match_result.match_id} Result Conflict",
            description=f"**{p1_rank_emote} {p1_flag} {p1_race_emote} {p1_name} ({int(p1_current_mmr)})** vs **{p2_rank_emote} {p2_flag} {p2_race_emote} {p2_name} ({int(p2_current_mmr)})**",
            color=discord.Color.orange()
        )
        
        conflict_embed.add_field(
            name="**Map:**",
            value=map_name,
            inline=False
        )
        
        conflict_embed.add_field(
            name="**Reported Results:**",
            value=f"- {p1_name}: **{p1_reported}**\n- {p2_name}: **{p2_reported}**",
            inline=False
        )
        
        conflict_embed.add_field(
            name="**MMR Changes:**",
            value=f"- {p1_name}: `+0 ({int(p1_current_mmr)})`\n- {p2_name}: `+0 ({int(p2_current_mmr)})`",
            inline=False
        )
        
        conflict_embed.add_field(
            name="**Status:**",
            value="⚠️ The reported results do not agree. **No MMR changes have been applied.**\n\nPlease contact an administrator to resolve this dispute.",
            inline=False
        )
        
        try:
            await queue_channel_send(self.channel, embed=conflict_embed)
        except discord.HTTPException as e:
            print(f"Error sending conflict notification for match {self.match_result.match_id}: {e}")

    async def _send_abort_notification_embed(self, p1_report: Optional[int] = None, p2_report: Optional[int] = None):
        """
        Sends a follow-up message indicating the match was aborted.
        
        Args:
            p1_report: Player 1's report code (optional, will be fetched if not provided)
            p2_report: Player 2's report code (optional, will be fetched if not provided)
        """
        print(f"📨 [DEBUG] _send_abort_notification_embed START for match {self.match_result.match_id}, p1_report={p1_report}, p2_report={p2_report}")
        if not self.channel:
            print(f"❌ [DEBUG] No channel available, cannot send abort notification for match {self.match_result.match_id}")
            return

        # Get match data from DataAccessService (in-memory, instant)
        from src.backend.services.data_access_service import DataAccessService
        data_service = DataAccessService()
        match_data = data_service.get_match(self.match_result.match_id)
        if not match_data:
            print(f"❌ [DEBUG] Match {self.match_result.match_id} not found in DataAccessService")
            raise ValueError(f"[MatchFoundView] Match {self.match_result.match_id} not found in DataAccessService memory")

        print(f"📨 [DEBUG] Got match data for match {self.match_result.match_id}")

        p1_info = data_service.get_player_info(match_data['player_1_discord_uid'])
        p2_info = data_service.get_player_info(match_data['player_2_discord_uid'])

        p1_name = p1_info.get('player_name') if p1_info else str(match_data['player_1_discord_uid'])
        p2_name = p2_info.get('player_name') if p2_info else str(match_data['player_2_discord_uid'])

        # Use provided report codes or fetch from match data
        if p1_report is None:
            p1_report = match_data.get("player_1_report")
        if p2_report is None:
            p2_report = match_data.get("player_2_report")

        print(f"📨 [DEBUG] Report codes (final): p1={p1_report}, p2={p2_report}")

        aborted_by = "Unknown"
        reason = "The match was aborted. No MMR changes were applied."

        # Determine the specific abort reason based on report codes
        if p1_report == -4 and p2_report == -4:
            aborted_by = "System"
            reason = "The match was automatically aborted because neither player confirmed in time."
        elif p1_report == -4 and p2_report is None:
            aborted_by = "System"
            reason = f"The match was automatically aborted because **{p1_name}** did not confirm in time."
        elif p2_report == -4 and p1_report is None:
            aborted_by = "System"
            reason = f"The match was automatically aborted because **{p2_name}** did not confirm in time."
        elif p1_report == -4:
            aborted_by = "System"
            reason = f"The match was automatically aborted because **{p1_name}** did not confirm in time."
        elif p2_report == -4:
            aborted_by = "System"
            reason = f"The match was automatically aborted because **{p2_name}** did not confirm in time."
        elif p1_report == -3:
            aborted_by = p1_name
            reason = f"The match was aborted by **{aborted_by}**. No MMR changes were applied."
        elif p2_report == -3:
            aborted_by = p2_name
            reason = f"The match was aborted by **{aborted_by}**. No MMR changes were applied."

        print(f"📨 [DEBUG] Abort reason determined: {reason}")
            
        p1_flag = get_flag_emote(p1_info['country']) if p1_info else '🏳️'
        p2_flag = get_flag_emote(p2_info['country']) if p2_info else '🏳️'
        p1_race = match_data.get('player_1_race')
        p2_race = match_data.get('player_2_race')
        p1_race_emote = get_race_emote(p1_race)
        p2_race_emote = get_race_emote(p2_race)

        # Get rank emotes for both players
        from src.backend.services.app_context import ranking_service
        
        p1_rank = ranking_service.get_letter_rank(match_data['player_1_discord_uid'], p1_race)
        p2_rank = ranking_service.get_letter_rank(match_data['player_2_discord_uid'], p2_race)
        
        p1_rank_emote = get_rank_emote(p1_rank)
        p2_rank_emote = get_rank_emote(p2_rank)

        p1_current_mmr = match_data['player_1_mmr']
        p2_current_mmr = match_data['player_2_mmr']

        abort_embed = discord.Embed(
            title=f"🛑 Match #{self.match_result.match_id} Aborted",
            description=f"**{p1_rank_emote} {p1_flag} {p1_race_emote} {p1_name} ({int(p1_current_mmr)})** vs **{p2_rank_emote} {p2_flag} {p2_race_emote} {p2_name} ({int(p2_current_mmr)})**",
            color=discord.Color.red()
        )

        abort_embed.add_field(
            name="**MMR Changes:**",
            value=f"- {p1_name}: `+0 ({int(p1_current_mmr)})`\n- {p2_name}: `+0 ({int(p2_current_mmr)})`",
            inline=False
        )
        
        abort_embed.add_field(
            name="**Reason:**",
            value=reason,
            inline=False
        )

        try:
            print(f"📨 [DEBUG] Sending abort embed to channel for match {self.match_result.match_id}")
            await queue_channel_send(self.channel, embed=abort_embed)
            print(f"✅ [DEBUG] Abort notification embed successfully sent for match {self.match_result.match_id}")
        except discord.HTTPException as e:
            print(f"❌ [DEBUG] Error sending abort notification for match {self.match_result.match_id}: {e}")
            print(f"Error sending abort notification for match {self.match_result.match_id}: {e}")

    def disable_all_components(self):
        """Disables all components in the view."""
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

    async def on_timeout(self):
        pass # Timeout is now handled by the match completion service


class MatchConfirmButton(discord.ui.Button):
    """Button to confirm the match"""
    
    def __init__(self, parent_view):
        self.parent_view = parent_view
        
        super().__init__(
            emoji="✅",
            label="Confirm Match",
            style=discord.ButtonStyle.green,
            row=0,
            disabled=False
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle the confirm match button click."""
        player_discord_uid = interaction.user.id
        match_id = self.parent_view.match_result.match_id
        
        # Immediately defer the response
        await queue_interaction_defer(interaction)
        
        # Call the backend to record the confirmation
        from src.backend.services.app_context import match_completion_service
        
        try:
            await match_completion_service.confirm_match(match_id, player_discord_uid)
            
            # Disable the confirm and abort buttons and update the view
            self.disabled = True
            self.parent_view.abort_button.disabled = True
            self.style = discord.ButtonStyle.secondary
            async with self.parent_view.edit_lock:
                # We must re-supply the embed, otherwise it will be removed
                current_embed = self.parent_view.get_embed()
                await queue_edit_original(interaction, embed=current_embed, view=self.parent_view)
            
            # Provide feedback to the user
            await queue_followup(
                interaction,
                content="✅ You have confirmed the match! Waiting for your opponent.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error confirming match {match_id} for player {player_discord_uid}: {e}")
            await queue_followup(
                interaction,
                content="❌ An error occurred while confirming the match. Please try again.",
                ephemeral=True
            )


class MatchAbortButton(discord.ui.Button):
    """Button to abort the match"""
    
    def __init__(self, parent_view):
        self.parent_view = parent_view
        self.awaiting_confirmation = False  # Track confirmation state
        self.first_click_time = None  # Track timing
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
            style=discord.ButtonStyle.secondary,
            row=0,
            disabled=is_disabled
        )
    
    async def callback(self, interaction: discord.Interaction):
        flow = FlowTracker(f"match_abort", user_id=interaction.user.id)
        player_discord_uid = interaction.user.id
        
        flow.checkpoint("check_confirmation_state")
        # If not yet in confirmation state, show confirmation prompt
        if not self.awaiting_confirmation:
            self.first_click_time = time.time()
            flow.checkpoint("show_confirmation_prompt")
            remaining_aborts = user_info_service.get_remaining_aborts(player_discord_uid)
            self.label = f"Confirm Abort ({remaining_aborts} remaining)"
            self.style = discord.ButtonStyle.danger  # Keep danger style
            self.awaiting_confirmation = True
            
            flow.checkpoint("update_button_ui_start")
            # Update the view to show the confirmation button
            async with self.parent_view.edit_lock:
                await queue_interaction_edit(
                    interaction,
                    embed=self.parent_view.get_embed(),
                    view=self.parent_view
                )
            flow.checkpoint("update_button_ui_complete")
            flow.complete("awaiting_confirmation")
            return
        
        # If already in confirmation state, proceed with abort
        if self.first_click_time:
            time_to_confirm = time.time() - self.first_click_time
            print(f"⏱️ [Abort PERF] Time between first click and confirmation: {time_to_confirm*1000:.2f}ms")
        
        flow.checkpoint("execute_abort_start")
        # Atomically abort the match
        success = await matchmaker.abort_match(
            self.parent_view.match_result.match_id,
            player_discord_uid
        )
        flow.checkpoint("execute_abort_complete")
        
        if success:
            flow.checkpoint("abort_succeeded")
            # The backend will now handle notifications.
            # We just need to update the UI to a disabled state.
            
            flow.checkpoint("update_ui_start")
            # Update button label
            remaining_aborts = user_info_service.get_remaining_aborts(player_discord_uid)
            self.label = f"Match Aborted ({remaining_aborts} left this month)"

            self.parent_view.disable_all_components()
            
            flow.checkpoint("send_abort_ui_update")
            # Update the embed to show abort status temporarily
            # The backend will send the final authoritative state
            async with self.parent_view.edit_lock:
                await queue_interaction_edit(
                    interaction,
                    embed=self.parent_view.get_embed(), 
                    view=self.parent_view
                )
            flow.checkpoint("send_abort_ui_complete")
            flow.complete("success")
        else:
            flow.complete("abort_failed")
            await queue_interaction_response(interaction, content="❌ Failed to abort match. It might have been already completed or aborted by the other player.")


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
        flow = FlowTracker(f"confirm_match_result", user_id=interaction.user.id)
        
        flow.checkpoint("update_confirmation_status")
        # Persist the confirmation status
        self.parent_view.match_result.match_result_confirmation_status = "Confirmed"
        
        flow.checkpoint("update_ui_state")
        # Set the selected option as default for persistence
        for option in self.options:
            option.default = (option.value == self.values[0])
        
        # Disable both dropdowns and abort button after confirmation
        self.parent_view.result_select.disabled = True
        self.parent_view.confirm_select.disabled = True
        self.parent_view.abort_button.disabled = True
        self.parent_view.last_interaction = interaction

        flow.checkpoint("update_discord_message_start")
        # Update the message to show the final state before backend processing
        async with self.parent_view.edit_lock:
            await queue_interaction_edit(
                interaction,
                embed=self.parent_view.get_embed(), view=self.parent_view
            )
        flow.checkpoint("update_discord_message_complete")

        flow.checkpoint("record_player_report_start")
        # Now, send the report to the backend for final processing.
        # The completion handler will send the final embed update.
        await self.parent_view.result_select.record_player_report(
            self.parent_view.selected_result
        )
        flow.checkpoint("record_player_report_complete")
        
        flow.complete("success")


class MatchResultSelect(discord.ui.Select):
    """Dropdown for reporting match results"""
    
    def __init__(self, match_result: MatchResult, is_player1: bool, parent_view):
        self.match_result = match_result
        self.is_player1 = is_player1
        self.parent_view = parent_view
        
        # Get player names from DataAccessService (in-memory, instant)
        from src.backend.services.data_access_service import DataAccessService
        data_service = DataAccessService()
        p1_info = data_service.get_player_info(match_result.player_1_discord_id)
        self.p1_name = p1_info.get('player_name') if p1_info else str(match_result.player_1_user_id)
        
        p2_info = data_service.get_player_info(match_result.player_2_discord_id)
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
        flow = FlowTracker(f"select_match_result", user_id=interaction.user.id)
        
        flow.checkpoint("validate_replay_uploaded")
        # Check if replay is uploaded before allowing result selection
        if self.parent_view.match_result.replay_uploaded != "Yes":
            flow.complete("no_replay_uploaded")
            await queue_interaction_response(interaction, content="❌ Please upload a replay file before reporting match results.")
            return
        
        flow.checkpoint("store_selected_result")
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
        
        flow.checkpoint("update_confirmation_dropdown")
        # Enable and update confirmation dropdown
        self.parent_view.confirm_select.disabled = False
        self.parent_view.confirm_select.options = [
            discord.SelectOption(
                label=f"Confirm: {result_label}",
                value="confirm"
            )
        ]
        self.parent_view.confirm_select.placeholder = "Confirm your selection..."
        
        flow.checkpoint("update_message_start")
        # Update the message (DO NOT call _update_dropdown_states() as it would reset our changes)
        self.parent_view.last_interaction = interaction
        async with self.parent_view.edit_lock:
            await queue_interaction_edit(
                interaction,
                embed=self.parent_view.get_embed(), view=self.parent_view
            )
        flow.checkpoint("update_message_complete")
        flow.complete("success")
    
    async def record_player_report(self, result: str):
        """Record a player's individual report for the match"""
        import time
        start_time = time.perf_counter()
        
        # Convert result to report value format
        if result == "player1_win":
            report_value = 1
        elif result == "player2_win":
            report_value = 2
        else:
            report_value = 0
        
        try:
            current_player_id = self.parent_view.match_result.player_1_discord_id if self.is_player1 else self.parent_view.match_result.player_2_discord_id
            
            checkpoint1 = time.perf_counter()
            success = await matchmaker.record_match_result(self.match_result.match_id, current_player_id, report_value)
            checkpoint2 = time.perf_counter()
            
            duration_ms = (checkpoint2 - checkpoint1) * 1000
            db_time = duration_ms
            
            if success:
                print(f"📝 Player report recorded for match {self.match_result.match_id}. Waiting for backend notification.")
            else:
                print(f"❌ Failed to record player report for match {self.match_result.match_id}")
        except Exception as e:
            print(f"❌ Error recording player report: {e}")
        finally:
            total_time = (time.perf_counter() - start_time) * 1000
            
            # Compact performance logging
            print(f"[Report] DB:{db_time:.1f}ms Total:{total_time:.1f}ms")
    
    async def update_embed_with_mmr_changes(self):
        """Update the embed to show MMR changes"""
        try:
            # Update the original message with new embed
            if hasattr(self.parent_view, 'last_interaction') and self.parent_view.last_interaction:
                embed = self.parent_view.get_embed()
                await queue_edit_original(
                    self.parent_view.last_interaction,
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
                        await queue_edit_original(
                            other_view.last_interaction,
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
                        await queue_edit_original(
                            other_view.last_interaction,
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
            success = await matchmaker.record_match_result(self.match_result.match_id, current_player_id, report_value)
            
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
                await queue_edit_original(
                    self.parent_view.last_interaction,
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


async def store_replay_background(match_id: int, player_id: int, replay_bytes: bytes, replay_info: dict, channel):
    """Background task to store replay without blocking UI updates"""
    try:
        print(f"[Background] Starting replay storage for match {match_id} (player: {player_id})")
        
        # Use the async method for non-blocking database writes
        result = await replay_service.store_upload_from_parsed_dict_async(
            match_id,
            player_id,
            replay_bytes,
            replay_info
        )
        
        if result.get("success"):
            replay_data = result.get("replay_data")
            stored_match_id = result.get("match_id")
            
            if replay_data and stored_match_id:
                try:
                    # Await verification completion before sending message
                    verification_results = await match_completion_service.verify_replay_data(
                        match_id=stored_match_id,
                        replay_data=replay_data
                    )
                    
                    # Create and send the single, complete embed
                    final_embed = ReplayDetailsEmbed.get_success_embed(
                        replay_data=replay_data,
                        verification_results=verification_results
                    )
                    await queue_channel_send(channel, embed=final_embed)
                    
                except ValueError as e:
                    # Match not found in database
                    error_embed = discord.Embed(
                        title="❌ Verification Error",
                        description=f"Could not verify replay: {str(e)}",
                        color=discord.Color.red()
                    )
                    await queue_channel_send(channel, embed=error_embed)
                    print(f"❌ Verification error for match {stored_match_id}: {e}")
                    
                except Exception as e:
                    # Unexpected error during verification
                    error_embed = discord.Embed(
                        title="❌ Unexpected Error",
                        description="An error occurred while verifying the replay.",
                        color=discord.Color.red()
                    )
                    await queue_channel_send(channel, embed=error_embed)
                    print(f"❌ Unexpected verification error for match {stored_match_id}: {e}")
                    import traceback
                    traceback.print_exc()
            
            print(f"✅ Background replay storage completed for match {match_id} (player: {player_id})")
        else:
            error_message = result.get("error")
            print(f"❌ Background replay storage failed for match {match_id}: {error_message}")
            
    except Exception as e:
        print(f"❌ Background replay storage error for match {match_id}: {e}")
        import traceback
        traceback.print_exc()


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
    
    flow = FlowTracker(f"replay_upload", user_id=message.author.id)
    
    try:
        flow.checkpoint("download_replay_start")
        # Download the replay file
        replay_bytes = await replay_attachment.read()
        flow.checkpoint("download_replay_complete")
        
        print(f"[Main Process] Replay uploaded by {message.author.name} "
              f"(size: {len(replay_bytes)} bytes). Offloading to worker process...")
        
        flow.checkpoint("parse_replay_start")
        # --- MULTIPROCESSING INTEGRATION ---
        # Get the current asyncio event loop
        loop = asyncio.get_running_loop()
        
        # Offload the blocking parsing function to the process pool with timeout
        # Uses 2.5-second timeout (2s work + 0.5s IPC overhead)
        # Falls back to synchronous parsing if worker is unresponsive
        try:
            if bot and hasattr(bot, 'process_pool'):
                # Event-driven process pool health check
                # Only check when we actually need to use the pool
                try:
                    from src.backend.services.process_pool_health import ensure_process_pool_healthy
                    from src.backend.services.replay_parsing_timeout import parse_replay_with_timeout
                    from src.backend.services.memory_monitor import log_memory
                    
                    is_healthy = await ensure_process_pool_healthy()
                    if not is_healthy:
                        print("[WARN] Process pool health check failed, falling back to synchronous parsing")
                        replay_info = parse_replay_data_blocking(replay_bytes)
                        was_timeout = False
                    else:
                        # Track work start
                        if hasattr(bot, '_track_work_start'):
                            bot._track_work_start()
                        
                        # Log memory before replay parsing
                        log_memory("Before replay parse")
                        
                        try:
                            # Use timeout-aware parsing with 2.5s timeout
                            replay_info, was_timeout = await parse_replay_with_timeout(
                                bot.process_pool,
                                parse_replay_data_blocking,
                                replay_bytes,
                                timeout=2.5
                            )
                            
                            if was_timeout:
                                print("[WARN] Replay parsing timed out - worker may have crashed")
                                # Don't attempt pool restart here; let health check handle it
                        finally:
                            # Track work end
                            if hasattr(bot, '_track_work_end'):
                                bot._track_work_end()
                            
                            # Log memory after replay parsing
                            log_memory("After replay parse")
                except Exception as e:
                    print(f"[WARN] Process pool health check failed with error: {e}")
                    # Fallback to synchronous parsing
                    replay_info = parse_replay_data_blocking(replay_bytes)
                    was_timeout = False
            else:
                # Fallback to synchronous parsing if process pool is not available
                # This shouldn't happen in production, but provides a safety net
                print("[WARN] Process pool not available, falling back to synchronous parsing")
                replay_info = parse_replay_data_blocking(replay_bytes)
                was_timeout = False
                
        except Exception as e:
            # This will catch any exception from the worker process or parsing
            print(f"[FATAL] Replay parsing failed: {type(e).__name__}: {e}")
            flow.complete("parse_failed")
            error_embed = ReplayDetailsEmbed.get_error_embed(
                "A critical error occurred while parsing the replay. "
                "The file may be corrupted. Please notify an admin."
            )
            await queue_channel_send(message.channel, embed=error_embed)
            return
        
        flow.checkpoint("parse_replay_complete")
        print(f"[Main Process] Received result from worker process")
        
        flow.checkpoint("validate_replay_data")
        # Check if parsing failed
        if replay_info.get("error"):
            error_message = replay_info["error"]
            print(f"[Main Process] Worker process reported parsing error: {error_message}")
            
            flow.complete("validation_failed")
            # Send the red error embed
            error_embed = ReplayDetailsEmbed.get_error_embed(error_message)
            await queue_channel_send(message.channel, embed=error_embed)
            
            # Update the match view to show "Replay Invalid"
            match_view.match_result.replay_uploaded = "Replay Invalid"
            match_view._update_dropdown_states()
            
            # Edit the original message using bot token (never expires!)
            embed = match_view.get_embed()
            await match_view._edit_original_message(embed, match_view)
            
            print(f"❌ Failed to parse replay for match {match_view.match_result.match_id}: {error_message}")
            return
        
        # IMMEDIATE UI UPDATE - Don't wait for storage to complete
        flow.checkpoint("immediate_ui_update_start")
        unix_epoch = int(time.time())
        match_view.match_result.replay_uploaded = "Yes"
        match_view.match_result.replay_upload_time = unix_epoch
        
        # Update ONLY the view for the player who uploaded the replay
        # Each player should only see their own replay status
        match_view._update_dropdown_states()
        
        # FIX: Ensure abort button remains disabled if the confirmation window is closed
        if match_view.confirmation_window_closed:
            match_view.abort_button.disabled = True
            
        # Edit the original message using bot token (never expires!)
        embed = match_view.get_embed()
        await match_view._edit_original_message(embed, match_view)
        flow.checkpoint("immediate_ui_update_complete")
        
        # Start background storage task (non-blocking)
        flow.checkpoint("start_background_storage")
        asyncio.create_task(store_replay_background(
            match_view.match_result.match_id,
            message.author.id,
            replay_bytes,
            replay_info,
            message.channel
        ))
        
        print(f"✅ Replay upload UI updated immediately for match {match_view.match_result.match_id} (player: {message.author.id})")
        flow.complete("success")

    except Exception as e:
        flow.complete("error")
        print(f"❌ Error processing replay file: {e}")


