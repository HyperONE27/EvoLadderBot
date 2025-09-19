"""Queue command for matchmaking."""
import discord
from discord import app_commands
import asyncio
from datetime import datetime
from typing import List, Optional
from src.utils.user_utils import get_user_info, create_user_embed_field, log_user_action
from src.backend.db import get_db_session
from src.backend.services import UserService, MatchmakingService, MapService
from src.backend.db.models import Race, MatchResult


class RaceSelect(discord.ui.Select):
    """Select menu for choosing races to queue with."""
    
    def __init__(self, saved_races: List[str] = None):
        # Define all available races
        races = [
            discord.SelectOption(label="BW Terran", value="bw_terran", emoji="🟦"),
            discord.SelectOption(label="BW Zerg", value="bw_zerg", emoji="🟪"),
            discord.SelectOption(label="BW Protoss", value="bw_protoss", emoji="🟨"),
            discord.SelectOption(label="SC2 Terran", value="sc2_terran", emoji="🔵"),
            discord.SelectOption(label="SC2 Zerg", value="sc2_zerg", emoji="🟣"),
            discord.SelectOption(label="SC2 Protoss", value="sc2_protoss", emoji="🟡"),
        ]
        
        # Set default selections based on saved preferences
        if saved_races:
            for option in races:
                if option.value in saved_races:
                    option.default = True
        
        super().__init__(
            placeholder="Select races to queue with (max 6)",
            min_values=1,
            max_values=6,
            options=races,
            custom_id="race_select"
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Check if valid BW vs SC2 selection
        has_bw = any(race.startswith("bw_") for race in self.values)
        has_sc2 = any(race.startswith("sc2_") for race in self.values)
        
        if has_bw and has_sc2:
            embed = discord.Embed(
                title="❌ Invalid Race Selection",
                description="You cannot queue with both BW and SC2 races at the same time.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Valid selections",
                value="• BW races only (for SC2 opponents)\n• SC2 races only (for BW opponents)",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await interaction.response.defer()


class MapVetoSelect(discord.ui.Select):
    """Select menu for choosing map vetoes."""
    
    def __init__(self, available_maps: List[str], saved_vetoes: List[str] = None, max_vetoes: int = 4):
        self.max_vetoes = max_vetoes
        
        # Create options for each map
        options = []
        for map_name in available_maps[:25]:  # Discord limit is 25 options
            option = discord.SelectOption(
                label=map_name,
                value=map_name
            )
            if saved_vetoes and map_name in saved_vetoes:
                option.default = True
            options.append(option)
        
        super().__init__(
            placeholder=f"Select maps to veto (max {max_vetoes})",
            min_values=0,
            max_values=min(max_vetoes, len(options)),
            options=options,
            custom_id="map_veto_select"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


class QueueView(discord.ui.View):
    """View for queue setup (race and map selection)."""
    
    def __init__(self, user_id: int, mmr_data: dict, available_maps: List[str], 
                 saved_races: List[str] = None, saved_vetoes: List[str] = None):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.mmr_data = mmr_data
        self.available_maps = available_maps
        self.selected_races = saved_races or []
        self.selected_vetoes = saved_vetoes or []
        
        # Calculate max vetoes based on map pool size
        self.max_vetoes = max(1, len(available_maps) // 2 - 1)
        
        # Add selects
        self.race_select = RaceSelect(saved_races)
        self.map_veto_select = MapVetoSelect(available_maps, saved_vetoes, self.max_vetoes)
        
        self.add_item(self.race_select)
        self.add_item(self.map_veto_select)
    
    @discord.ui.button(label="Queue", style=discord.ButtonStyle.success, row=2)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start queueing for a match."""
        # Get selected values
        self.selected_races = self.race_select.values
        self.selected_vetoes = self.map_veto_select.values
        
        # Validate race selection again
        has_bw = any(race.startswith("bw_") for race in self.selected_races)
        has_sc2 = any(race.startswith("sc2_") for race in self.selected_races)
        
        if has_bw and has_sc2:
            embed = discord.Embed(
                title="❌ Invalid Race Selection",
                description="You cannot queue with both BW and SC2 races.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Save preferences and add to queue
        async with get_db_session() as db_session:
            # Update user preferences
            await UserService.update_user_preferences(
                db_session,
                discord_id=self.user_id,
                map_vetoes=self.selected_vetoes,
                last_queue_races=self.selected_races
            )
            
            # Get user and add to queue
            user = await UserService.get_user_by_discord_id(db_session, self.user_id)
            queue_entry = await MatchmakingService.add_to_queue(
                db_session,
                user,
                self.selected_races,
                self.selected_vetoes
            )
        
        # Create queue status embed
        embed = discord.Embed(
            title="🔍 Searching for Match...",
            description="You have been added to the queue!",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Show selected races and MMR
        race_info = []
        for race in self.selected_races:
            race_display = race.replace("_", " ").title()
            mmr = self.mmr_data.get(race, 1500)
            race_info.append(f"{race_display}: {int(mmr)} MMR")
        
        embed.add_field(
            name="Queued Races",
            value="\n".join(race_info),
            inline=True
        )
        
        if self.selected_vetoes:
            embed.add_field(
                name="Map Vetoes",
                value="\n".join(self.selected_vetoes),
                inline=True
            )
        
        embed.add_field(
            name="Queue Time",
            value="0:00",
            inline=False
        )
        
        # Create queue management view
        queue_view = QueueManagementView(self.user_id)
        
        await interaction.response.edit_message(
            embed=embed,
            view=queue_view
        )
        
        # Start updating queue status
        asyncio.create_task(self._update_queue_status(interaction, queue_view))
    
    async def _update_queue_status(self, interaction: discord.Interaction, queue_view):
        """Update queue status periodically."""
        start_time = datetime.utcnow()
        message = await interaction.original_response()
        
        while queue_view.is_queued:
            await asyncio.sleep(5)  # Update every 5 seconds
            
            try:
                async with get_db_session() as db_session:
                    # Check if still in queue
                    position = await MatchmakingService.get_queue_position(
                        db_session, 
                        self.user_id
                    )
                    
                    if not position:
                        # No longer in queue - check for match
                        # This would be handled by a separate match notification system
                        break
                    
                    # Update embed with current status
                    elapsed = datetime.utcnow() - start_time
                    minutes = int(elapsed.total_seconds() // 60)
                    seconds = int(elapsed.total_seconds() % 60)
                    
                    embed = message.embeds[0]
                    embed.set_field_at(
                        -1,  # Last field (Queue Time)
                        name="Queue Time",
                        value=f"{minutes}:{seconds:02d}",
                        inline=False
                    )
                    
                    # Add position info
                    position_num, total = position
                    embed.description = f"Position in queue: **{position_num}/{total}**"
                    
                    await message.edit(embed=embed)
                    
            except Exception as e:
                print(f"Error updating queue status: {e}")
                break


class QueueManagementView(discord.ui.View):
    """View for managing queue status (cancel button)."""
    
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.is_queued = True
    
    @discord.ui.button(label="Cancel Queue", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the queue."""
        async with get_db_session() as db_session:
            removed = await MatchmakingService.remove_from_queue(
                db_session,
                self.user_id
            )
        
        if removed:
            embed = discord.Embed(
                title="❌ Queue Cancelled",
                description="You have been removed from the queue.",
                color=discord.Color.red()
            )
        else:
            embed = discord.Embed(
                title="ℹ️ Not in Queue",
                description="You were not in the queue.",
                color=discord.Color.blue()
            )
        
        self.is_queued = False
        await interaction.response.edit_message(embed=embed, view=None)


async def queue_command(interaction: discord.Interaction):
    """Handle the /queue command."""
    user_info = get_user_info(interaction)
    
    # Check prerequisites
    async with get_db_session() as db_session:
        # Check terms acceptance
        has_accepted = await UserService.has_accepted_terms(
            db_session,
            interaction.user.id
        )
        
        if not has_accepted:
            embed = discord.Embed(
                title="❌ Terms of Service Required",
                description="You must accept the Terms of Service before queueing.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="How to proceed",
                value="Please use the `/termsofservice` command to review and accept the terms.",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Check setup completion
        has_setup = await UserService.has_completed_setup(
            db_session,
            interaction.user.id
        )
        
        if not has_setup:
            embed = discord.Embed(
                title="❌ Setup Required",
                description="You must complete your profile setup before queueing.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="How to proceed",
                value="Please use the `/setup` command to set up your profile first.",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Check if already in queue
        position = await MatchmakingService.get_queue_position(
            db_session,
            interaction.user.id
        )
        
        if position:
            pos_num, total = position
            embed = discord.Embed(
                title="⚠️ Already in Queue",
                description=f"You are already in the queue at position **{pos_num}/{total}**.",
                color=discord.Color.yellow()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Get user data
        user = await UserService.get_user_by_discord_id(db_session, interaction.user.id)
        mmr_data = await UserService.get_user_mmr(db_session, interaction.user.id)
        
        # Get available maps
        available_maps = await MapService.get_map_names(db_session)
    
    # Create queue setup embed
    embed = discord.Embed(
        title="⚔️ Ranked Queue Setup",
        description="Select your races and map vetoes for matchmaking.",
        color=discord.Color.green()
    )
    
    # Show current MMR for each race
    mmr_lines = []
    for race_key, mmr in mmr_data.items():
        race_display = race_key.replace("_", " ").title()
        mmr_lines.append(f"{race_display}: **{int(mmr)}** MMR")
    
    embed.add_field(
        name="Your Ratings",
        value="\n".join(mmr_lines),
        inline=False
    )
    
    embed.add_field(
        name="Instructions",
        value=(
            "• Select races you want to queue with\n"
            "• You can only queue as BW **or** SC2 races\n"
            f"• You may veto up to {max(1, len(available_maps) // 2 - 1)} maps\n"
            "• Your preferences will be saved"
        ),
        inline=False
    )
    
    # Add user info
    embed.add_field(**create_user_embed_field(user_info))
    
    # Create view with saved preferences
    view = QueueView(
        user_id=interaction.user.id,
        mmr_data=mmr_data,
        available_maps=available_maps,
        saved_races=user.last_queue_races,
        saved_vetoes=user.map_vetoes
    )
    
    await interaction.response.send_message(
        embed=embed,
        view=view,
        ephemeral=True
    )
    
    log_user_action(user_info, "opened queue interface")


def register_queue_command(tree: app_commands.CommandTree):
    """Register the queue command."""
    @tree.command(
        name="queue",
        description="Queue for a ranked ladder match"
    )
    async def queue(interaction: discord.Interaction):
        await queue_command(interaction)
    
    return queue
