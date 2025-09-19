import discord
from discord import app_commands
from src.utils.country_region_utils import CountryLookup
from src.utils.user_utils import get_user_info, create_user_embed_field, log_user_action

country_lookup = CountryLookup()

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
    
    # TODO: Update in backend with user ID
    # async with aiohttp.ClientSession() as session:
    #     await session.patch(
    #         f'http://backend/api/players/{user_info["id"]}',
    #         json={'country': country_code, 'discord_user_id': user_info["id"]}
    #     )
    
    embed = discord.Embed(
        title="✅ Country Updated",
        description=f"Your country has been set to **{country['name']}** ({country_code})",
        color=discord.Color.green()
    )
    
    # Add user information using utility function
    embed.add_field(**create_user_embed_field(user_info))
    
    # Log the action using utility function
    log_user_action(user_info, "set country", f"to {country['name']} ({country_code})")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


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