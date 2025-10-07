import discord
from discord import app_commands
import os
from src.backend.services.countries_service import CountriesService
from src.backend.services.command_guard_service import CommandGuardService, CommandGuardError
from src.backend.services.user_info_service import UserInfoService, get_user_info, log_user_action
from src.bot.utils.discord_utils import send_ephemeral_response
from src.bot.interface.components.confirm_embed import ConfirmEmbedView
from src.bot.interface.components.confirm_restart_cancel_buttons import ConfirmButton, CancelButton

countries_service = CountriesService()
user_info_service = UserInfoService()
guard_service = CommandGuardService()

# Get global timeout from environment
GLOBAL_TIMEOUT = int(os.getenv('GLOBAL_TIMEOUT'))


# API Call / Data Handling
async def country_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for country names"""
    if not current:
        # Show first 25 countries if nothing typed
        countries = countries_service.get_sorted_countries()[:25]
    else:
        # Search for matching countries
        countries = countries_service.search_countries(current, limit=25)
    
    return [
        app_commands.Choice(name=country['name'], value=country['code'])
        for country in countries
    ]


async def setcountry_command(interaction: discord.Interaction, country_code: str):
    """Set or update your country"""
    try:
        player = guard_service.ensure_player_record(interaction.user.id, interaction.user.name)
        guard_service.require_tos_accepted(player)
    except CommandGuardError as exc:
        await send_ephemeral_response(interaction, content=str(exc))
        return
    
    country = countries_service.get_country_by_code(country_code)
    
    # If no exact match by code, try to find by name (fallback for early Enter)
    if not country:
        # Search for countries that match the input as a name
        search_results = countries_service.search_countries(country_code, limit=1)
        if search_results:
            # Use the first search result as a fallback
            country = search_results[0]
            country_code = country['code']  # Update to use the correct code
        else:
            error_embed = discord.Embed(
                title="❌ Invalid Country Selection",
                description="The selected country is not valid. Please try again with a different country.\n\n(If you are sure your country is valid, please ensure you are waiting for Discord's UI to load your country before selecting it and pressing Enter.)",
                color=discord.Color.red()
            )
            await send_ephemeral_response(
                interaction,
                embed=error_embed
            )
            return
    
    # Get user information using utility function
    user_info = get_user_info(interaction)
    
    # Show preview with confirm/cancel options only
    async def confirm_callback(interaction: discord.Interaction):
        # Update in backend with user ID
        success = user_info_service.update_country(user_info["id"], country_code)
        
        if not success:
            error_embed = discord.Embed(
                title="❌ Update Failed",
                description="An error occurred while updating your country. Please try again.",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(
                embed=error_embed,
                view=None
            )
            return
        
        # Log the action using utility function
        log_user_action(user_info, "set country", f"to {country['name']} ({country_code})")
        
        # Show post-confirmation view
        post_confirm_view = ConfirmEmbedView(
            title="Country Updated",
            description=f"Your country has been successfully set to **{country['name']}** ({country_code})",
            fields=[
                (":map: **Selected Country**", f"{country['name']} ({country_code})")
            ],
            mode="post_confirmation"
        )
        await interaction.response.edit_message(embed=post_confirm_view.embed, view=post_confirm_view)
    
    # Create a simple view for the cancel target (just show the command again)
    class CountryCancelView(discord.ui.View):
        def __init__(self) -> None:
            super().__init__(timeout=GLOBAL_TIMEOUT)
        
        @discord.ui.button(label="Try Again", emoji="🔄", style=discord.ButtonStyle.secondary)
        async def retry(self, interaction: discord.Interaction, button: discord.ui.Button):
            await send_ephemeral_response(
                interaction,
                content="Please use `/setcountry` command again to select a different country."
            )
    
    # Create custom view with only confirm and cancel buttons
    class CountryConfirmView(discord.ui.View):
        def __init__(self) -> None:
            super().__init__(timeout=GLOBAL_TIMEOUT)
            self.add_item(ConfirmButton(confirm_callback, "Confirm"))
            self.add_item(CancelButton(CountryCancelView(), "Cancel"))
    
    # Create the embed
    embed = discord.Embed(
        title="🔍 Preview Country Selection",
        description="Please review your country selection before confirming:",
        color=discord.Color.blue()
    )
    embed.add_field(
        name=":map: **Country of Citizenship/Nationality**",
        value=f"{country['name']}",
        inline=False
    )
    
    confirm_view = CountryConfirmView()
    
    await send_ephemeral_response(interaction, embed=embed, view=confirm_view)


# Register Command
def register_setcountry_command(tree: app_commands.CommandTree):
    """Register the setcountry command"""
    @tree.command(
        name="setcountry",
        description="Set or update your country"
    )
    @app_commands.autocomplete(country=country_autocomplete)
    async def setcountry(interaction: discord.Interaction, country: str):
        await setcountry_command(interaction, country)
    
    return setcountry