import discord
from discord import app_commands
import re
from typing import Optional
from src.backend.services.countries_service import CountriesService
from src.backend.services.regions_service import RegionsService
from src.backend.services.command_guard_service import CommandGuardService, CommandGuardError
from src.backend.services.user_info_service import UserInfoService, get_user_info, log_user_action
from src.backend.services.validation_service import ValidationService
from src.bot.utils.discord_utils import send_ephemeral_response, get_flag_emote
from src.bot.interface.components.confirm_embed import ConfirmEmbedView
from src.bot.interface.components.confirm_restart_cancel_buttons import ConfirmRestartCancelButtons
from src.bot.interface.components.command_guard_embeds import create_command_guard_error_embed
from src.bot.config import GLOBAL_TIMEOUT

countries_service = CountriesService()
regions_service = RegionsService()
user_info_service = UserInfoService()
validation_service = ValidationService()
guard_service = CommandGuardService()


# API Call / Data Handling
async def setup_command(interaction: discord.Interaction):
    """Handle the /setup slash command"""
    try:
        player = guard_service.ensure_player_record(interaction.user.id, interaction.user.name)
        guard_service.require_tos_accepted(player)
    except CommandGuardError as exc:
        error_embed = create_command_guard_error_embed(exc)
        await send_ephemeral_response(interaction, embed=error_embed)
        return
    
    # Get existing player data for presets
    existing_data = user_info_service.get_player(interaction.user.id)
    
    # Send the modal with existing data as presets
    modal = SetupModal(existing_data=existing_data)
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
    def __init__(self, error_message: Optional[str] = None, existing_data: Optional[dict] = None) -> None:
        super().__init__(timeout=GLOBAL_TIMEOUT)
        self.error_message = error_message
        self.existing_data = existing_data or {}
        
        # Create TextInput fields with existing data as defaults
        self.user_id = discord.ui.TextInput(
            label="User ID",
            placeholder="Enter your user ID (3-12 characters)",
            default=self.existing_data.get('player_name', ''),
            min_length=3,
            max_length=12,
            required=True
        )
        
        self.battle_tag = discord.ui.TextInput(
            label="BattleTag",
            placeholder="e.g., Username#1234 (3-12 letters + # + 4-12 digits)",
            default=self.existing_data.get('battletag', ''),
            min_length=8,
            max_length=25,  # 12 + # + 12 = 25 max
            required=True
        )
        
        self.alt_id_1 = discord.ui.TextInput(
            label="Alternative ID 1 (optional)",
            placeholder="Enter your first alternative ID (3-12 characters)",
            default=self.existing_data.get('alt_player_name_1', ''),
            min_length=3,
            max_length=12,
            required=False
        )
        
        self.alt_id_2 = discord.ui.TextInput(
            label="Alternative ID 2 (optional)",
            placeholder="Enter your second alternative ID (3-12 characters)",
            default=self.existing_data.get('alt_player_name_2', ''),
            min_length=3,
            max_length=12,
            required=False
        )
        
        # Add the fields to the modal
        self.add_item(self.user_id)
        self.add_item(self.battle_tag)
        self.add_item(self.alt_id_1)
        self.add_item(self.alt_id_2)

    async def on_submit(self, interaction: discord.Interaction):
        # Capture current input values for restart functionality
        current_input = {
            'player_name': self.user_id.value,
            'battletag': self.battle_tag.value,
            'alt_player_name_1': self.alt_id_1.value.strip() if self.alt_id_1.value else '',
            'alt_player_name_2': self.alt_id_2.value.strip() if self.alt_id_2.value else '',
            # Preserve country/region from existing data if present
            'country': self.existing_data.get('country', ''),
            'region': self.existing_data.get('region', '')
        }
        
        # Validate user ID
        is_valid, error = validation_service.validate_user_id(self.user_id.value)
        if not is_valid:
            error_embed = discord.Embed(
                title="❌ Invalid User ID",
                description=f"**Error:** {error}\n\nPlease try again with a valid User ID.",
                color=discord.Color.red()
            )
            await send_ephemeral_response(
                interaction,
                embed=error_embed,
                view=ErrorView(error, current_input)
            )
            return

        # Validate BattleTag
        is_valid, error = validation_service.validate_battle_tag(self.battle_tag.value)
        if not is_valid:
            error_embed = discord.Embed(
                title="❌ Invalid BattleTag",
                description=f"**Error:** {error}\n\nPlease try again with a valid BattleTag.",
                color=discord.Color.red()
            )
            await send_ephemeral_response(
                interaction,
                embed=error_embed,
                view=ErrorView(error, current_input)
            )
            return

        # Validate alternative IDs
        alt_ids_list = []
        
        # Validate alt_id_1 if provided
        if self.alt_id_1.value.strip():
            is_valid, error = validation_service.validate_user_id(self.alt_id_1.value.strip())
            if not is_valid:
                error_embed = discord.Embed(
                    title="❌ Invalid Alternative ID 1",
                    description=f"**Error:** {error}\n\nPlease try again with a valid Alternative ID.",
                    color=discord.Color.red()
                )
                await send_ephemeral_response(
                    interaction,
                    embed=error_embed,
                    view=ErrorView(error, current_input)
                )
                return
            alt_ids_list.append(self.alt_id_1.value.strip())
        
        # Validate alt_id_2 if provided
        if self.alt_id_2.value.strip():
            is_valid, error = validation_service.validate_user_id(self.alt_id_2.value.strip())
            if not is_valid:
                error_embed = discord.Embed(
                    title="❌ Invalid Alternative ID 2",
                    description=f"**Error:** {error}\n\nPlease try again with a valid Alternative ID.",
                    color=discord.Color.red()
                )
                await send_ephemeral_response(
                    interaction,
                    embed=error_embed,
                    view=ErrorView(error, current_input)
                )
                return
            alt_ids_list.append(self.alt_id_2.value.strip())
        
        # Check for duplicate IDs
        all_ids = [self.user_id.value] + alt_ids_list
        if len(all_ids) != len(set(all_ids)):
            error_embed = discord.Embed(
                title="❌ Duplicate IDs",
                description="**Error:** All IDs must be unique.\n\nPlease ensure each ID is different from the others.",
                color=discord.Color.red()
            )
            await send_ephemeral_response(
                interaction,
                embed=error_embed,
                view=ErrorView("Duplicate IDs detected", current_input)
            )
            return

        # Get existing country and region data for presets
        existing_country = None
        existing_region = None
        country_page1_selection = None
        country_page2_selection = None
        
        if self.existing_data:
            existing_country_code = self.existing_data.get('country')
            existing_region_code = self.existing_data.get('region')
            
            if existing_country_code:
                try:
                    # Try to find the country in common countries
                    existing_country = next(
                        (c for c in countries_service.get_common_countries() 
                         if c['code'] == existing_country_code), 
                        None
                    )
                    if existing_country:
                        # Check which page the country is on
                        common_countries = countries_service.get_common_countries()
                        country_index = next(
                            (i for i, c in enumerate(common_countries) if c['code'] == existing_country_code), 
                            -1
                        )
                        if country_index >= 0:
                            if country_index < 25:
                                country_page1_selection = existing_country_code
                            else:
                                country_page2_selection = existing_country_code
                except:
                    # If country is not in common countries, default to "Other"
                    existing_country = next(
                        (c for c in countries_service.get_common_countries() 
                         if c['code'] == 'ZZ'), 
                        None
                    )
                    if existing_country:
                        country_page2_selection = 'ZZ'
            
            if existing_region_code:
                existing_region = next(
                    (r for r in regions_service.get_all_regions() 
                     if r['code'] == existing_region_code), 
                    None
                )
        
        # Store data and show unified selection view
        view = UnifiedSetupView(
            user_id=self.user_id.value,
            alt_ids=alt_ids_list,
            battle_tag=self.battle_tag.value,
            selected_country=existing_country,
            selected_region=existing_region,
            country_page1_selection=country_page1_selection,
            country_page2_selection=country_page2_selection
        )
        
        # Create initial blue embed
        initial_embed = discord.Embed(
            title="⚙️ Setup - Country & Region Selection",
            description=f"Please select your country and region.\n\n**Due to Discord UI limitations, we list only 49 countries here.**\n- If your country is not listed, please select \"Other\" at the bottom of Page 2, then select your exact country later with `/setcountry`.\n- If you are not a citizen of, or are choosing not to represent, any particular nation, please select \"Other\" at the bottom of Page 2, then select \"Non-representing\" as your country later with `/setcountry`.",
            color=discord.Color.blue()
        )
        
        await send_ephemeral_response(
            interaction,
            embed=initial_embed,
            view=view
        )

