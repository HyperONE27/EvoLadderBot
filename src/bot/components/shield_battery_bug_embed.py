import discord
from src.backend.services.app_context import data_access_service
from src.bot.utils.message_helpers import queue_interaction_edit
from src.bot.config import GLOBAL_TIMEOUT


class ShieldBatteryBugView(discord.ui.View):
    """View for the shield battery bug notification."""
    
    def __init__(self, discord_uid: int):
        super().__init__(timeout=GLOBAL_TIMEOUT)
        self.discord_uid = discord_uid
        
        # Add the confirm button
        self.add_item(ShieldBatteryBugButton(self))


class ShieldBatteryBugButton(discord.ui.Button):
    """Button to acknowledge the shield battery bug warning."""
    
    def __init__(self, parent_view: ShieldBatteryBugView):
        super().__init__(
            label="I Understand",
            style=discord.ButtonStyle.success,
            emoji="✅",
            row=0
        )
        self.parent_view = parent_view
    
    async def callback(self, interaction: discord.Interaction):
        """Handle button click - uses interaction queue for immediate response."""
        # Update button to acknowledged state
        self.disabled = True
        self.style = discord.ButtonStyle.secondary
        self.label = "Acknowledged"
        
        # Update in database
        await data_access_service.set_shield_battery_bug(self.parent_view.discord_uid, True)
        
        # Get current embed and add confirmation field
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.add_field(
                name="✅ Acknowledged",
                value=f"<@{self.parent_view.discord_uid}> has acknowledged this information.",
                inline=False
            )
        
        # Update the message using interaction queue (high priority)
        await queue_interaction_edit(interaction, embed=embed, view=self.parent_view)


def create_shield_battery_bug_embed() -> discord.Embed:
    """Create the shield battery bug notification embed."""
    embed = discord.Embed(
        title="⚠️ Shield Battery Bug",
        description="Placeholder description about the shield battery bug.",
        color=discord.Color.orange()
    )
    return embed

