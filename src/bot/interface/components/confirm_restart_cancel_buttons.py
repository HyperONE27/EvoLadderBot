import discord
from typing import Optional, Union, Callable
from src.bot.utils.discord_utils import send_ephemeral_response
from src.bot.interface.components.cancel_embed import create_cancel_embed


class ConfirmButton(discord.ui.Button):
    """Generic confirm button with customizable callback."""
    
    def __init__(
        self,
        callback: Callable,
        label: str = "Confirm",
        style: discord.ButtonStyle = discord.ButtonStyle.success,
        row: int = 0
    ):
        super().__init__(label=label, style=style, emoji="✅", row=row)
        self.callback_func = callback

    async def callback(self, interaction: discord.Interaction):
        # Disable all buttons immediately to prevent double-clicks
        for item in self.view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        # Call the actual callback function (which will handle deferral and response)
        await self.callback_func(interaction)


class RestartButton(discord.ui.Button):
    """Generic restart button with customizable reset target."""
    
    def __init__(
        self,
        reset_target: Union[discord.ui.View, discord.ui.Modal],
        label: str = "Restart",
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        row: int = 0
    ):
        super().__init__(label=label, style=style, emoji="🔄", row=row)
        self.reset_target = reset_target

    async def callback(self, interaction: discord.Interaction):
        if isinstance(self.reset_target, discord.ui.View):
            # Defer to prevent timeout
            await interaction.response.defer()
            
            # Check if the view has a get_embed method to get the proper embed
            if hasattr(self.reset_target, 'get_embed'):
                embed = self.reset_target.get_embed()
                await interaction.edit_original_response(
                    content="",
                    embed=embed,
                    view=self.reset_target
                )
            else:
                await interaction.edit_original_response(
                    content="",
                    embed=None,
                    view=self.reset_target
                )
        elif isinstance(self.reset_target, discord.ui.Modal):
            # Modals must be sent immediately, no deferral
            await interaction.response.send_modal(self.reset_target)
        else:
            await send_ephemeral_response(
                interaction,
                content="⚠️ Nothing to restart to."
            )


class CancelButton(discord.ui.Button):
    """Generic cancel button with customizable behavior."""
    
    def __init__(
        self,
        reset_target: Union[discord.ui.View, discord.ui.Modal],
        label: str = "Cancel",
        style: discord.ButtonStyle = discord.ButtonStyle.danger,
        row: int = 0,
        show_fields: bool = True
    ):
        super().__init__(label=label, style=style, emoji="✖️", row=row)
        self.reset_target = reset_target
        self.show_fields = show_fields

    async def callback(self, interaction: discord.Interaction):
        # Defer to prevent timeout
        await interaction.response.defer()
        
        # Always use the cancel embed for consistency
        cancel_view = create_cancel_embed()
        
        await interaction.edit_original_response(
            content="",
            embed=cancel_view.embed,
            view=cancel_view
        )


class ConfirmRestartCancelButtons:
    """Helper class to create sets of confirm, restart, and cancel buttons."""
    
    @staticmethod
    def create_buttons(
        confirm_callback: Optional[Callable] = None,
        reset_target: Optional[Union[discord.ui.View, discord.ui.Modal]] = None,
        confirm_label: str = "Confirm",
        restart_label: str = "Restart",
        cancel_label: str = "Cancel",
        show_cancel_fields: bool = True,
        row: int = 0,
        include_confirm: bool = True,
        include_restart: bool = True,
        include_cancel: bool = True
    ) -> list[discord.ui.Button]:
        """Create a list of buttons based on provided parameters.
        
        Args:
            confirm_callback: Callback function for confirm button
            reset_target: Target for restart/cancel buttons
            confirm_label: Label for confirm button (emoji automatically added)
            restart_label: Label for restart button (emoji automatically added)
            cancel_label: Label for cancel button (emoji automatically added)
            show_cancel_fields: Whether to show fields in cancel embed
            row: Row position for buttons
            include_confirm: Whether to include confirm button
            include_restart: Whether to include restart button
            include_cancel: Whether to include cancel button
        """
        buttons = []
        
        if include_confirm and confirm_callback:
            buttons.append(ConfirmButton(confirm_callback, confirm_label, row=row))
        
        if include_restart and reset_target:
            buttons.append(RestartButton(reset_target, restart_label, row=row))
        
        if include_cancel and reset_target:
            buttons.append(CancelButton(reset_target, cancel_label, show_fields=show_cancel_fields, row=row))
        
        return buttons
