import discord
from discord import app_commands
from src.utils.data_loader import DataLoader

data_loader = DataLoader()

async def country_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Autocomplete for country names"""
    if not current:
        # Show first 25 countries if nothing typed
        countries = data_loader.get_all_countries()[:25]
    else:
        # Search for matching countries
        countries = data_loader.search_countries(current, limit=25)
    
    return [
        app_commands.Choice(name=country['name'], value=country['code'])
        for country in countries
    ]


async def setcountry_command(interaction: discord.Interaction, country_code: str):
    """Set or update your country"""
    country = data_loader.get_country_by_code(country_code)
    
    if not country:
        await interaction.response.send_message(
            "❌ Invalid country selection.",
            ephemeral=True
        )
        return
    
    # TODO: Update in backend
    # async with aiohttp.ClientSession() as session:
    #     await session.patch(
    #         f'http://backend/api/players/{interaction.user.id}',
    #         json={'country': country_code}
    #     )
    
    embed = discord.Embed(
        title="✅ Country Updated",
        description=f"Your country has been set to **{country['name']}** ({country_code})",
        color=discord.Color.green()
    )
    
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
