# src/bot/commands/setup_command.py

import discord
from discord import app_commands
import json
import re
from typing import Optional, List, Tuple
from pathlib import Path
from src.utils.country_organization import ORGANIZED_COUNTRIES, split_countries_alphabetically

# Load data files
DATA_PATH = Path(__file__).parent.parent.parent.parent / "data"
with open(DATA_PATH / "misc" / "countries.json", "r", encoding="utf-8") as f:
    COUNTRIES = json.load(f)
with open(DATA_PATH / "misc" / "regions.json", "r", encoding="utf-8") as f:
    REGIONS = json.load(f)

# Continent emojis for better UX
CONTINENT_EMOJIS = {
    "Africa": "🌍",
    "Asia": "🌏",
    "Europe": "🌍",
    "North America": "🌎",
    "South America": "🌎",
    "Oceania": "🌏",
    "Antarctica": "🧊"
}

class SetupModal(discord.ui.Modal, title="Player Setup - Basic Info"):
    """Modal for collecting basic player information"""
    
    main_id = discord.ui.TextInput(
        label="Main ID",
        placeholder="Enter your main ID (max 12 characters)",
        max_length=12,
        required=True,
        style=discord.TextStyle.short
    )
    
    alt_ids = discord.ui.TextInput(
        label="Alternative IDs",
        placeholder="Enter alt IDs separated by commas (optional)",
        max_length=100,
        required=False,
        style=discord.TextStyle.paragraph
    )
    
    battletag = discord.ui.TextInput(
        label="BattleTag",
        placeholder="Username#1234 (or Username#12345)",
        max_length=18,
        required=True,
        style=discord.TextStyle.short
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_data = {}
    
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
        self.user_data = {
            'main_id': self.main_id.value,
            'alt_ids': alt_ids_list,
            'battletag': self.battletag.value
        }
        
        # Send location selection view
        view = ContinentSelectionView(self.user_data)
        await interaction.response.send_message(
            "📍 **Step 2/3: Select your continent**",
            view=view,
            ephemeral=True
        )


class ContinentSelectionView(discord.ui.View):
    """View for selecting continent"""
    
    def __init__(self, user_data: dict):
        super().__init__(timeout=300)
        self.user_data = user_data
        
        # Create continent select
        options = []
        for continent in ["Africa", "Asia", "Europe", "North America", "South America", "Oceania"]:
            emoji = CONTINENT_EMOJIS.get(continent, "🌍")
            country_count = len(ORGANIZED_COUNTRIES[continent])
            options.append(discord.SelectOption(
                label=continent,
                value=continent,
                emoji=emoji,
                description=f"{country_count} countries"
            ))
        
        # Add Antarctica if it has countries
        if "Antarctica" in ORGANIZED_COUNTRIES and ORGANIZED_COUNTRIES["Antarctica"]:
            options.append(discord.SelectOption(
                label="Antarctica",
                value="Antarctica",
                emoji="🧊",
                description=f"{len(ORGANIZED_COUNTRIES['Antarctica'])} territories"
            ))
        
        continent_select = discord.ui.Select(
            placeholder="Select your continent...",
            options=options,
            row=0
        )
        continent_select.callback = self.continent_callback
        self.add_item(continent_select)
        
        # Add restart button
        restart_button = discord.ui.Button(
            label="🔄 Restart",
            style=discord.ButtonStyle.secondary,
            row=1
        )
        restart_button.callback = self.restart_callback
        self.add_item(restart_button)
        
        # Add cancel button
        cancel_button = discord.ui.Button(
            label="❌ Cancel",
            style=discord.ButtonStyle.danger,
            row=1
        )
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)
    
    async def continent_callback(self, interaction: discord.Interaction):
        continent = interaction.data['values'][0]
        countries = ORGANIZED_COUNTRIES[continent]
        
        # Check if we need alphabetical splitting
        groups = split_countries_alphabetically(countries, max_per_group=25)
        
        if len(groups) == 1:
            # Direct country selection
            view = CountrySelectionView(self.user_data, countries, continent)
        else:
            # Need letter range selection first
            view = AlphabeticalGroupView(self.user_data, groups, continent)
        
        await interaction.response.edit_message(
            content=f"📍 **Step 2/3: Select your country** (Continent: {continent})",
            view=view
        )
    
    async def restart_callback(self, interaction: discord.Interaction):
        modal = SetupModal()
        await interaction.response.send_modal(modal)
    
    async def cancel_callback(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="Setup cancelled.",
            view=self
        )


