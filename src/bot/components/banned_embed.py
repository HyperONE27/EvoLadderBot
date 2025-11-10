import discord
from src.bot.components.confirm_restart_cancel_buttons import ConfirmRestartCancelButtons
from src.bot.config import GLOBAL_TIMEOUT


def create_banned_embed() -> tuple[discord.Embed, discord.ui.View]:
    """Create the banned player embed with a close button."""
    embed = discord.Embed(
        title="🚫 Account Banned",
        description="Your account has been banned from using this bot. If you believe this is in error, please contact an administrator.",
        color=discord.Color.red()
    )
    
    class ErrorView(discord.ui.View):
        pass
    
    view = ErrorView(timeout=GLOBAL_TIMEOUT)
    close_buttons = ConfirmRestartCancelButtons.create_buttons(
        reset_target=view,
        include_confirm=False,
        include_restart=False,
        include_cancel=True,
        cancel_label="Close"
    )
    for button in close_buttons:
        view.add_item(button)
    
    return embed, view

