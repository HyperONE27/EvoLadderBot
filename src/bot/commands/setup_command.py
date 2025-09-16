import discord
from discord import app_commands
from src.bot.interface.setup_views import SetupModal

async def setup_command(interaction: discord.Interaction):
    """Main setup command handler"""
    # TODO: Check if user already has a profile
    # existing_profile = await check_existing_profile(interaction.user.id)
    # if existing_profile:
    #     await interaction.response.send_message(...)
    
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