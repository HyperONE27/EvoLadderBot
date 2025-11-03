import discord


def create_banned_embed() -> discord.Embed:
    """Create the banned player embed."""
    embed = discord.Embed(
        title="🚫 Account Banned",
        description="Your account has been banned from using this bot. If you believe this is in error, please contact an administrator.",
        color=discord.Color.red()
    )
    return embed