class AlphabeticalGroupView(discord.ui.View):
    """View for selecting alphabetical group when continent has too many countries"""
    
    def __init__(self, user_data: dict, groups: List[Tuple[str, List[dict]]], continent: str):
        super().__init__(timeout=300)
        self.user_data = user_data
        self.groups = groups
        self.continent = continent
        
        # Create letter range select
        options = []
        for label, countries in groups:
            if len(countries) == 1:
                desc = countries[0]['name']
            else:
                desc = f"{countries[0]['name']} - {countries[-1]['name']}"
            
            options.append(discord.SelectOption(
                label=f"Countries {label}",
                value=label,
                description=desc,
                emoji="📖"
            ))
         
        select = discord.ui.Select(
            placeholder="Select letter range...",
            options=options,
            row=0
        )
        select.callback = self.group_callback
        self.add_item(select)
        
        # Add back button
        back_button = discord.ui.Button(
            label="⬅️ Back",
            style=discord.ButtonStyle.secondary,
            row=1
        )
        back_button.callback = self.back_callback
        self.add_item(back_button)
        
        # Add restart button
        restart_button = discord.ui.Button(
            label="🔄 Restart",
            style=discord.ButtonStyle.secondary,
            row=1
        )
        restart_button.callback = self.restart_callback
        self.add_item(restart_button)
        
        # Add cancel button
        cancel_button = discord.ui.Button(
            label="❌ Cancel",
            style=discord.ButtonStyle.danger,
            row=1
        )
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)
    
    async def group_callback(self, interaction: discord.Interaction):
        selected_label = interaction.data['values'][0]
        countries = next(countries for label, countries in self.groups if label == selected_label)
         
        view = CountrySelectionView(self.user_data, countries, self.continent)
        await interaction.response.edit_message(
            content=f"📍 **Step 2/3: Select your country** (Continent: {self.continent}, Range: {selected_label})",
            view=view
        )
    
    async def back_callback(self, interaction: discord.Interaction):
        view = ContinentSelectionView(self.user_data)
        await interaction.response.edit_message(
            content="📍 **Step 2/3: Select your continent**",
            view=view
        )
    
    async def restart_callback(self, interaction: discord.Interaction):
        modal = SetupModal()
        await interaction.response.send_modal(modal)
    
    async def cancel_callback(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="Setup cancelled.",
            view=self
        )


class CountrySelectionView(discord.ui.View):
    """View for selecting a specific country"""
    
    def __init__(self, user_data: dict, countries: List[dict], continent: str):
        super().__init__(timeout=300)
        self.user_data = user_data
        self.continent = continent
        
        # Create country select
        options = []
        for country in countries:
            options.append(discord.SelectOption(
                label=country['name'],
                value=country['code'],
                emoji="🏳️"
            ))
         
        select = discord.ui.Select(
            placeholder="Select your country...",
            options=options,
            row=0
        )
        select.callback = self.country_callback
        self.add_item(select)
        
        # Add back button
        back_button = discord.ui.Button(
            label="⬅️ Back",
            style=discord.ButtonStyle.secondary,
            row=1
        )
        back_button.callback = self.back_callback
        self.add_item(back_button)
        
        # Add restart button
        restart_button = discord.ui.Button(
            label="🔄 Restart",
            style=discord.ButtonStyle.secondary,
            row=1
        )
        restart_button.callback = self.restart_callback
        self.add_item(restart_button)
        
        # Add cancel button
        cancel_button = discord.ui.Button(
            label="❌ Cancel",
            style=discord.ButtonStyle.danger,
            row=1
        )
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)
    
    async def country_callback(self, interaction: discord.Interaction):
        country_code = interaction.data['values'][0]
        self.user_data['country'] = country_code
        
        view = RegionSelectionView(self.user_data)
        await interaction.response.edit_message(
            content="📍 **Step 3/3: Select your region of residence**",
            view=view
        )
    
    async def back_callback(self, interaction: discord.Interaction):
        countries = ORGANIZED_COUNTRIES[self.continent]
        groups = split_countries_alphabetically(countries, max_per_group=25)
        
        if len(groups) == 1:
            view = ContinentSelectionView(self.user_data)
            await interaction.response.edit_message(
                content="📍 **Step 2/3: Select your continent**",
                view=view
            )
        else:
            view = AlphabeticalGroupView(self.user_data, groups, self.continent)
            await interaction.response.edit_message(
                content=f"📍 **Step 2/3: Select your country** (Continent: {self.continent})",
                view=view
            )
    
    async def restart_callback(self, interaction: discord.Interaction):
        modal = SetupModal()
        await interaction.response.send_modal(modal)
    
    async def cancel_callback(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="Setup cancelled.",
            view=self
        )


