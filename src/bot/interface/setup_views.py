import discord
from discord import ui
from typing import Dict, Optional
import re
from src.utils.data_loader import DataLoader
from src.bot.interface.ui_components import PaginatedCountrySelect, RegionSelect

data_loader = DataLoader()

class SetupModal(ui.Modal, title="Player Setup - Basic Info"):
    """Modal for collecting basic player information"""
    
    main_id = ui.TextInput(
        label="Main ID",
        placeholder="Enter your main ID (max 12 characters)",
        max_length=12,
        required=True,
        style=discord.TextStyle.short
    )
    
    alt_ids = ui.TextInput(
        label="Alternative IDs",
        placeholder="Enter alt IDs separated by commas (optional)",
        max_length=100,
        required=False,
        style=discord.TextStyle.paragraph
    )
    
    battletag = ui.TextInput(
        label="BattleTag",
        placeholder="Username#1234 (or Username#12345)",
        max_length=18,
        required=True,
        style=discord.TextStyle.short
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # Validate BattleTag format
        battletag_pattern = r'^[^#]{1,12}#\d{4,5}$'
        if not re.match(battletag_pattern, self.battletag.value):
            await interaction.response.send_message(
                "Invalid BattleTag format. Please use: Username#1234 (4-5 digits)",
                ephemeral=True
            )
            return
        
        # Validate alt IDs
        alt_ids_list = []
        if self.alt_ids.value:
            alt_ids_list = [aid.strip() for aid in self.alt_ids.value.split(',')]
            invalid_alt_ids = [aid for aid in alt_ids_list if len(aid) > 12 or len(aid) == 0]
            if invalid_alt_ids:
                await interaction.response.send_message(
                    f"Invalid alternative IDs (must be 1-12 characters): {', '.join(invalid_alt_ids)}",
                    ephemeral=True
                )
                return
        
        # Store the data
        user_data = {
            'main_id': self.main_id.value,
            'alt_ids': alt_ids_list,
            'battletag': self.battletag.value
        }
        
        # Send location selection view
        view = LocationSelectionView(user_data, page=0)
        await interaction.response.send_message(
            "📍 **Step 2/3: Select your country and region**\n"
            "If you don't see your country, select 'Other' and use `/setcountry` later.",
            view=view,
            ephemeral=True
        )


class LocationSelectionView(ui.View):
    """View for selecting country and region"""
    
    def __init__(self, user_data: Dict, page: int = 0):
        super().__init__(timeout=300)
        self.user_data = user_data
        self.page = page
        self.selected_country: Optional[str] = None
        self.selected_region: Optional[str] = None
        
        # Get data
        common_countries = data_loader.get_common_countries()
        regions = data_loader.get_regions()
        
        # Add country select
        country_select = PaginatedCountrySelect(
            countries=common_countries,
            page=page,
            callback_func=self.on_country_select
        )
        self.add_item(country_select)
        
        # Add region select
        region_select = RegionSelect(
            regions=regions,
            callback_func=self.on_region_select
        )
        self.add_item(region_select)
        
        # Add navigation buttons if needed
        total_pages = (len(common_countries) + 24) // 25
        if total_pages > 1:
            if page > 0:
                prev_button = ui.Button(label="◀️ Previous", style=discord.ButtonStyle.secondary, row=2)
                prev_button.callback = self.prev_page
                self.add_item(prev_button)
            
            if page < total_pages - 1:
                next_button = ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, row=2)
                next_button.callback = self.next_page
                self.add_item(next_button)
        
        # Add confirm button (disabled until both selected)
        self.confirm_button = ui.Button(
            label="✅ Confirm",
            style=discord.ButtonStyle.success,
            disabled=True,
            row=3
        )
        self.confirm_button.callback = self.confirm_setup
        self.add_item(self.confirm_button)
        
        # Add restart and cancel buttons
        restart_button = ui.Button(label="🔄 Restart", style=discord.ButtonStyle.secondary, row=3)
        restart_button.callback = self.restart_setup
        self.add_item(restart_button)
        
        cancel_button = ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=3)
        cancel_button.callback = self.cancel_setup
        self.add_item(cancel_button)
    
    async def on_country_select(self, interaction: discord.Interaction, country_code: str):
        self.selected_country = country_code
        self.check_enable_confirm()
        await interaction.response.edit_message(view=self)
    
    async def on_region_select(self, interaction: discord.Interaction, region_code: str):
        self.selected_region = region_code
        self.check_enable_confirm()
        await interaction.response.edit_message(view=self)
    
    def check_enable_confirm(self):
        """Enable confirm button if both selections are made"""
        if self.selected_country and self.selected_region:
            self.confirm_button.disabled = False
    
    async def prev_page(self, interaction: discord.Interaction):
        view = LocationSelectionView(self.user_data, page=self.page - 1)
        view.selected_country = self.selected_country
        view.selected_region = self.selected_region
        view.check_enable_confirm()
        await interaction.response.edit_message(view=view)
    
    async def next_page(self, interaction: discord.Interaction):
        view = LocationSelectionView(self.user_data, page=self.page + 1)
        view.selected_country = self.selected_country
        view.selected_region = self.selected_region
        view.check_enable_confirm()
        await interaction.response.edit_message(view=view)
    
    async def confirm_setup(self, interaction: discord.Interaction):
        """Show preview and final confirmation"""
        self.user_data['country'] = self.selected_country
        self.user_data['region'] = self.selected_region
        
        # Create preview
        country = data_loader.get_country_by_code(self.selected_country)
        region = data_loader.get_region_by_code(self.selected_region)
        
        embed = discord.Embed(
            title="📋 Profile Preview",
            description="Please review your information before confirming:",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Main ID", value=self.user_data['main_id'], inline=True)
        embed.add_field(name="BattleTag", value=self.user_data['battletag'], inline=True)
        embed.add_field(name="Country", value=country['name'] if country else "Unknown", inline=True)
        embed.add_field(name="Region", value=region['name'] if region else "Unknown", inline=True)
        
        if self.user_data['alt_ids']:
            embed.add_field(
                name="Alternative IDs",
                value=", ".join(self.user_data['alt_ids']),
                inline=False
            )
        
        if self.selected_country == "XX":
            embed.set_footer(text="⚠️ Remember to set your actual country later using /setcountry")
        
        view = ProfilePreviewView(self.user_data)
        await interaction.response.edit_message(
            content="✅ **Setup Complete - Please review your information:**",
            embed=embed,
            view=view
        )
    
    async def restart_setup(self, interaction: discord.Interaction):
        modal = SetupModal()
        await interaction.response.send_modal(modal)
    
    async def cancel_setup(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="❌ Setup cancelled.",
            view=self
        )


class ProfilePreviewView(ui.View):
    """Final confirmation view"""
    
    def __init__(self, user_data: Dict):
        super().__init__(timeout=300)
        self.user_data = user_data
        
        confirm_button = ui.Button(
            label="✅ Confirm and Save",
            style=discord.ButtonStyle.success
        )
        confirm_button.callback = self.confirm_save
        self.add_item(confirm_button)
        
        restart_button = ui.Button(
            label="🔄 Start Over",
            style=discord.ButtonStyle.secondary
        )
        restart_button.callback = self.restart
        self.add_item(restart_button)
        
        cancel_button = ui.Button(
            label="❌ Cancel",
            style=discord.ButtonStyle.danger
        )
        cancel_button.callback = self.cancel
        self.add_item(cancel_button)
    
    async def confirm_save(self, interaction: discord.Interaction):
        """Save the profile"""
        # TODO: Send to backend API
        # async with aiohttp.ClientSession() as session:
        #     await session.post('http://backend/api/players', json=self.user_data)
        
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(
            content="✅ **Profile saved successfully!** Your matchmaking profile has been created.",
            view=self
        )
    
    async def restart(self, interaction: discord.Interaction):
        modal = SetupModal()
        await interaction.response.send_modal(modal)
    
    async def cancel(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="❌ Setup cancelled.",
            view=self
        )