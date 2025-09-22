import discord
from discord import app_commands
from src.utils.country_region_utils import CountryLookup
from src.utils.user_utils import get_user_info, log_user_action
from components.confirm_embed import ConfirmEmbedView

country_lookup = CountryLookup()


# API Call / Data Handling
async def country_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for country names"""
    if not current:
        # Show first 25 countries if nothing typed
        countries = country_lookup.get_sorted_countries()[:25]
    else:
        # Search for matching countries
        countries = country_lookup.search_countries(current, limit=25)
    
    return [
        app_commands.Choice(name=country['name'], value=country['code'])
        for country in countries
    ]


async def setcountry_command(interaction: discord.Interaction, country_code: str):
    """Set or update your country"""
    country = country_lookup.get_country_by_code(country_code)
    
    if not country:
        await interaction.response.send_message(
            "❌ Invalid country selection.",
            ephemeral=True
        )
        return
    
    # Get user information using utility function
    user_info = get_user_info(interaction)
    
    # Show preview with confirm/restart/cancel options
    async def confirm_callback(interaction: discord.Interaction):
        # TODO: Update in backend with user ID
        # async with aiohttp.ClientSession() as session:
        #     await session.patch(
        #         f'http://backend/api/players/{user_info["id"]}',
        #         json={'country': country_code, 'discord_user_id': user_info["id"]}
        #     )
        
        # Log the action using utility function
        log_user_action(user_info, "set country", f"to {country['name']} ({country_code})")
        
        # Show post-confirmation view
        post_confirm_view = ConfirmEmbedView(
            title="Country Updated",
            description=f"Your country has been successfully set to **{country['name']}** ({country_code})",
            fields=[
                (":map: **Selected Country**", f"{country['name']} ({country_code})")
            ],
            mode="post_confirmation",
            reset_target=None,  # No restart option for country setting
            restart_label="🔄 Change Country"
        )
        await interaction.response.edit_message(embed=post_confirm_view.embed, view=post_confirm_view)
    
    # Create a simple view for the reset target (just show the command again)
    class CountryResetView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
        
        @discord.ui.button(label="🔄 Try Again", style=discord.ButtonStyle.secondary)
        async def retry(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message(
                "Please use `/setcountry` command again to select a different country.",
                ephemeral=True
            )
    
    confirm_view = ConfirmEmbedView(
        title="Preview Country Selection",
        description="Please review your country selection before confirming:",
        fields=[
            (":map: **Country of Citizenship/Nationality**", f"{country['name']}"),
        ],
        mode="preview",
        confirm_callback=confirm_callback,
        reset_target=CountryResetView()
    )
    
    await interaction.response.send_message(embed=confirm_view.embed, view=confirm_view, ephemeral=True)


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