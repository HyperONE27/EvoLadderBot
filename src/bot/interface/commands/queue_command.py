import discord
from discord import app_commands
from src.backend.services.race_config_service import RaceConfigService
from src.backend.services.ladder_config_service import LadderConfigService

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
    
    embed = discord.Embed(
        title="🎮 Matchmaking Queue",
        description="Configure your queue preferences",
        color=discord.Color.blue()
    )
    
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
            row=0
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
            placeholder="Select maps to veto (multiselect)...",
            min_values=0,
            max_values=len(options),
            options=options,
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        self.view.vetoed_maps = self.values
        await self.view.update_embed(interaction)


class QueueView(discord.ui.View):
    """Main queue view with race and map veto selections"""
    
    def __init__(self, default_races=None, default_maps=None):
        super().__init__(timeout=300)
        self.selected_races = default_races or []
        self.vetoed_maps = default_maps or []
        
        # Add selection dropdowns with default values
        self.add_item(RaceSelect(default_values=default_races))
        self.add_item(MapVetoSelect(default_values=default_maps))
    
    async def update_embed(self, interaction: discord.Interaction):
        """Update the embed with current selections"""
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
        if self.vetoed_maps:
            # Sort maps according to the service's defined order
            map_order = ladder_service.get_map_short_names()
            sorted_maps = [map_name for map_name in map_order if map_name in self.vetoed_maps]
            map_list = "\n".join([f"• {map_name}" for map_name in sorted_maps])
            embed.add_field(
                name="Vetoed Maps",
                value=map_list,
                inline=False
            )
        else:
            embed.add_field(
                name="Vetoed Maps",
                value="No vetoes",
                inline=False
            )
        
        # Recreate the view with current selections to maintain persistence
        new_view = QueueView(default_races=self.selected_races, default_maps=self.vetoed_maps)
        await interaction.response.edit_message(embed=embed, view=new_view)
