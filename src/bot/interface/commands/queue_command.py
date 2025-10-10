import asyncio
import json
import discord
from discord import app_commands
import os
from src.backend.services.races_service import RacesService
from src.backend.services.maps_service import MapsService
from src.backend.services.regions_service import RegionsService
from src.bot.interface.components.error_embed import ErrorEmbedException, create_error_view_from_exception
from src.bot.interface.components.confirm_restart_cancel_buttons import ConfirmRestartCancelButtons
from src.bot.interface.components.cancel_embed import create_cancel_embed
from src.backend.services.matchmaking_service import matchmaker, Player, QueuePreferences, MatchResult
from src.backend.services.user_info_service import get_user_info
from src.backend.db.db_reader_writer import DatabaseWriter, DatabaseReader
from src.bot.utils.discord_utils import send_ephemeral_response, get_current_unix_timestamp, format_discord_timestamp
from src.backend.services.command_guard_service import CommandGuardService, CommandGuardError
from src.backend.services.replay_service import ReplayService
from typing import Optional
import logging
import time

race_service = RacesService()
maps_service = MapsService()
db_writer = DatabaseWriter()
db_reader = DatabaseReader()
guard_service = CommandGuardService()
regions_service = RegionsService()

# Get global timeout from environment
GLOBAL_TIMEOUT = int(os.getenv('GLOBAL_TIMEOUT'))

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
    try:
        player = guard_service.ensure_player_record(interaction.user.id, interaction.user.name)
        guard_service.require_queue_access(player)
    except CommandGuardError as exc:
        error_embed = guard_service.create_error_embed(exc)
        await send_ephemeral_response(interaction, embed=error_embed)
        return
    
    # Get user's saved preferences from database
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
    
    view = await QueueView.create(
        discord_user_id=interaction.user.id,
        default_races=default_races,
        default_maps=default_maps,
    )
    
    # Use the same embed format as the updated embed
    embed = view.get_embed()
    
    await send_ephemeral_response(interaction, embed=embed, view=view)


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
        
        # Create queue preferences
        preferences = QueuePreferences(
            selected_races=self.view.get_selected_race_codes(),
            vetoed_maps=self.view.vetoed_maps,
            discord_user_id=user_info["id"],
            user_id="Player" + str(user_info["id"])  # TODO: Get actual user ID from database
        )
        
        # Create player and add to matchmaking queue
        player = Player(
            discord_user_id=user_info["id"],
            user_id=preferences.user_id,
            preferences=preferences
        )
        
        # Add player to matchmaker
        print(f"🎮 Adding player to matchmaker: {player.user_id}")
        matchmaker.add_player(player)
        
        # Show searching state
        searching_view = QueueSearchingView(
            original_view=self.view,
            selected_races=self.view.get_selected_race_codes(),
            vetoed_maps=self.view.vetoed_maps,
            player=player
        )
        
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
                from src.bot.utils.discord_utils import get_race_emote
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
        self.status_lock = asyncio.Lock()
        
        # Store this view globally so we can update it when match is found
        active_queue_views[player.discord_user_id] = self
        
        # Add cancel button
        self.add_item(CancelQueueButton(original_view, player))
        
        # Start async match checking
        asyncio.create_task(self.periodic_match_check())
    
    def start_status_updates(self) -> None:
        if self.status_task is None:
            self.status_task = asyncio.create_task(self.periodic_status_update())

    async def periodic_status_update(self):
        while self.is_active and self.player.discord_user_id in active_queue_views:
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
            color=discord.Color.teal()
        )
        return embed

    async def periodic_match_check(self):
        """Periodically check for matches and update the view"""
        while self.player.discord_user_id in active_queue_views:
            if self.player.discord_user_id in match_results:
                # Match found! Update the view
                match_result = match_results[self.player.discord_user_id]
                is_player1 = match_result.player1_discord_id == self.player.discord_user_id
                
                # Create match found view
                match_view = MatchFoundView(match_result, is_player1)
                
                # Register the view for replay detection
                if self.last_interaction:
                    channel_id = self.last_interaction.channel_id
                    match_view.register_for_replay_detection(channel_id)
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
                if self.player.discord_user_id in active_queue_views:
                    del active_queue_views[self.player.discord_user_id]
                self.is_active = False
                if self.status_task:
                    self.status_task.cancel()
                break
            
            # Wait 1 second before checking again
            await asyncio.sleep(1)
    
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
        # Remove player from matchmaker
        print(f"🚪 Removing player from matchmaker: {self.player.user_id}")
        matchmaker.remove_player(self.player.discord_user_id)
        
        # Clean up from active views
        if self.player.discord_user_id in active_queue_views:
            del active_queue_views[self.player.discord_user_id]
        if isinstance(interaction.view, QueueSearchingView):
            interaction.view.is_active = False
            if interaction.view.status_task:
                interaction.view.status_task.cancel()
        
        # Return to the original queue view with its embed
        await interaction.response.edit_message(
            embed=self.original_view.get_embed(),
            view=self.original_view
        )