class ErrorView(discord.ui.View):
    def __init__(self, error_message: str, existing_data: Optional[dict] = None) -> None:
        super().__init__(timeout=GLOBAL_TIMEOUT)
        self.error_message = error_message
        self.existing_data = existing_data or {}
        
        # Add restart and cancel buttons only
        buttons = ConfirmRestartCancelButtons.create_buttons(
            reset_target=SetupModal(existing_data=self.existing_data),
            restart_label="Try Again",
            cancel_label="Cancel",
            show_cancel_fields=False,
            include_confirm=False,
            include_restart=True,
            include_cancel=True
        )
        
        for button in buttons:
            self.add_item(button)

class CountryPage1Select(discord.ui.Select):
    def __init__(self, countries, selected_country=None):
        # Countries 1-25 (indices 0-24)
        page_countries = countries[:25]
        options = [
            discord.SelectOption(
                label=country['name'],
                value=country['code'],
                emoji=get_flag_emote(country['code']),
                default=(country['code'] == selected_country)
            )
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
    def __init__(self, countries, selected_country=None):
        # Countries 26-50 (indices 25-49)
        page_countries = countries[25:50] if len(countries) > 25 else []
        options = [
            discord.SelectOption(
                label=country['name'],
                value=country['code'],
                emoji=get_flag_emote(country['code']),
                default=(country['code'] == selected_country)
            )
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
    def __init__(self, regions, selected_region=None):
        options = [
            discord.SelectOption(
                label=region['name'], 
                value=region['code'],
                default=(region['code'] == selected_region)
            )
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
    def __init__(self, user_id: str, alt_ids: list, battle_tag: str, selected_country=None, selected_region=None, country_page1_selection=None, country_page2_selection=None):
        super().__init__(timeout=GLOBAL_TIMEOUT)
        self.user_id = user_id
        self.alt_ids = alt_ids
        self.battle_tag = battle_tag
        self.selected_country = selected_country
        self.selected_region = selected_region
        
        # Track which country page has a selection (for mutual exclusion)
        self.country_page1_selection = country_page1_selection
        self.country_page2_selection = country_page2_selection
        
        # Get countries and regions
        self.countries = countries_service.get_common_countries()
        self.regions = regions_service.get_all_regions()
        
        # Create dropdowns with current selections
        self.country_page1_select = CountryPage1Select(self.countries, self.country_page1_selection)
        self.country_page2_select = CountryPage2Select(self.countries, self.country_page2_selection)
        self.region_select = RegionSelect(self.regions, self.selected_region['code'] if self.selected_region else None)
        
        # Add dropdowns to view
        self.add_item(self.country_page1_select)
        self.add_item(self.country_page2_select)
        self.add_item(self.region_select)
        
        # Prepare existing data for restart button
        existing_data = {
            'player_name': self.user_id,
            'battletag': self.battle_tag,
            'alt_player_name_1': self.alt_ids[0] if len(self.alt_ids) > 0 else '',
            'alt_player_name_2': self.alt_ids[1] if len(self.alt_ids) > 1 else '',
            'country': self.selected_country['code'] if self.selected_country else '',
            'region': self.selected_region['code'] if self.selected_region else ''
        }
        
        # Add action buttons using the unified approach
        buttons = ConfirmRestartCancelButtons.create_buttons(
            confirm_callback=self.confirm_callback,
            reset_target=SetupModal(existing_data=existing_data),
            confirm_label="Confirm",
            restart_label="Restart", 
            cancel_label="Cancel",
            show_cancel_fields=False,
            row=3,
            include_confirm=True,
            include_restart=True,
            include_cancel=True
        )
        
        for button in buttons:
            self.add_item(button)

    async def update_view(self, interaction: discord.Interaction):
        """Update the view with current selections"""
        # Create a new view with current selections to maintain state
        new_view = UnifiedSetupView(
            self.user_id, 
            self.alt_ids, 
            self.battle_tag,
            selected_country=self.selected_country,
            selected_region=self.selected_region,
            country_page1_selection=self.country_page1_selection,
            country_page2_selection=self.country_page2_selection
        )
        
        await interaction.response.edit_message(
            embed=new_view.get_status_embed(),
            view=new_view
        )

    def get_status_embed(self) -> discord.Embed:
        """Get status embed based on current selections"""
        embed = discord.Embed(
            title="⚙️ Setup - Country & Region Selection",
            color=discord.Color.blue()
        )
        
        if self.selected_country and self.selected_region:
            embed.description = (
                f"**Selected:**\n"
                f"- Country of citizenship/nationality: {get_flag_emote(self.selected_country['code'])} {self.selected_country['name']}\n"
                f"- Region of residency: {self.selected_region['name']}\n\n"
                "Click Confirm to proceed."
            )
        elif self.selected_country:
            embed.description = (
                f"**Selected:**\n"
                f"- Country of citizenship/nationality: {get_flag_emote(self.selected_country['code'])} {self.selected_country['name']}\n\n"
                "Please select your region of residency."
            )
        elif self.selected_region:
            embed.description = (
                f"**Selected:**\n"
                f"- Region of residency: {self.selected_region['name']}\n\n"
                f"Please select your country and region.\n\n**Due to Discord UI limitations, we list only 49 countries here.**\n- If your country is not listed, please select \"Other\" at the bottom of Page 2, then select your exact country later with `/setcountry`.\n- If you are not a citizen of, or are choosing not to represent, any particular nation, please select \"Other\" at the bottom of Page 2, then select \"Non-representing\" as your country later with `/setcountry`."
            )
        else:
            embed.description =f"Please select your country and region.\n\n**Due to Discord UI limitations, we list only 49 countries here.**\n- If your country is not listed, please select \"Other\" at the bottom of Page 2, then select your exact country later with `/setcountry`.\n- If you are not a citizen of, or are choosing not to represent, any particular nation, please select \"Other\" at the bottom of Page 2, then select \"Non-representing\" as your country later with `/setcountry`."
        
        return embed

    async def confirm_callback(self, interaction: discord.Interaction):
        """Handle confirm button press"""
        if not self.selected_country or not self.selected_region:
            error_embed = discord.Embed(
                title="⚙️ Setup - Country & Region Selection",
                description="❌ Please select both country and region before confirming.",
                color=discord.Color.red()
            )
            
            # Create custom error view that restarts to country/region selection
            class SetupErrorView(discord.ui.View):
                def __init__(self, original_view):
                    super().__init__(timeout=GLOBAL_TIMEOUT)
                    self.original_view = original_view
                
                @discord.ui.button(emote="🔄", label="Try Again", style=discord.ButtonStyle.secondary)
                async def restart(self, interaction: discord.Interaction, button: discord.ui.Button):
                    # Go back to the country/region selection view
                    embed = self.original_view.get_embed()
                    await interaction.response.edit_message(embed=embed, view=self.original_view)
                
                @discord.ui.button(emote="❌", label="Cancel", style=discord.ButtonStyle.danger)
                async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                    await send_ephemeral_response(
                        interaction,
                        content="Setup cancelled. You can use `/setup` again when ready."
                    )
            
            error_view = SetupErrorView(self)
            
            await send_ephemeral_response(
                interaction,
                embed=error_embed,
                view=error_view
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
        (":map: **Region of Residency**", region['name'])
    ]
    
    if alt_ids:
        alt_ids_str = ", ".join(alt_ids)
        fields.append((":id: **Alternative IDs**", alt_ids_str))
    else:
        fields.append((":id: **Alternative IDs**", "None"))
    
    # Prepare existing data for restart button
    existing_data = {
        'player_name': user_id,
        'battletag': battle_tag,
        'alt_player_name_1': alt_ids[0] if len(alt_ids) > 0 else '',
        'alt_player_name_2': alt_ids[1] if len(alt_ids) > 1 else '',
        'country': country['code'],
        'region': region['code']
    }
    
    # Define confirmation callback
    async def confirm_callback(interaction: discord.Interaction):
        # CRITICAL: Defer immediately to prevent timeout (gives 15 minutes instead of 3 seconds)
        await interaction.response.defer()
        
        user_info = get_user_info(interaction)
        
        # Send data to backend
        # Always pass alt names (empty string if not provided) to ensure clearing is recorded
        success = user_info_service.complete_setup(
            discord_uid=user_info["id"],
            player_name=user_id,
            battletag=battle_tag,
            alt_player_name_1=alt_ids[0] if len(alt_ids) > 0 else "",
            alt_player_name_2=alt_ids[1] if len(alt_ids) > 1 else "",
            country=country['code'],
            region=region['code']
        )
        
        if not success:
            error_embed = discord.Embed(
                title="❌ Setup Failed",
                description="An error occurred while saving your profile. Please try again.",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(
                embed=error_embed,
                view=None
            )
            return
        
        # Log the setup
        log_user_action(user_info, "completed player setup", 
                       f"User ID: {user_id}, Country: {country['name']}, Region: {region['name']}")
        
        # Show post-confirmation view
        post_confirm_view = ConfirmEmbedView(
            title="Setup Complete!",
            description="Your player profile has been successfully configured:",
            fields=fields,
            mode="post_confirmation",
            reset_target=SetupModal(existing_data=user_info_service.get_player(user_info["id"])),
            restart_label="🔄 Setup Again"
        )
        
        
        await interaction.edit_original_response(
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
        reset_target=SetupModal(existing_data=existing_data)
    )