import asyncio
import discord
from discord import app_commands
from src.backend.services.race_config_service import RaceConfigService
from src.backend.services.ladder_config_service import LadderConfigService
from src.bot.interface.components.error_embed import ErrorEmbedException, create_error_view_from_exception
from src.bot.interface.components.confirm_restart_cancel_buttons import ConfirmRestartCancelButtons
from src.backend.services.matchmaking_service import matchmaker, Player, QueuePreferences, MatchResult
from src.utils.user_utils import get_user_info

race_service = RaceConfigService()
ladder_service = LadderConfigService()


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
    # Get user's saved preferences (can be implemented later with a user service)
    # For now, we'll use empty defaults
    default_races = []  # TODO: Get from user preferences service
    default_maps = []   # TODO: Get from user preferences service
    
    view = QueueView(default_races=default_races, default_maps=default_maps)
    
    # Use the same embed format as the updated embed
    embed = view.get_embed()
    
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class RaceSelect(discord.ui.Select):
    """Multiselect dropdown for race selection"""
    
    def __init__(self, default_values=None):
        # Get race options from service
        race_options = race_service.get_race_options_for_dropdown()
        
        options = []
        for label, value, description in race_options:
            options.append(
                discord.SelectOption(
                    label=label,
                    value=value,
                    description=description,
                    default=value in (default_values or [])
                )
            )
        
        super().__init__(
            placeholder="Select your races (multiselect)...",
            min_values=0,
            max_values=len(options),
            options=options,
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        self.view.selected_races = self.values
        await self.view.update_embed(interaction)


class MapVetoSelect(discord.ui.Select):
    """Multiselect dropdown for map vetoes"""
    
    def __init__(self, default_values=None):
        # Get map options from ladder service
        maps = ladder_service.get_maps()
        
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
            row=2
        )
    
    async def callback(self, interaction: discord.Interaction):
        self.view.vetoed_maps = self.values
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
        if not self.view.selected_races or len(self.view.selected_races) == 0:
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
            selected_races=self.view.selected_races,
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
            selected_races=self.view.selected_races,
            vetoed_maps=self.view.vetoed_maps,
            player=player
        )
        
        searching_embed = discord.Embed(
            title="🔍 Searching...",
            description="The queue is searching for a game.",
            color=discord.Color.teal()
        )
        
        await interaction.response.edit_message(
            embed=searching_embed,
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
        self.view.selected_races = []
        self.view.vetoed_maps = []
        
        # Update the view with cleared selections
        await self.view.update_embed(interaction)


class QueueView(discord.ui.View):
    """Main queue view with race and map veto selections"""
    
    def __init__(self, default_races=None, default_maps=None):
        super().__init__(timeout=300)
        self.selected_races = default_races or []
        self.vetoed_maps = default_maps or []
        
        # Add action buttons at the top
        self.add_item(JoinQueueButton())
        self.add_item(ClearSelectionsButton())
        
        # Add selection dropdowns with default values
        self.add_item(RaceSelect(default_values=default_races))
        self.add_item(MapVetoSelect(default_values=default_maps))
    
    def get_embed(self):
        """Get the embed for this view without requiring an interaction"""
        embed = discord.Embed(
            title="🎮 Matchmaking Queue",
            description="Configure your queue preferences",
            color=discord.Color.blue()
        )
        
        # Add race selection info
        if self.selected_races:
            # Sort races according to the service's defined order
            race_order = race_service.get_race_order()
            sorted_races = [race for race in race_order if race in self.selected_races]
            race_names = [race_service.get_race_name(race) for race in sorted_races]
            race_list = "\n".join([f"• {name}" for name in race_names])
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
            map_order = ladder_service.get_map_short_names()
            sorted_maps = [map_name for map_name in map_order if map_name in self.vetoed_maps]
            map_list = "\n".join([f"• {map_name}" for map_name in sorted_maps])
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
        
        # Recreate the view with current selections to maintain persistence
        new_view = QueueView(default_races=self.selected_races, default_maps=self.vetoed_maps)
        await interaction.response.edit_message(embed=embed, view=new_view)


class QueueSearchingView(discord.ui.View):
    """View shown while searching for a match"""
    
    def __init__(self, original_view, selected_races, vetoed_maps, player):
        super().__init__(timeout=300)
        self.original_view = original_view
        self.selected_races = selected_races
        self.vetoed_maps = vetoed_maps
        self.player = player
        self.last_interaction = None
        
        # Store this view globally so we can update it when match is found
        active_queue_views[player.discord_user_id] = self
        
        # Add cancel button
        self.add_item(CancelQueueButton(original_view, player))
        
        # Start async match checking
        asyncio.create_task(self.periodic_match_check())
    
    async def periodic_match_check(self):
        """Periodically check for matches and update the view"""
        while self.player.discord_user_id in active_queue_views:
            if self.player.discord_user_id in match_results:
                # Match found! Update the view
                match_result = match_results[self.player.discord_user_id]
                is_player1 = match_result.player1_discord_id == self.player.discord_user_id
                
                # Create match found view
                match_view = MatchFoundView(match_result, is_player1)
                
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
            emoji="❌",
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
        
        # Return to the original queue view with its embed
        await interaction.response.edit_message(
            embed=self.original_view.get_embed(),
            view=self.original_view
        )


# Global dictionary to store match results by Discord user ID
match_results = {}

# Global dictionary to store active queue views by Discord user ID
active_queue_views = {}

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
        super().__init__(timeout=300)
        self.match_result = match_result
        self.is_player1 = is_player1
        
        # Add match result reporting dropdown
        self.add_item(MatchResultSelect(match_result, is_player1))
    
    def get_embed(self) -> discord.Embed:
        """Get the match found embed"""
        embed = discord.Embed(
            title="🎮 Match Found!",
            description="A match has been found for you!",
            color=discord.Color.green()
        )
        
        # Determine opponent info
        if self.is_player1:
            opponent_user_id = self.match_result.player2_user_id
            opponent_discord_id = self.match_result.player2_discord_id
        else:
            opponent_user_id = self.match_result.player1_user_id
            opponent_discord_id = self.match_result.player1_discord_id
        
        embed.add_field(
            name="Opponent's User ID",
            value=f"`{opponent_user_id}`",
            inline=False
        )
        
        embed.add_field(
            name="Opponent's Discord ID",
            value=f"`{opponent_discord_id}`",
            inline=False
        )
        
        embed.add_field(
            name="Map Choice",
            value=f"`{self.match_result.map_choice}`",
            inline=False
        )
        
        embed.add_field(
            name="Server Choice",
            value=f"`{self.match_result.server_choice}`",
            inline=False
        )
        
        embed.add_field(
            name="In-Game Channel",
            value=f"`{self.match_result.in_game_channel}`",
            inline=False
        )
        
        return embed


class MatchResultSelect(discord.ui.Select):
    """Dropdown for reporting match results"""
    
    def __init__(self, match_result: MatchResult, is_player1: bool):
        self.match_result = match_result
        self.is_player1 = is_player1
        
        # Create options for the dropdown
        options = [
            discord.SelectOption(
                label=f"{match_result.player1_user_id} Won",
                value="player1_win",
                description=f"Report that {match_result.player1_user_id} won the match"
            ),
            discord.SelectOption(
                label=f"{match_result.player2_user_id} Won", 
                value="player2_win",
                description=f"Report that {match_result.player2_user_id} won the match"
            ),
            discord.SelectOption(
                label="Draw",
                value="draw",
                description="Report that the match was a draw"
            )
        ]
        
        super().__init__(
            placeholder="Report match winner...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Get the current player's Discord ID
        current_player_id = interaction.user.id
        
        # Store the result
        result_key = f"{self.match_result.player1_discord_id}_{self.match_result.player2_discord_id}"
        
        # Initialize match results storage if not exists
        if not hasattr(MatchFoundView, 'match_results_reported'):
            MatchFoundView.match_results_reported = {}
        
        # Store this player's reported result
        MatchFoundView.match_results_reported[result_key] = MatchFoundView.match_results_reported.get(result_key, {})
        MatchFoundView.match_results_reported[result_key][current_player_id] = self.values[0]
        
        # Check if both players have reported
        reported_results = MatchFoundView.match_results_reported[result_key]
        if len(reported_results) == 2:
            # Both players have reported - check for agreement
            results = list(reported_results.values())
            if len(set(results)) == 1:  # All results are the same
                # Results match - process the match
                await self.process_match_result(interaction, results[0])
            else:
                # Results don't match - show error to both players
                await self.handle_disagreement(interaction)
        else:
            # Only one player has reported so far - add confirmation embed
            await self.add_result_confirmation_embed(interaction)
    
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
        if result == "player1_win":
            winner = self.match_result.player1_user_id
            loser = self.match_result.player2_user_id
        elif result == "player2_win":
            winner = self.match_result.player2_user_id
            loser = self.match_result.player1_user_id
        else:  # draw
            winner = "Draw"
            loser = "Draw"
        
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
        
        # TODO: Send result to backend API
        print(f"📊 Match result: {winner} defeated {loser} on {self.match_result.map_choice}")
    
    async def handle_disagreement(self, interaction: discord.Interaction):
        """Handle when players report different results"""
        # Get the original match embed
        original_embed = self.view.get_embed()
        
        # Create disagreement embed
        disagreement_embed = discord.Embed(
            title="⚠️ Result Disagreement",
            description="The reported results don't match. Please contact an administrator to resolve this dispute.",
            color=discord.Color.red()
        )
        
        # Disable the dropdown and update the message
        self.disabled = True
        self.placeholder = f"Selected: {self.get_selected_label()}"
        
        # Update the message with both embeds
        await interaction.response.edit_message(
            embeds=[original_embed, disagreement_embed],
            view=self.view
        )
        
        # Also send the disagreement to the other player
        await self.notify_other_player_disagreement(original_embed, disagreement_embed)
        
        print(f"⚠️ Result disagreement for match {self.match_result.player1_user_id} vs {self.match_result.player2_user_id}")
    
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

