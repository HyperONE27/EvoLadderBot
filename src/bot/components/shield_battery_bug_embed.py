import discord
from src.backend.services.app_context import data_access_service
from src.bot.utils.message_helpers import queue_interaction_edit
from src.bot.config import GLOBAL_TIMEOUT
from src.bot.utils.discord_utils import get_race_emote


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
        
        # Cleanup after acknowledgment
        self.parent_view.stop()
        self.parent_view.clear_items()
        print(f"🧹 [ShieldBatteryBugView] Cleaned up after acknowledgment from {self.parent_view.discord_uid}")


def create_shield_battery_bug_embed() -> discord.Embed:
    """Create the shield battery bug notification embed."""
    embed = discord.Embed(
        title="⚠️ Shield Battery Bug",
        description=(
            f"We detected your match contains a {get_race_emote("bw_protoss")} Brood War Protoss player.\n\n"
            "We are currently aware of an issue where the Brood War Shield Battery causes **intense lag**. "
            "This issue is caused by the Shield Battery's splat model size being set too large.\n\n"
            "You can solve this issue in one of two ways:\n"
            "- 1. Go to Options > Graphics > set Effects to **Low**.\n"
            "- 2. Use this program to automatically set `splatlod=0` in all of your `Variables.txt` files: https://drive.google.com/file/d/1D-x27NZsGuK391mWcBHefOM4SfE0JuZh/view?usp=drive_link\n\n"
            "Then, ***RESTART YOUR GAME***. It will no longer render the Shield Battery's splat model.\n\n"
            "Thank you for your understanding. We will resolve this issue when Blizzard re-enables uploading to the Battle.net servers."
        ),
        color=discord.Color.orange()
    )
    return embed

