import discord


class CancelEmbedView(discord.ui.View):
    """
    Simple cancel view with red color and X emote.
    Shows that an operation has been cancelled.
    """

    def __init__(self):
        super().__init__(timeout=300)
        
        # Build the cancel embed with red color and X emote
        self.embed = discord.Embed(
            title="❌ Operation Cancelled",
            description="The operation has been cancelled.",
            color=discord.Color.red()
        )


def create_cancel_embed() -> CancelEmbedView:
    """
    Create a simple cancel embed view.
    
    Returns:
        CancelEmbedView with cancel message
    """
    return CancelEmbedView()
