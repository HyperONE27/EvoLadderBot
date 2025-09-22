import discord
from typing import Optional, Union, Callable


class ConfirmButton(discord.ui.Button):
    """Generic confirm button with customizable callback."""
    
    def __init__(
        self,
        callback: Callable,
        label: str = "✅ Confirm",
        style: discord.ButtonStyle = discord.ButtonStyle.success,
        row: int = 0
    ):
        super().__init__(label=label, style=style, row=row)
        self.callback_func = callback

    async def callback(self, interaction: discord.Interaction):
        await self.callback_func(interaction)


class RestartButton(discord.ui.Button):
    """Generic restart button with customizable reset target."""
    
    def __init__(
        self,
        reset_target: Union[discord.ui.View, discord.ui.Modal],
        label: str = "🔄 Restart",
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        row: int = 0
    ):
        super().__init__(label=label, style=style, row=row)
        self.reset_target = reset_target

    async def callback(self, interaction: discord.Interaction):
        if isinstance(self.reset_target, discord.ui.View):
            await interaction.response.edit_message(
                content="🔄 Restarted.",
                embed=None,
                view=self.reset_target
            )
        elif isinstance(self.reset_target, discord.ui.Modal):
            await interaction.response.send_modal(self.reset_target)
        else:
            await interaction.response.send_message(
                "⚠️ Nothing to restart to.",
                ephemeral=True
            )


class CancelButton(discord.ui.Button):
    """Generic cancel button with customizable behavior."""
    
    def __init__(
        self,
        reset_target: Union[discord.ui.View, discord.ui.Modal],
        label: str = "❌ Cancel",
        style: discord.ButtonStyle = discord.ButtonStyle.danger,
        row: int = 0,
        show_fields: bool = True
    ):
        super().__init__(label=label, style=style, row=row)
        self.reset_target = reset_target
        self.show_fields = show_fields

    async def callback(self, interaction: discord.Interaction):
        if self.show_fields:
            # Get the current embed and modify it to show cancellation
            current_embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
            
            # Create cancelled embed with same fields but different title/description
            cancel_embed = discord.Embed(
                title="❌ Operation Cancelled",
                description="The operation has been cancelled.",
                color=discord.Color.red()
            )
            
            # Copy all fields from the original embed
            for field in current_embed.fields:
                cancel_embed.add_field(
                    name=field.name,
                    value=field.value,
                    inline=field.inline
                )
            
            await interaction.response.edit_message(
                content="",
                embed=cancel_embed,
                view=None
            )
        else:
            # Simple cancellation without showing fields
            await interaction.response.edit_message(
                content="❌ Operation cancelled.",
                embed=None,
                view=None
            )


class ConfirmRestartCancelButtons:
    """Helper class to create sets of confirm, restart, and cancel buttons."""
    
    @staticmethod
    def create_buttons(
        confirm_callback: Optional[Callable] = None,
        reset_target: Optional[Union[discord.ui.View, discord.ui.Modal]] = None,
        confirm_label: str = "✅ Confirm",
        restart_label: str = "🔄 Restart",
        cancel_label: str = "❌ Cancel",
        show_cancel_fields: bool = True,
        row: int = 0
    ) -> list[discord.ui.Button]:
        """Create a list of buttons based on provided parameters."""
        buttons = []
        
        if confirm_callback:
            buttons.append(ConfirmButton(confirm_callback, confirm_label, row=row))
        
        if reset_target:
            buttons.append(RestartButton(reset_target, restart_label, row=row))
            buttons.append(CancelButton(reset_target, cancel_label, show_fields=show_cancel_fields, row=row))
        
        return buttons
