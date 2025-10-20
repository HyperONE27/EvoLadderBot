import discord
from typing import Optional, Union, Callable
from .confirm_restart_cancel_buttons import ConfirmRestartCancelButtons


class ConfirmEmbedView(discord.ui.View):
    """
    Flexible confirmation dialog with preview and post-confirmation modes.
    - Preview mode: Shows data with Confirm, Restart, and Cancel buttons
    - Post-confirmation mode: Shows final confirmation that everything is set
    """

    def __init__(
        self,
        title: str,
        description: str = "",
        fields: list[tuple[str, str]] = None,
        mode: str = "preview",  # "preview" or "post_confirmation"
        reset_target: Optional[Union[discord.ui.View, discord.ui.Modal]] = None,
        confirm_callback: Optional[Callable] = None,
        restart_label: str = "Restart",
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
        color: discord.Color = None  # Will be set based on mode
    ):
        super().__init__(timeout=300)
        
        self.mode = mode
        self.reset_target = reset_target
        self.confirm_callback = confirm_callback
        self.fields = fields or []
        
        # Set color based on mode if not provided
        if color is None:
            color = discord.Color.blue() if mode == "preview" else discord.Color.green()
        
        # Add appropriate emote to title based on mode
        if mode == "preview":
            title = f"🔍 {title}"
        elif mode == "post_confirmation":
            title = f"✅ {title}"
        
        # Build the embed
        self.embed = discord.Embed(title=title, description=description, color=color)
        for name, value in self.fields:
            # Automatically format values with code blocks for better readability
            formatted_value = f"`{value}`" if value else "`None`"
            self.embed.add_field(name=name, value=formatted_value, inline=False)
        
        # Add appropriate buttons based on mode
        if mode == "preview":
            # Preview mode: Confirm, Restart, Cancel
            buttons = ConfirmRestartCancelButtons.create_buttons(
                confirm_callback=confirm_callback,
                reset_target=reset_target,
                confirm_label=confirm_label,
                restart_label=restart_label,
                cancel_label=cancel_label,
                show_cancel_fields=True,
                include_confirm=bool(confirm_callback),
                include_restart=bool(reset_target),
                include_cancel=bool(reset_target)
            )
            
            for button in buttons:
                self.add_item(button)
        elif mode == "post_confirmation":
            # Post-confirmation mode: No buttons - this is the end of the interaction
            pass