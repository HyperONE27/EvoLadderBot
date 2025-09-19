"""Admin commands for ladder management."""
import discord
from discord import app_commands
from typing import List
from src.utils.user_utils import get_user_info, create_user_embed_field, log_user_action
from src.backend.db import get_db_session
from src.backend.services import UserService, MapService


# Admin user IDs - replace with actual admin Discord IDs
ADMIN_USER_IDS = [
    123456789012345678,  # Replace with actual admin IDs
]


def is_admin(interaction: discord.Interaction) -> bool:
    """Check if the user is an admin."""
    return interaction.user.id in ADMIN_USER_IDS


class MapUpdateModal(discord.ui.Modal, title="Update Map Pool"):
    """Modal for updating the map pool."""
    
    def __init__(self, current_maps: List[str]):
        super().__init__(timeout=600)
        self.current_maps = current_maps
        
        # Create text input with current maps
        self.maps_input = discord.ui.TextInput(
            label="Map Names (comma-separated)",
            placeholder="Eclipse, Polypoid, Goldenaura, ...",
            default=", ".join(current_maps),
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        self.add_item(self.maps_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        # Parse map names
        raw_maps = self.maps_input.value.split(",")
        new_maps = [m.strip() for m in raw_maps if m.strip()]
        
        if len(new_maps) < 3:
            await interaction.response.send_message(
                "❌ At least 3 maps are required in the pool.",
                ephemeral=True
            )
            return
        
        if len(new_maps) > 15:
            await interaction.response.send_message(
                "❌ Maximum 15 maps allowed in the pool.",
                ephemeral=True
            )
            return
        
        # Create confirmation embed
        embed = discord.Embed(
            title="📋 Confirm Map Pool Update",
            description="Please review the new map pool:",
            color=discord.Color.blue()
        )
        
        # Show old vs new
        old_maps_str = "\n".join(f"• {m}" for m in self.current_maps)
        new_maps_str = "\n".join(f"• {m}" for m in new_maps)
        
        embed.add_field(
            name="Current Maps",
            value=old_maps_str or "None",
            inline=True
        )
        
        embed.add_field(
            name="New Maps", 
            value=new_maps_str,
            inline=True
        )
        
        # Create confirmation view
        view = MapUpdateConfirmView(new_maps)
        
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )


class MapUpdateConfirmView(discord.ui.View):
    """View for confirming map pool update."""
    
    def __init__(self, new_maps: List[str]):
        super().__init__(timeout=120)
        self.new_maps = new_maps
    
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm the map update."""
        async with get_db_session() as db_session:
            await MapService.update_map_pool(db_session, self.new_maps)
        
        embed = discord.Embed(
            title="✅ Map Pool Updated",
            description=f"Successfully updated the map pool with {len(self.new_maps)} maps.",
            color=discord.Color.green()
        )
        
        map_list = "\n".join(f"{i+1}. {m}" for i, m in enumerate(self.new_maps))
        embed.add_field(
            name="New Map Pool",
            value=map_list,
            inline=False
        )
        
        user_info = get_user_info(interaction)
        log_user_action(user_info, "updated map pool", f"to {len(self.new_maps)} maps")
        
        await interaction.response.edit_message(embed=embed, view=None)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the map update."""
        embed = discord.Embed(
            title="❌ Update Cancelled",
            description="Map pool update has been cancelled.",
            color=discord.Color.red()
        )
        
        await interaction.response.edit_message(embed=embed, view=None)


async def resetladder_command(interaction: discord.Interaction):
    """Handle the /resetladder admin command."""
    if not is_admin(interaction):
        await interaction.response.send_message(
            "❌ You do not have permission to use this command.",
            ephemeral=True
        )
        return
    
    # Create confirmation embed
    embed = discord.Embed(
        title="⚠️ Reset Ladder Confirmation",
        description=(
            "**This will reset ALL player MMRs and statistics!**\n\n"
            "The following will be reset:\n"
            "• All MMRs to 1500\n"
            "• All win/loss/draw counts to 0\n"
            "• Match history will be preserved\n\n"
            "This action cannot be undone!"
        ),
        color=discord.Color.yellow()
    )
    
    view = ResetLadderConfirmView()
    
    await interaction.response.send_message(
        embed=embed,
        view=view,
        ephemeral=True
    )


class ResetLadderConfirmView(discord.ui.View):
    """View for confirming ladder reset."""
    
    def __init__(self):
        super().__init__(timeout=120)
    
    @discord.ui.button(label="Reset Ladder", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm the ladder reset."""
        # Require typing "RESET" to confirm
        modal = ResetConfirmModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the reset."""
        embed = discord.Embed(
            title="❌ Reset Cancelled",
            description="Ladder reset has been cancelled.",
            color=discord.Color.green()
        )
        
        await interaction.response.edit_message(embed=embed, view=None)


class ResetConfirmModal(discord.ui.Modal, title="Confirm Ladder Reset"):
    """Modal for final reset confirmation."""
    
    def __init__(self):
        super().__init__(timeout=120)
        
        self.confirm_input = discord.ui.TextInput(
            label='Type "RESET" to confirm',
            placeholder="RESET",
            required=True,
            max_length=5
        )
        self.add_item(self.confirm_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.confirm_input.value != "RESET":
            await interaction.response.send_message(
                "❌ Incorrect confirmation text. Reset cancelled.",
                ephemeral=True
            )
            return
        
        # Perform the reset
        async with get_db_session() as db_session:
            await UserService.reset_all_mmr(db_session)
        
        embed = discord.Embed(
            title="✅ Ladder Reset Complete",
            description="All player MMRs and statistics have been reset.",
            color=discord.Color.green()
        )
        
        user_info = get_user_info(interaction)
        log_user_action(user_info, "reset the ladder", "all MMRs reset to 1500")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def updatemaps_command(interaction: discord.Interaction):
    """Handle the /updatemaps admin command."""
    if not is_admin(interaction):
        await interaction.response.send_message(
            "❌ You do not have permission to use this command.",
            ephemeral=True
        )
        return
    
    # Get current maps
    async with get_db_session() as db_session:
        current_maps = await MapService.get_map_names(db_session)
    
    # Show modal for updating maps
    modal = MapUpdateModal(current_maps)
    await interaction.response.send_modal(modal)


def register_admin_commands(tree: app_commands.CommandTree):
    """Register admin commands."""
    
    @tree.command(
        name="resetladder",
        description="[ADMIN] Reset all player MMRs and statistics"
    )
    async def resetladder(interaction: discord.Interaction):
        await resetladder_command(interaction)
    
    @tree.command(
        name="updatemaps",
        description="[ADMIN] Update the map pool"
    )
    async def updatemaps(interaction: discord.Interaction):
        await updatemaps_command(interaction)
    
    return resetladder, updatemaps
