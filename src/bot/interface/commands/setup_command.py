import discord
from discord import app_commands
import re
from src.utils.country_region_utils import CountryLookup, RegionLookup
from src.utils.user_utils import get_user_info, log_user_action
from src.utils.validation_utils import validate_user_id, validate_battle_tag, validate_alt_ids
from components.confirm_embed import ConfirmEmbedView
from components.confirm_restart_cancel_buttons import ConfirmButton, RestartButton, CancelButton

country_lookup = CountryLookup()
region_lookup = RegionLookup()


# API Call / Data Handling
async def setup_command(interaction: discord.Interaction):
    """Handle the /setup slash command"""
    # Send the modal directly as the initial response
    modal = SetupModal()
    await interaction.response.send_modal(modal)


# Register Command
def register_setup_command(tree: app_commands.CommandTree):
    """Register the setup command"""
    @tree.command(
        name="setup",
        description="Set up your player profile for matchmaking"
    )
    async def setup(interaction: discord.Interaction):
        await setup_command(interaction)
    
    return setup


# UI Elements
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
    
    battle_tag = discord.ui.TextInput(
        label="BattleTag",
        placeholder="e.g., Username#1234 (3-12 letters + # + 4-12 digits)",
        min_length=8,
        max_length=25,  # 12 + # + 12 = 25 max
        required=True
    )
    
    alt_id_1 = discord.ui.TextInput(
        label="Alternative ID 1 (optional)",
        placeholder="Enter your first alternative ID (3-12 characters)",
        min_length=3,
        max_length=12,
        required=False
    )
    
    alt_id_2 = discord.ui.TextInput(
        label="Alternative ID 2 (optional)",
        placeholder="Enter your second alternative ID (3-12 characters)",
        min_length=3,
        max_length=12,
        required=False
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
        alt_ids_list = []
        
        # Validate alt_id_1 if provided
        if self.alt_id_1.value.strip():
            is_valid, error = validate_user_id(self.alt_id_1.value.strip())
            if not is_valid:
                await interaction.response.send_message(
                    f"❌ **Invalid Alternative ID 1:** {error}\n\nClick the button below to try again:",
                    view=ErrorView(error),
                    ephemeral=True
                )
                return
            alt_ids_list.append(self.alt_id_1.value.strip())
        
        # Validate alt_id_2 if provided
        if self.alt_id_2.value.strip():
            is_valid, error = validate_user_id(self.alt_id_2.value.strip())
            if not is_valid:
                await interaction.response.send_message(
                    f"❌ **Invalid Alternative ID 2:** {error}\n\nClick the button below to try again:",
                    view=ErrorView(error),
                    ephemeral=True
                )
                return
            alt_ids_list.append(self.alt_id_2.value.strip())
        
        # Check for duplicate IDs
        all_ids = [self.user_id.value] + alt_ids_list
        if len(all_ids) != len(set(all_ids)):
            await interaction.response.send_message(
                f"❌ **Duplicate IDs:** All IDs must be unique.\n\nClick the button below to try again:",
                view=ErrorView("Duplicate IDs detected"),
                ephemeral=True
            )
            return

        # Store data and show unified selection view
        view = UnifiedSetupView(
            user_id=self.user_id.value,
            alt_ids=alt_ids_list,
            battle_tag=self.battle_tag.value
        )
        
        # Create initial blue embed
        initial_embed = discord.Embed(
            title="🔍 Setup - Country & Region Selection",
            description="Please select your country and region.\n\n(Due to Discord UI limitations, we list only 49 countries here. If your country is not listed, please select \"Other\" at the bottom of Page 2, then set it up later with `/setcountry`.)",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(
            embed=initial_embed,
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

class CountryPage1Select(discord.ui.Select):
    def __init__(self, countries):
        # Countries 1-25 (indices 0-24)
        page_countries = countries[:25]
        options = [
            discord.SelectOption(label=country['name'], value=country['code'])
            for country in page_countries
        ]
        
        super().__init__(
            placeholder="Choose your country of citizenship (Page 1)...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        # Update country page 1 selection
        selected_country = next(
            c for c in self.view.countries 
            if c['code'] == self.values[0]
        )
        self.view.selected_country = selected_country
        self.view.country_page1_selection = self.values[0]
        
        # Clear the other country page selection in the view state
        self.view.country_page2_selection = None
        
        # Update the view
        await self.view.update_view(interaction)

class CountryPage2Select(discord.ui.Select):
    def __init__(self, countries):
        # Countries 26-50 (indices 25-49)
        page_countries = countries[25:50] if len(countries) > 25 else []
        options = [
            discord.SelectOption(label=country['name'], value=country['code'])
            for country in page_countries
        ]
        
        super().__init__(
            placeholder="Choose your country of citizenship (Page 2)...",
            min_values=1,
            max_values=1,
            options=options,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        # Update country page 2 selection
        selected_country = next(
            c for c in self.view.countries 
            if c['code'] == self.values[0]
        )
        self.view.selected_country = selected_country
        self.view.country_page2_selection = self.values[0]
        
        # Clear the other country page selection in the view state
        self.view.country_page1_selection = None
        
        # Update the view
        await self.view.update_view(interaction)

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
            options=options,
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        selected_region = next(
            r for r in self.view.regions 
            if r['code'] == self.values[0]
        )
        self.view.selected_region = selected_region
        
        # Update the view
        await self.view.update_view(interaction)

class UnifiedSetupView(discord.ui.View):
    def __init__(self, user_id: str, alt_ids: list, battle_tag: str):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.alt_ids = alt_ids
        self.battle_tag = battle_tag
        self.selected_country = None
        self.selected_region = None
        
        # Track which country page has a selection (for mutual exclusion)
        self.country_page1_selection = None
        self.country_page2_selection = None
        
        # Get countries and regions
        self.countries = country_lookup.get_common_countries()
        self.regions = region_lookup.get_all_regions()
        
        # Create dropdowns
        self.country_page1_select = CountryPage1Select(self.countries)
        self.country_page2_select = CountryPage2Select(self.countries)
        self.region_select = RegionSelect(self.regions)
        
        # Add dropdowns to view
        self.add_item(self.country_page1_select)
        self.add_item(self.country_page2_select)
        self.add_item(self.region_select)
        
        # Add action buttons
        self.add_item(ConfirmButton(self.confirm_callback, "✅ Confirm", row=3))
        self.add_item(RestartButton(SetupModal(), "🔄 Restart", row=3))
        self.add_item(CancelButton(SetupModal(), "❌ Cancel", row=3, show_fields=False))

    async def update_view(self, interaction: discord.Interaction):
        """Update the view with current selections"""
        # Create a new view with current selections to maintain state
        new_view = UnifiedSetupView(self.user_id, self.alt_ids, self.battle_tag)
        new_view.selected_country = self.selected_country
        new_view.selected_region = self.selected_region
        new_view.country_page1_selection = self.country_page1_selection
        new_view.country_page2_selection = self.country_page2_selection
        
        # Update the dropdowns to show current selections
        if self.country_page1_selection:
            new_view.country_page1_select.placeholder = f"Selected: {self.selected_country['name']}"
        if self.country_page2_selection:
            new_view.country_page2_select.placeholder = f"Selected: {self.selected_country['name']}"
        if self.selected_region:
            new_view.region_select.placeholder = f"Selected: {self.selected_region['name']}"
        
        await interaction.response.edit_message(
            embed=new_view.get_status_embed(),
            view=new_view
        )

    def get_status_embed(self) -> discord.Embed:
        """Get status embed based on current selections"""
        embed = discord.Embed(
            title="🔍 Setup - Country & Region Selection",
            color=discord.Color.blue()
        )
        
        if self.selected_country and self.selected_region:
            embed.description = (
                "**Selected:**\n"
                f"- Country of citizenship/nationality: `{self.selected_country['name']}`\n"
                f"- Region of residence: `{self.selected_region['name']}`\n\n"
                "Click Confirm to proceed."
            )
        elif self.selected_country:
            embed.description = (
                "**Selected:**\n"
                f"- Country of citizenship/nationality: `{self.selected_country['name']}`\n\n"
                "Please select your region of residence."
            )
        elif self.selected_region:
            embed.description = (
                "**Selected:**\n"
                f"- Region of residence: `{self.selected_region['name']}`\n\n"
                "Please select your country of citizenship/nationality.\n\n(Due to Discord UI limitations, we list only 49 countries here. If your country is not listed, please select \"Other\" at the bottom of Page 2, then set it up later with `/setcountry`.)"
            )
        else:
            embed.description = "Please select your country and region.\n\n(Due to Discord UI limitations, we list only 49 countries here. If your country is not listed, please select \"Other\" at the bottom of Page 2, then set it up later with `/setcountry`.)"
        
        return embed

    async def confirm_callback(self, interaction: discord.Interaction):
        """Handle confirm button press"""
        if not self.selected_country or not self.selected_region:
            error_embed = discord.Embed(
                title="🔍 Setup - Country & Region Selection",
                description="❌ Please select both country and region before confirming.",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(
                embed=error_embed,
                ephemeral=True
            )
            return
        
        # Show confirmation
        view = create_setup_confirmation_view(
            user_id=self.user_id,
            alt_ids=self.alt_ids,
            battle_tag=self.battle_tag,
            country=self.selected_country,
            region=self.selected_region
        )
        
        await interaction.response.edit_message(
            content="",
            embed=view.embed,
            view=view
        )


def create_setup_confirmation_view(user_id: str, alt_ids: list, battle_tag: str, country: dict, region: dict) -> ConfirmEmbedView:
    """Create a preview confirmation view for setup data."""
    
    # Prepare fields for display
    fields = [
        (":id: **User ID**", user_id),
        (":hash: **BattleTag**", battle_tag),
        (":map: **Country of Citizenship/Nationality**", country['name']),
        (":map: **Region of Residence**", region['name'])
    ]
    
    if alt_ids:
        alt_ids_str = ", ".join(alt_ids)
        fields.append((":id: **Alternative IDs**", alt_ids_str))
    else:
        fields.append((":id: **Alternative IDs**", "None"))
    
    # Define confirmation callback
    async def confirm_callback(interaction: discord.Interaction):
        user_info = get_user_info(interaction)
        
        # TODO: Send data to backend
        # async with aiohttp.ClientSession() as session:
        #     await session.post(
        #         f'http://backend/api/players/{user_info["id"]}',
        #         json={
        #             'discord_user_id': user_info["id"],
        #             'user_id': user_id,
        #             'alt_ids': alt_ids,
        #             'battle_tag': battle_tag,
        #             'country_code': country['code'],
        #             'region_code': region['code']
        #         }
        #     )
        
        # Log the setup
        log_user_action(user_info, "completed player setup", 
                       f"User ID: {user_id}, Country: {country['name']}, Region: {region['name']}")
        
        # Show post-confirmation view
        post_confirm_view = ConfirmEmbedView(
            title="Setup Complete!",
            description="Your player profile has been successfully configured:",
            fields=fields,
            mode="post_confirmation",
            reset_target=SetupModal(),
            restart_label="🔄 Setup Again"
        )
        
        
        await interaction.response.edit_message(
            content="",
            embed=post_confirm_view.embed,
            view=post_confirm_view
        )
    
    return ConfirmEmbedView(
        title="Preview Setup Information",
        description="Please review your setup information before confirming:",
        fields=fields,
        mode="preview",
        confirm_callback=confirm_callback,
        reset_target=SetupModal()
    )