class RegionSelectionView(discord.ui.View):
    """View for selecting region"""
    
    def __init__(self, user_data: dict):
        super().__init__(timeout=300)
        self.user_data = user_data
        # Create region select
        options = []
        for region in REGIONS:
            options.append(discord.SelectOption(
                label=region['name'],
                value=region['code'],
                emoji="📍"
            ))
        
        select = discord.ui.Select(
            placeholder="Select your region of residence...",
            options=options,
            row=0
        )
        select.callback = self.region_callback
        self.add_item(select)
        
        # Add back button
        back_button = discord.ui.Button(
            label="⬅️ Back",
           style=discord.ButtonStyle.secondary,
            row=1
        )
        back_button.callback = self.back_callback
        self.add_item(back_button)
       
        # Add restart button
        restart_button = discord.ui.Button(
            label="🔄 Restart",
            style=discord.ButtonStyle.secondary,
            row=1
        )
        restart_button.callback = self.restart_callback
        self.add_item(restart_button)
       
        # Add cancel button
        cancel_button = discord.ui.Button(
            label="❌ Cancel",
           style=discord.ButtonStyle.danger,
            row=1
        )
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)
    
    async def region_callback(self, interaction: discord.Interaction):
        region_code = interaction.data['values'][0]
        self.user_data['region'] = region_code
        
        # Show preview
        view = ProfilePreviewView(self.user_data)
        embed = self._create_preview_embed()
        
        await interaction.response.edit_message(
            content="✅ **Setup Complete - Please review your information:**",
            embed=embed,
            view=view
        )

    def _create_preview_embed(self) -> discord.Embed:
        """Create the preview embed"""
        country_name = next((c['name'] for c in COUNTRIES if c['code'] == self.user_data['country']), self.user_data['country'])
        region_name = next((r['name'] for r in REGIONS if r['code'] == self.user_data['region']), self.user_data['region'])
        
        embed = discord.Embed(
            title="📋 Profile Preview",
            description="Please review your information before confirming:",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Main ID", value=self.user_data['main_id'], inline=True)
        embed.add_field(name="BattleTag", value=self.user_data['battletag'], inline=True)
        embed.add_field(name="Country", value=f"{country_name} ({self.user_data['country']})", inline=True)
        embed.add_field(name="Region", value=f"{region_name} ({self.user_data['region']})", inline=True)
        
        if self.user_data['alt_ids']:
            embed.add_field(
                name="Alternative I    Ds",
                value=", ".join(self.user_data['alt_ids']),
                inline=False
            )
        
        return embed
    
    async def back_callback(self, interaction: discord.Interaction):
        # Find continent for the selected country
        continent = None
        for cont, countries in ORGANIZED_COUNTRIES.items():
            if any(c['code'] == self.user_data['country'] for c in countries):
                continent = cont
                break
        
        countries = [c for c in ORGANIZED_COUNTRIES[continent] if c['code'] == self.user_data['country']]
        view = CountrySelectionView(self.user_data, ORGANIZED_COUNTRIES[continent], continent)
        await interaction.response.edit_message(
            content=f"📍 **Step 2/3: Select your country** (Continent: {continent})",
            view=view,
            embed=None
        )
    
    async def restart_callback(self, interaction: discord.Interaction):
        modal = SetupModal()
        await interaction.response.send_modal(modal)
    
    async def cancel_callback(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="Setup cancelled.",
            view=self,
            embed=None
        )


class ProfilePreviewView(discord.ui.View):
    """View for profile preview with confirm/edit options"""
    
    def __init__(self, user_data: dict):
        super().__init__(timeout=300)
        self.user_data = user_data
        
        # Add confirm button
        confirm_button = discord.ui.Button(
            label="✅ Confirm and Save",
            style=discord.ButtonStyle.success,
            row=0
        )
        confirm_button.callback = self.confirm_callback
        self.add_item(confirm_button)
        
        # Add restart button
        restart_button = discord.ui.Button(
            label="🔄 Start Over",
            style=discord.ButtonStyle.secondary,
            row=0
        )
        restart_button.callback = self.restart_callback
        self.add_item(restart_button)
        
        # Add cancel button
        cancel_button = discord.ui.Button(
            label="❌ Cancel",
            style=discord.ButtonStyle.danger,
            row=0
        )
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)
    
    async def confirm_callback(self, interaction: discord.Interaction):
        """Save the profile"""
        # TODO: Send data to backend API for storage
        # async with aiohttp.ClientSession() as session:
        #     async with session.post('http://backend/api/players', json=self.user_data) as resp:
        #         ...
        
        # Disable all components
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(
            content="✅ **Profile saved successfully!** Your matchmaking profile has been created.",
            view=self
        )
    async def restart_callback(self, interaction: discord.Interaction):
        modal = SetupModal()
        await interaction.response.send_modal(modal)
    
    async def cancel_callback(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(
            content="Setup cancelled.",
            view=self
        )

async def setup_command(interaction: discord.Interaction):
    """
    Main setup command handler
    """
    # Check if user already has a profile (TODO: implement backend check)
    # existing_profile = await check_existing_profile(interaction.user.id)
    # if existing_profile:
    #     await interaction.response.send_message(
    #         "You already have a profile set up. Use `/profile update` to modify it.",
    #         ephemeral=True
    #     )
    #     return
    
    modal = SetupModal()
    await interaction.response.send_modal(modal)


# Command tree registration function
def register_setup_command(tree: app_commands.CommandTree):
    """Register the setup command with the bot's command tree"""
    @tree.command(
        name="setup",
        description="Set up your player profile for matchmaking"
    )
    async def setup(interaction: discord.Interaction):
        await setup_command(interaction)
    
    return setup