from discord import Interaction
from src.bot.interface.interface_views import LadderSetupView, SetupView, PageOneView

def register_commands(bot):
    @bot.tree.command(name="setup", description="Configure your ladder profile")
    async def setup(interaction: Interaction):
        await interaction.response.send_message(
            "⚙️ Configure your settings below:",
            view=LadderSetupView(),
            ephemeral=True
        )

    @bot.tree.command(name="setup2", description="Extended setup with advanced UI")
    async def setup2(interaction: Interaction):
        await interaction.response.send_message(
            "⚙️ **Extended Setup**\nSelect game modes, pick a faction, confirm/cancel, or add notes:",
            view=SetupView(),
            ephemeral=True
        )

    @bot.tree.command(name="setup3", description="Paginated setup flow")
    async def setup3(interaction: Interaction):
        await interaction.response.send_message(
            "⚙️ Setup (Page 1)",
            view=PageOneView(),
            ephemeral=True
        )
