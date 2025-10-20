import discord
from discord import app_commands
import re
from typing import Optional
from src.backend.services import (
    command_guard_service,
    user_info_service,
    countries_service,
    regions_service,
    validation_service
)
from src.backend.services.command_guard_service import CommandGuardError
from src.backend.services.user_info_service import get_user_info, log_user_action
from src.bot.utils.discord_utils import send_ephemeral_response, get_flag_emote
from src.bot.interface.components.confirm_embed import ConfirmEmbedView
from src.bot.interface.components.confirm_restart_cancel_buttons import ConfirmRestartCancelButtons
from src.bot.interface.components.command_guard_embeds import create_command_guard_error_embed
from src.bot.config import GLOBAL_TIMEOUT

# --- Command Registration ---
def register_setup_command(tree: app_commands.CommandTree):
    """Register the setup command"""
    @tree.command(
        name="setup",
        description="Set up your player profile for matchmaking"
    )
    async def setup(interaction: discord.Interaction):
        await setup_command(interaction)
    
    return setup


# --- UI Views ---

class SetupView(discord.ui.View):
    """Main setup view for the /setup command."""

    def __init__(self, user_info: dict, original_interaction: discord.Interaction):
        super().__init__(timeout=GLOBAL_TIMEOUT)
        self.user_info = user_info
        self.original_interaction = original_interaction
        self.selected_country: Optional[str] = user_info.get("country")
        self.selected_region: Optional[str] = user_info.get("region")
        self.player_name: Optional[str] = user_info.get("player_name")
        self.battletag: Optional[str] = user_info.get("battletag")
        self.alt_name_1: Optional[str] = user_info.get("alt_player_name_1")
        self.alt_name_2: Optional[str] = user_info.get("alt_player_name_2")

        # Add components
        self.add_item(ConfirmButton(self.confirm_callback))
        self.add_item(CancelButton(self.cancel_callback))
        self.add_item(PlayerNameButton())
        self.add_item(RegionSelect(regions_service.get_regions(), default_value=self.selected_region))
        self.add_item(CountrySelect(countries_service.get_countries(), default_value=self.selected_country))

    async def confirm_callback(self, interaction: discord.Interaction):
        """Callback for the confirm button."""
        await interaction.response.defer()

        # Validation
        errors = validation_service.validate_setup_data(
            player_name=self.player_name,
            country=self.selected_country,
            region=self.selected_region,
            battletag=self.battletag,
            alt_name_1=self.alt_name_1,
            alt_name_2=self.alt_name_2,
        )

        if errors:
            error_embed = discord.Embed(
                title="❌ Setup Failed",
                description="\n".join(errors),
                color=discord.Color.red()
            )
            await send_ephemeral_response(
                interaction,
                embed=error_embed,
                view=self
            )
            return

        # Persist data
        success = user_info_service.complete_setup(
            discord_uid=self.user_info["id"],
            player_name=self.player_name,
            battletag=self.battletag,
            alt_player_name_1=self.alt_name_1,
            alt_player_name_2=self.alt_name_2,
            country=self.selected_country,
            region=self.selected_region
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
        log_user_action(self.user_info, "completed player setup", 
                       f"User ID: {self.player_name}, Country: {self.selected_country}, Region: {self.selected_region}")
        
        # Show post-confirmation view
        post_confirm_view = ConfirmEmbedView(
            title="Setup Complete!",
            description="Your player profile has been successfully configured:",
            fields=[
                (":id: **User ID**", self.player_name),
                (":hash: **BattleTag**", self.battletag),
                (":map: **Country of Citizenship/Nationality**", self.selected_country),
                (":map: **Region of Residency**", self.selected_region)
            ],
            mode="post_confirmation",
            reset_target=SetupView(user_info_service.get_full_user_info(self.user_info["id"]), self.original_interaction),
            restart_label="🔄 Setup Again"
        )
        
        
        await interaction.edit_original_response(
            content="",
            embed=post_confirm_view.embed,
            view=post_confirm_view
        )

    async def cancel_callback(self, interaction: discord.Interaction):
        """Callback for the cancel button."""
        await send_ephemeral_response(
            interaction,
            content="Setup cancelled. You can use `/setup` again when ready."
        )


class PlayerNameButton(discord.ui.Button):
    """Button to input player name."""

    def __init__(self):
        super().__init__(
            label="Enter Player Name",
            style=discord.ButtonStyle.primary,
            emoji=":id:",
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PlayerNameModal(self.view.user_info))


class PlayerNameModal(discord.ui.Modal, title="Enter Player Name"):
    """Modal to input player name."""

    def __init__(self, user_info: dict):
        super().__init__(timeout=GLOBAL_TIMEOUT)
        self.user_info = user_info
        self.player_name_input = discord.ui.TextInput(
            label="Player Name",
            placeholder="Enter your player name (3-12 characters)",
            default=user_info.get("player_name", ""),
            min_length=3,
            max_length=12,
            required=True
        )
        self.add_item(self.player_name_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view.player_name = self.player_name_input.value
        self.view.add_item(RegionSelect(regions_service.get_regions(), default_value=self.view.selected_region))
        self.view.add_item(CountrySelect(countries_service.get_countries(), default_value=self.view.selected_country))
        await interaction.response.edit_message(
            embed=self.view.get_embed(),
            view=self.view
        )


class CountrySelect(discord.ui.Select):
    """Dropdown to select country"""

    def __init__(self, countries: list, default_value: Optional[str] = None):
        options = [
            discord.SelectOption(
                label=country["name"],
                value=country["code"],
                default=country["code"] == default_value
            ) for country in countries
        ]
        super().__init__(placeholder="Select your country of citizenship/nationality", options=options, row=4)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_country = self.values[0]
        await self.view.update_view(interaction)


class RegionSelect(discord.ui.Select):
    """Dropdown to select region"""
    def __init__(self, regions: list, default_value: Optional[str] = None):
        options = [
            discord.SelectOption(
                label=region["name"],
                value=region["code"],
                default=region["code"] == default_value
            ) for region in regions
        ]
        super().__init__(placeholder="Select your region of residence", options=options, row=3)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_region = self.values[0]
        await self.view.update_view(interaction)


class ConfirmButton(discord.ui.Button):
    """Button to confirm setup."""

    def __init__(self, callback):
        super().__init__(
            label="Confirm Setup",
            style=discord.ButtonStyle.success,
            emoji="✅",
            row=2
        )
        self.callback = callback

    async def callback(self, interaction: discord.Interaction):
        await self.callback(interaction)


class CancelButton(discord.ui.Button):
    """Button to cancel setup."""

    def __init__(self, callback):
        super().__init__(
            label="Cancel Setup",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            row=2
        )
        self.callback = callback

    async def callback(self, interaction: discord.Interaction):
        await self.callback(interaction)


class ErrorView(discord.ui.View):
    def __init__(self, error_message: str, existing_data: Optional[dict] = None) -> None:
        super().__init__(timeout=GLOBAL_TIMEOUT)
        self.error_message = error_message
        self.existing_data = existing_data or {}
        
        # Add restart and cancel buttons only
        buttons = ConfirmRestartCancelButtons.create_buttons(
            reset_target=SetupView(user_info_service.get_full_user_info(self.existing_data.get("id")), None), # Pass None for original_interaction
            restart_label="Try Again",
            cancel_label="Cancel",
            show_cancel_fields=False,
            include_confirm=False,
            include_restart=True,
            include_cancel=True
        )
        
        for button in buttons:
            self.add_item(button)


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
            reset_target=SetupView(user_info_service.get_full_user_info(user_info["id"]), None), # Pass None for original_interaction
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
        reset_target=SetupView(user_info_service.get_full_user_info(user_info["id"]), None) # Pass None for original_interaction
    )