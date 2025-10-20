import discord
from typing import Optional, Union, Callable, Any
from src.bot.utils.discord_utils import send_ephemeral_response


class ErrorEmbedException(Exception):
    """
    Custom exception that triggers the error embed view.
    Contains all necessary information to display a user-friendly error message.
    """
    
    def __init__(
        self,
        title: str,
        description: str = "",
        error_fields: list[tuple[str, str]] = None,
        reset_target: Optional[Union[discord.ui.View, discord.ui.Modal]] = None,
        retry_callback: Optional[Callable] = None
    ):
        super().__init__(description)
        self.title = title
        self.description = description
        self.error_fields = error_fields or []
        self.reset_target = reset_target
        self.retry_callback = retry_callback


class ErrorEmbedView(discord.ui.View):
    """
    Generic error view with red color and red X emote.
    - Shows error information with customizable fields
    - Includes retry functionality if reset_target or retry_callback is provided
    - Provides clear error reporting to users
    """

    def __init__(
        self,
        title: str,
        description: str = "",
        error_fields: list[tuple[str, str]] = None,
        reset_target: Optional[Union[discord.ui.View, discord.ui.Modal]] = None,
        retry_callback: Optional[Callable] = None,
        retry_label: str = "Try Again",
        dismiss_label: str = "Dismiss"
    ):
        super().__init__(timeout=300)
        
        self.reset_target = reset_target
        self.retry_callback = retry_callback
        self.error_fields = error_fields or []
        
        # Build the error embed with red color and X emote
        self.embed = discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=discord.Color.red()
        )
        
        # Add error fields
        for name, value in self.error_fields:
            self.embed.add_field(name=name, value=value, inline=False)
        
        # Add appropriate buttons
        if retry_callback:
            self.add_item(RetryCallbackButton(retry_callback, retry_label))
        elif reset_target:
            self.add_item(RetryTargetButton(reset_target, retry_label))
        
        # Always add dismiss button
        self.add_item(DismissButton(dismiss_label))


class RetryCallbackButton(discord.ui.Button):
    """Button that calls a custom retry callback function."""
    
    def __init__(self, callback: Callable, label: str):
        super().__init__(emoji="🔄", label=label, style=discord.ButtonStyle.secondary)
        self.callback_func = callback

    async def callback(self, interaction: discord.Interaction):
        await self.callback_func(interaction)


class RetryTargetButton(discord.ui.Button):
    """Button that restarts to a specific view or modal."""
    
    def __init__(self, reset_target: Union[discord.ui.View, discord.ui.Modal], label: str):
        super().__init__(emoji="🔄", label=label, style=discord.ButtonStyle.secondary)
        self.reset_target = reset_target

    async def callback(self, interaction: discord.Interaction):
        if isinstance(self.reset_target, discord.ui.View):
            await interaction.response.edit_message(
                content="🔄 Retrying...",
                embed=None,
                view=self.reset_target
            )
        elif isinstance(self.reset_target, discord.ui.Modal):
            await interaction.response.send_modal(self.reset_target)
        else:
            await send_ephemeral_response(
                interaction,
                content="⚠️ Unable to retry - no valid target provided."
            )


class DismissButton(discord.ui.Button):
    """Button that dismisses the error message."""
    
    def __init__(self, label: str):
        super().__init__(emoji="✖️", label=label, style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="❌ Error dismissed.",
            embed=None,
            view=None
        )


def create_error_view_from_exception(error: ErrorEmbedException) -> ErrorEmbedView:
    """
    Create an ErrorEmbedView from an ErrorEmbedException.
    
    Args:
        error: The ErrorEmbedException containing error details
        
    Returns:
        ErrorEmbedView configured with the exception's data
    """
    return ErrorEmbedView(
        title=error.title,
        description=error.description,
        error_fields=error.error_fields,
        reset_target=error.reset_target,
        retry_callback=error.retry_callback
    )


def create_simple_error_view(
    title: str,
    description: str = "",
    error_fields: list[tuple[str, str]] = None,
    reset_target: Optional[Union[discord.ui.View, discord.ui.Modal]] = None
) -> ErrorEmbedView:
    """
    Create a simple error view without custom callbacks.
    
    Args:
        title: Error title
        description: Error description
        error_fields: List of (name, value) tuples for error details
        reset_target: Optional view or modal to restart to
        
    Returns:
        ErrorEmbedView configured with the provided data
    """
    return ErrorEmbedView(
        title=title,
        description=description,
        error_fields=error_fields or [],
        reset_target=reset_target
    )
