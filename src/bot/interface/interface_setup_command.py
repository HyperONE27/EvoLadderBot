import discord
from discord import app_commands
import re
from src.utils.country_region_utils import CountryLookup, RegionLookup
from src.utils.user_utils import get_user_info, create_user_embed_field, log_user_action
from src.utils.validation_utils import validate_user_id, validate_battle_tag, validate_alt_ids

country_lookup = CountryLookup()
region_lookup = RegionLookup()

class SetupModal(discord.ui.Modal, title="Player Setup"):
    def __init__(self, error_message: str = None):
        super().__init__(timeout=300)
        self.error_message = error_message
        
    user_id = discord.ui.TextInput(
        label="User ID",
        placeholder="Enter your user ID (3-12 characters)",
        min_length=3,
        max_length=12,
        required=True
    )
    
    alt_ids = discord.ui.TextInput(
        label="Alternative IDs (optional)",
        placeholder="Enter alternative IDs separated by commas",
        max_length=200,
        required=False,
        style=discord.TextStyle.paragraph
    )
    
    battle_tag = discord.ui.TextInput(
        label="BattleTag",
        placeholder="e.g., Username#1234 (3-12 letters + # + 4-12 digits)",
        min_length=8,
        max_length=25,  # 12 + # + 12 = 25 max
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Validate user ID
        is_valid, error = validate_user_id(self.user_id.value)
        if not is_valid:
            await interaction.response.send_message(
                f"❌ **Invalid User ID:** {error}\n\nClick the button below to try again:",
                view=ErrorView(error),
                ephemeral=True
            )
            return

        # Validate BattleTag
        is_valid, error = validate_battle_tag(self.battle_tag.value)
        if not is_valid:
            await interaction.response.send_message(
                f"❌ **Invalid BattleTag:** {error}\n\nClick the button below to try again:",
                view=ErrorView(error),
                ephemeral=True
            )
            return

        # Validate alternative IDs
        is_valid, error, alt_ids_list = validate_alt_ids(self.alt_ids.value)
        if not is_valid:
            await interaction.response.send_message(
                f"❌ **Invalid Alternative IDs:** {error}\n\nClick the button below to try again:",
                view=ErrorView(error),
                ephemeral=True
            )
            return

        # Store data and show country selection
        view = CountrySelectView(
            user_id=self.user_id.value,
            alt_ids=alt_ids_list,
            battle_tag=self.battle_tag.value
        )
        
        await interaction.response.send_message(
            "✅ Basic information collected! Now please select your country of citizenship:",
            view=view,
            ephemeral=True
        )

class ErrorView(discord.ui.View):
    def __init__(self, error_message: str):
        super().__init__(timeout=60)
        self.error_message = error_message

    @discord.ui.button(label=" Try Again", style=discord.ButtonStyle.primary)
    async def try_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SetupModal()
        await interaction.response.send_modal(modal)

class CountrySelect(discord.ui.Select):
    def __init__(self, countries, page=1):
        self.page = page
        self.countries = countries
        
        # Create options for this page
        start_idx = (page - 1) * 24
        end_idx = start_idx + 24
        page_countries = countries[start_idx:end_idx]
        
        options = [
            discord.SelectOption(label=country['name'], value=country['code'])
            for country in page_countries
        ]
        
        # Add navigation options
        if page == 1 and len(countries) > 24:
            options.append(discord.SelectOption(
                label="➡️ Next Page", 
                value="__next_page__",
                description="View more countries"
            ))
        elif page == 2:
            options.insert(0, discord.SelectOption(
                label="⬅️ Previous Page", 
                value="__prev_page__",
                description="Go back to first page"
            ))
        
        super().__init__(
            placeholder=f"Choose your country of citizenship (Page {page})...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "__next_page__":
            # Show second page
            view = CountrySelectView(
                user_id=self.view.user_id,
                alt_ids=self.view.alt_ids,
                battle_tag=self.view.battle_tag,
                page=2
            )
            await interaction.response.edit_message(
                content="✅ Basic information collected! Now please select your country of citizenship:",
                view=view
            )
        elif self.values[0] == "__prev_page__":
            # Show first page
            view = CountrySelectView(
                user_id=self.view.user_id,
                alt_ids=self.view.alt_ids,
                battle_tag=self.view.battle_tag,
                page=1
            )
            await interaction.response.edit_message(
                content="✅ Basic information collected! Now please select your country of citizenship:",
                view=view
            )
        else:
            # Country selected, move to region selection
            selected_country = next(
                c for c in self.view.countries 
                if c['code'] == self.values[0]
            )
            
            view = RegionSelectView(
                user_id=self.view.user_id,
                alt_ids=self.view.alt_ids,
                battle_tag=self.view.battle_tag,
                country=selected_country
            )
            
            await interaction.response.edit_message(
                content="✅ Country selected! Now please select your region of residency:",
                view=view
            )

class CountrySelectView(discord.ui.View):
    def __init__(self, user_id: str, alt_ids: list, battle_tag: str, page=1):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.alt_ids = alt_ids
        self.battle_tag = battle_tag
        self.page = page
        
        # Get common countries
        self.countries = country_lookup.get_common_countries()
        
        self.add_item(CountrySelect(self.countries, page))

class RegionSelect(discord.ui.Select):
    def __init__(self, regions):
        options = [
            discord.SelectOption(label=region['name'], value=region['code'])
            for region in regions
        ]
        
        super().__init__(
            placeholder="Choose your region of residency...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_region = next(
            r for r in self.view.regions 
            if r['code'] == self.values[0]
        )
        
        # Show confirmation view
        view = ConfirmationView(
            user_id=self.view.user_id,
            alt_ids=self.view.alt_ids,
            battle_tag=self.view.battle_tag,
            country=self.view.country,
            region=selected_region
        )
        
        await interaction.response.edit_message(
            content="📋 Please review and confirm your information:",
            view=view
        )

class RegionSelectView(discord.ui.View):
    def __init__(self, user_id: str, alt_ids: list, battle_tag: str, country: dict):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.alt_ids = alt_ids
        self.battle_tag = battle_tag
        self.country = country
        
        # Get all regions
        self.regions = region_lookup.get_all_regions()
        
        self.add_item(RegionSelect(self.regions))

class ConfirmationView(discord.ui.View):
    def __init__(self, user_id: str, alt_ids: list, battle_tag: str, country: dict, region: dict):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.alt_ids = alt_ids
        self.battle_tag = battle_tag
        self.country = country
        self.region = region

    @discord.ui.button(label=" Restart", style=discord.ButtonStyle.secondary)
    async def restart(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Create a new modal and send it
        modal = SetupModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get user info
        user_info = get_user_info(interaction)
        
        # Create confirmation embed
        embed = discord.Embed(
            title="✅ Setup Complete!",
            description="Your player profile has been configured:",
            color=discord.Color.green()
        )
        
        embed.add_field(name="User ID", value=self.user_id, inline=True)
        embed.add_field(name="BattleTag", value=self.battle_tag, inline=True)
        embed.add_field(name="Country", value=self.country['name'], inline=True)
        embed.add_field(name="Region", value=self.region['name'], inline=False)
        
        if self.alt_ids:
            alt_ids_str = ", ".join(self.alt_ids)
            embed.add_field(name="Alternative IDs", value=alt_ids_str, inline=False)
        else:
            embed.add_field(name="Alternative IDs", value="None", inline=False)
        
        # Add user information
        embed.add_field(**create_user_embed_field(user_info))
        
        # TODO: Send data to backend
        # async with aiohttp.ClientSession() as session:
        #     await session.post(
        #         f'http://backend/api/players/{user_info["id"]}',
        #         json={
        #             'discord_user_id': user_info["id"],
        #             'user_id': self.user_id,
        #             'alt_ids': self.alt_ids,
        #             'battle_tag': self.battle_tag,
        #             'country_code': self.country['code'],
        #             'region_code': self.region['code']
        #         }
        #     )
        
        # Log the setup
        log_user_action(user_info, "completed player setup", 
                       f"User ID: {self.user_id}, Country: {self.country['name']}, Region: {self.region['name']}")
        
        await interaction.response.edit_message(
            content="",
            embed=embed,
            view=None
        )

async def setup_command(interaction: discord.Interaction):
    """Handle the /setup slash command"""
    # Send the modal directly as the initial response
    modal = SetupModal()
    await interaction.response.send_modal(modal)

def register_setup_command(tree: app_commands.CommandTree):
    """Register the setup command"""
    @tree.command(
        name="setup",
        description="Set up your player profile for matchmaking"
    )
    async def setup(interaction: discord.Interaction):
        await setup_command(interaction)
    
    return setup