# Global dictionary to store match results by Discord user ID
match_results = {}

# Global dictionary to store active queue views by Discord user ID
active_queue_views = {}

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
        from src.backend.services.match_completion_service import match_completion_service
        
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

def handle_match_result(match_result: MatchResult):
    """Handle when a match is found"""
    print(f"🎉 MATCH FOUND!")
    print(f"   Player 1: {match_result.player1_user_id} (Discord: {match_result.player1_discord_id})")
    print(f"   Player 2: {match_result.player2_user_id} (Discord: {match_result.player2_discord_id})")
    print(f"   Map: {match_result.map_choice}")
    print(f"   Server: {match_result.server_choice}")
    print(f"   Channel: {match_result.in_game_channel}")
    
    # Store match results for both players
    match_results[match_result.player1_discord_id] = match_result
    match_results[match_result.player2_discord_id] = match_result
    print(f"   Match results stored for both players")
    
    # Match results are now stored and will be picked up when players click "Check for Match"
    print(f"📱 Match results ready for both players to check")


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
        
        # Add match result reporting dropdown
        self.result_select = MatchResultSelect(match_result, is_player1, self)
        self.add_item(self.result_select)
        
        # Add confirmation dropdown (disabled initially)
        self.confirm_select = MatchResultConfirmSelect(self)
        self.add_item(self.confirm_select)
        
        # Update dropdown states based on persisted data
        self._update_dropdown_states()
    
    def _update_dropdown_states(self):
        """Update dropdown states based on persisted data"""
        if self.confirmation_status == "Confirmed":
            # Result has been confirmed, disable both dropdowns
            self.result_select.disabled = True
            self.confirm_select.disabled = True
        elif self.match_result.replay_uploaded == "Yes":
            # Replay uploaded, enable result selection
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
        # Get player information from database
        from src.backend.db.db_reader_writer import DatabaseReader
        db_reader = DatabaseReader()
        
        # Import discord utils for flag and emote functions
        from src.bot.utils.discord_utils import get_flag_emote, get_race_emote
        
        # Get player 1 info
        p1_info = db_reader.get_player_by_discord_uid(self.match_result.player1_discord_id)
        p1_name = p1_info.get('player_name') if p1_info else None
        p1_country = p1_info.get('country') if p1_info else None
        p1_display_name = p1_name if p1_name else str(self.match_result.player1_discord_id)
        p1_flag = get_flag_emote(p1_country) if p1_country else get_flag_emote("XX")
        
        # Get player 2 info
        p2_info = db_reader.get_player_by_discord_uid(self.match_result.player2_discord_id)
        p2_name = p2_info.get('player_name') if p2_info else None
        p2_country = p2_info.get('country') if p2_info else None
        p2_display_name = p2_name if p2_name else str(self.match_result.player2_discord_id)
        p2_flag = get_flag_emote(p2_country) if p2_country else get_flag_emote("XX")
        
        # Get race information from match result
        p1_race = self.match_result.player1_race
        p2_race = self.match_result.player2_race
        
        # Get race emotes
        p1_race_emote = get_race_emote(p1_race)
        p2_race_emote = get_race_emote(p2_race)
        
        # Get MMR values from database
        from src.backend.db.db_reader_writer import DatabaseReader
        db_reader = DatabaseReader()
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
        
        embed = discord.Embed(
            title=title,
            description="",  # Empty description as requested
            color=discord.Color.green()
        )
        
        # Player Information section
        embed.add_field(
            name="**Player Information:**",
            value=f"- Player 1: {p1_flag} {p1_race_emote} {p1_display_name} ({p1_race_name})\n- Player 2: {p2_flag} {p2_race_emote} {p2_display_name} ({p2_race_name})",
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
            print(f"🔍 FALLBACK: No map link found for {map_short_name} in {region_name}, falling back to Americas")
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
        print(f"🔍 EMBED: match_result value = '{self.match_result.match_result}'")
        
        if self.match_result.match_result == 'conflict':
            result_display = "Conflict"
            mmr_display = "\n- MMR Awarded: :x: Report Conflict Detected"
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
                from src.backend.services.mmr_service import MMRService
                mmr_service = MMRService()
                p1_mmr_rounded = mmr_service.round_mmr_change(p1_mmr_change)
                p2_mmr_rounded = mmr_service.round_mmr_change(p2_mmr_change)
                
                # Format MMR changes with proper signs
                p1_sign = "+" if p1_mmr_rounded >= 0 else ""
                p2_sign = "+" if p2_mmr_rounded >= 0 else ""
                
                mmr_display = f"\n- MMR Awarded: `{p1_display_name}: {p1_sign}{p1_mmr_rounded}`, `{p2_display_name}: {p2_sign}{p2_mmr_rounded}`"
            else:
                # MMR changes not calculated yet - always show TBD
                mmr_display = f"\n- MMR Awarded: `{p1_display_name}: TBD`, `{p2_display_name}: TBD`"
        else:
            result_display = "Not selected"
            mmr_display = f"\n- MMR Awarded: `{p1_display_name}: TBD`, `{p2_display_name}: TBD`"
            
        confirmation_display = self.match_result.match_result_confirmation_status or "Not confirmed"
        
        embed.add_field(
            name="**Match Result:**",
            value=f"- Result: `{result_display}`\n- Result Confirmation Status: `{confirmation_display}`{mmr_display}",
            inline=False
        )

        # Replay section
        replay_status = self.match_result.replay_uploaded or "No"
        if self.match_result.replay_upload_time:
            replay_upload_time = format_discord_timestamp(self.match_result.replay_upload_time)
        else:
            replay_upload_time = "Not uploaded"
        
        embed.add_field(
            name="**Replay Status:**",
            value=f"- Replay Uploaded: `{replay_status}`\n- Replay Uploaded At: {replay_upload_time}",
            inline=False
        )

        return embed
    
    def register_for_replay_detection(self, channel_id: int):
        """Register this view for replay detection in the specified channel."""
        self.channel_id = channel_id
        register_match_view(channel_id, self)
        match_id = getattr(self.match_result, "match_id", None)
        if match_id is not None:
            match_view_snapshots.setdefault(match_id, [])
            # Avoid duplicate entries for the same channel
            existing_channels = {cid for cid, _ in match_view_snapshots[match_id]}
            if channel_id not in existing_channels:
                match_view_snapshots[match_id].append((channel_id, self))
            else:
                # Replace existing entry with latest view reference
                match_view_snapshots[match_id] = [
                    (cid, self if cid == channel_id else view)
                    for cid, view in match_view_snapshots[match_id]
                ]
        print(f"🔍 REGISTER: Registered match view for channel {channel_id}, match {self.match_result.match_id}")


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
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Persist the confirmation status
        self.parent_view.match_result.match_result_confirmation_status = "Confirmed"
        
        # Set the selected option as default for persistence
        for option in self.options:
            option.default = (option.value == self.values[0])
        
        # Disable both dropdowns after confirmation
        self.parent_view.result_select.disabled = True
        self.parent_view.confirm_select.disabled = True
        
        # Update the embed to show confirmation status
        embed = self.parent_view.get_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

        # Record the player's individual report
        await self.parent_view.result_select.record_player_report(self.parent_view.selected_result)


class MatchResultSelect(discord.ui.Select):
    """Dropdown for reporting match results"""
    
    def __init__(self, match_result: MatchResult, is_player1: bool, parent_view):
        self.match_result = match_result
        self.is_player1 = is_player1
        self.parent_view = parent_view
        
        # Get player names from database
        from src.backend.db.db_reader_writer import DatabaseReader
        db_reader = DatabaseReader()
        
        p1_info = db_reader.get_player_by_discord_uid(match_result.player1_discord_id)
        self.p1_name = p1_info.get('player_name') if p1_info else str(match_result.player1_user_id)
        
        p2_info = db_reader.get_player_by_discord_uid(match_result.player2_discord_id)
        self.p2_name = p2_info.get('player_name') if p2_info else str(match_result.player2_user_id)
        
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
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Check if replay is uploaded before allowing result selection
        if self.parent_view.match_result.replay_uploaded != "Yes":
            await interaction.response.send_message("❌ Please upload a replay file before reporting match results.", ephemeral=True)
            return
        
        # Store the selected result in parent view and persist it
        self.parent_view.selected_result = self.values[0]
        self.parent_view.match_result.match_result = self.values[0]
        
        # Get result label
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
        
        # Set default value for result dropdown
        for option in self.options:
            if option.value == self.values[0]:
                option.default = True
            else:
                option.default = False
        
        # Update the message with new embed
        embed = self.parent_view.get_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
    
    async def add_result_confirmation_embed(self, interaction: discord.Interaction):
        """Add a confirmation embed when a player reports their result"""
        # Get the original match embed
        original_embed = self.view.get_embed()
        
        # Create confirmation embed
        confirmation_embed = discord.Embed(
            title="✅ Result Reported",
            description="Your result has been recorded. Waiting for your opponent to report their result.",
            color=discord.Color.blue()
        )
        
        # Disable the dropdown and update the message
        self.disabled = True
        self.placeholder = f"Selected: {self.get_selected_label()}"
        
        # Update the message with both embeds
        await interaction.response.edit_message(
            embeds=[original_embed, confirmation_embed],
            view=self.view
        )
    
    async def process_match_result(self, interaction: discord.Interaction, result: str):
        """Process a match result when both players agree"""
        # Determine winner Discord ID for database
        if result == "player1_win":
            winner_discord_id = self.match_result.player1_discord_id
            winner = self.match_result.player1_user_id
            loser = self.match_result.player2_user_id
        elif result == "player2_win":
            winner_discord_id = self.match_result.player2_discord_id
            winner = self.match_result.player2_user_id
            loser = self.match_result.player1_user_id
        else:  # draw
            winner_discord_id = -1  # -1 for draw
            winner = "Draw"
            loser = "Draw"
        
        # Record the result in the database
        from src.backend.services.matchmaking_service import matchmaker
        success = matchmaker.record_match_result(self.match_result.match_id, winner_discord_id)
        
        if not success:
            # Handle database error
            error_embed = discord.Embed(
                title="❌ Database Error",
                description="Failed to record match result. Please contact an administrator.",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=error_embed)
            return
        
        # Get the original match embed
        original_embed = self.view.get_embed()
        
        # Create result recorded embed
        result_embed = discord.Embed(
            title="🏆 Match Result Recorded",
            description=f"**Result:** {winner} won the match!\n\nMatch details have been recorded to the ladder.",
            color=discord.Color.green()
        )
        
        # Disable the dropdown and update the message
        self.disabled = True
        self.placeholder = f"Selected: {self.get_selected_label()}"
        
        # Update the message with both embeds
        await interaction.response.edit_message(
            embeds=[original_embed, result_embed],
            view=self.view
        )
        
        # Also update the other player's message
        await self.notify_other_player_result(original_embed, result_embed)
        
        print(f"📊 Match result recorded: {winner} defeated {loser} on {self.match_result.map_choice} (Match ID: {self.match_result.match_id})")
    
    # Removed handle_disagreement - no longer needed with individual reporting
    
    def get_selected_label(self):
        """Get the label for the selected result"""
        if self.values[0] == "player1_win":
            return f"{self.match_result.player1_user_id} Won"
        elif self.values[0] == "player2_win":
            return f"{self.match_result.player2_user_id} Won"
        else:
            return "Draw"
    
    async def notify_other_player_result(self, original_embed, result_embed):
        """Notify the other player about the match result"""
        # Notify both players about the result
        for player_id in [self.match_result.player1_discord_id, self.match_result.player2_discord_id]:
            if player_id in active_queue_views:
                other_view = active_queue_views[player_id]
                if hasattr(other_view, 'last_interaction') and other_view.last_interaction:
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
        for player_id in [self.match_result.player1_discord_id, self.match_result.player2_discord_id]:
            if player_id in active_queue_views:
                other_view = active_queue_views[player_id]
                if hasattr(other_view, 'last_interaction') and other_view.last_interaction:
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
            report_value = 1  # Player 1 won
        elif result == "player2_win":
            report_value = 2  # Player 2 won
        else:  # draw
            report_value = 0  # Draw
        
        # Record the player's report in the database
        try:
            from src.backend.services.matchmaking_service import matchmaker
            # Get the current player's Discord ID
            current_player_id = self.parent_view.match_result.player1_discord_id if self.is_player1 else self.parent_view.match_result.player2_discord_id
            success = matchmaker.record_match_result(self.match_result.match_id, current_player_id, report_value)
            
            if success:
                print(f"📝 Player report recorded for match {self.match_result.match_id}")
                
                # Wait for match completion and get final results
                final_results = await wait_for_match_completion(self.match_result.match_id)
                
                if final_results:
                    # Update match result with final data
                    print(f"🔍 FINAL RESULTS: {final_results}")
                    self.match_result.match_result = final_results['match_result']
                    self.match_result.p1_mmr_change = final_results['p1_mmr_change']
                    self.match_result.p2_mmr_change = final_results['p2_mmr_change']
                    print(f"🔍 SET match_result to: {self.match_result.match_result}")
                    
                    # Update the embed with final results
                    await self.update_embed_with_mmr_changes()
                else:
                    print(f"📝 Match {self.match_result.match_id} still waiting for other player")
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


# Global dictionary to track active match views for replay detection
active_match_views = {}
match_view_snapshots = {}


async def on_message(message: discord.Message):
    """
    Listen for SC2Replay file uploads in channels with active match views.
    """
    # Ignore bot messages
    if message.author.bot:
        return
    
    # Check if there are any attachments
    if not message.attachments:
        return
    
    # Check if any attachment is an SC2Replay file
    replay_service = ReplayService()
    replay_attachment = None
    
    for attachment in message.attachments:
        if replay_service.is_sc2_replay(attachment.filename):
            replay_attachment = attachment
            break  # Take the first SC2Replay file and ignore the rest
    
    if not replay_attachment:
        return
    
    # Check if this channel has an active match view
    channel_id = message.channel.id
    if channel_id not in active_match_views:
        return
    
    # Get the match view for this channel
    match_view = active_match_views[channel_id]
    if not match_view or not hasattr(match_view, 'match_result'):
        return
    
    # Download and store the replay file
    try:
        # Download the replay file
        replay_data = await replay_attachment.read()
        
        # Get current timestamp
        from src.backend.db.db_reader_writer import get_timestamp
        current_timestamp = get_timestamp()
        
        # Store replay in database
        from src.backend.db.db_reader_writer import DatabaseWriter
        db_writer = DatabaseWriter()
        
        # Determine which player uploaded the replay
        player_discord_uid = message.author.id
        
        # print(f"🔍 Attempting to store replay for match {match_view.match_result.match_id}, player {player_discord_uid}, data size: {len(replay_data)} bytes")
        
        success = db_writer.update_match_replay_1v1(
            match_view.match_result.match_id,
            player_discord_uid,
            replay_data,
            current_timestamp
        )
        
        if success:
            # Update the replay status and timestamp
            match_view.match_result.replay_uploaded = "Yes"
            match_view.match_result.replay_upload_time = get_current_unix_timestamp()

            # Update dropdown states now that replay is uploaded
            match_view._update_dropdown_states()

            # Update the existing embed
            embed = match_view.get_embed()
            if hasattr(match_view, 'last_interaction') and match_view.last_interaction:
                await match_view.last_interaction.edit_original_response(
                    embed=embed,
                    view=match_view
                )

            print(f"✅ Replay file stored for match {match_view.match_result.match_id} (player: {player_discord_uid})")
        else:
            print(f"❌ Failed to store replay for match {match_view.match_result.match_id}")
            
    except Exception as e:
        print(f"❌ Error processing replay file: {e}")


def register_match_view(channel_id: int, match_view):
    """Register a match view for replay detection."""
    active_match_views[channel_id] = match_view
    match_id = getattr(getattr(match_view, "match_result", None), "match_id", "unknown")
    print(f"🔍 REGISTER: Added match view to active_match_views: {channel_id} -> match {match_id}")
    print(f"🔍 REGISTER: Total active match views: {len(active_match_views)}")


def unregister_match_view(channel_id: int):
    """Unregister a match view when it's no longer active."""
    if channel_id in active_match_views:
        match_view = active_match_views[channel_id]
        match_id = getattr(getattr(match_view, "match_result", None), "match_id", "unknown")
        del active_match_views[channel_id]
        print(f"🔍 UNREGISTER: Removed match view from active_match_views: {channel_id} -> match {match_id}")
        print(f"🔍 UNREGISTER: Total active match views: {len(active_match_views)}")

        if match_id in match_view_snapshots:
            match_view_snapshots[match_id] = [
                pair for pair in match_view_snapshots[match_id] if pair[0] != channel_id
            ]
            if not match_view_snapshots[match_id]:
                del match_view_snapshots[match_id]
    else:
        print(f"⚠️ UNREGISTER: Channel {channel_id} not in active_match_views")


def unregister_match_views_by_match_id(match_id: int):
    """Remove all registered match views whose match id matches the provided id."""
    if match_id in match_view_snapshots:
        for channel_id, _ in match_view_snapshots[match_id]:
            unregister_match_view(channel_id)
        match_view_snapshots.pop(match_id, None)
    else:
        to_remove = []
        for channel_id, match_view in active_match_views.items():
            current_match_id = getattr(getattr(match_view, "match_result", None), "match_id", None)
            if current_match_id == match_id:
                to_remove.append(channel_id)

        for channel_id in to_remove:
            unregister_match_view(channel_id)


def get_active_match_views_by_match_id(match_id: int):
    """Return a list of active match views whose match id matches the provided id."""
    if match_id in match_view_snapshots:
        return match_view_snapshots[match_id].copy()

    matches = []
    for channel_id, match_view in active_match_views.items():
        current_match_id = getattr(getattr(match_view, "match_result", None), "match_id", None)
        if current_match_id == match_id:
            matches.append((channel_id, match_view))

    match_view_snapshots[match_id] = matches.copy()
    return matches

