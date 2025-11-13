import discord


def create_opponent_report_notification_embed(
    match_id: int,
    reporting_player_name: str,
    report_text: str
) -> discord.Embed:
    """
    Create embed sent to a player when their opponent reports a match result.
    
    Args:
        match_id: The match ID
        reporting_player_name: Name of the player who reported
        report_text: Text description of what was reported
        
    Returns:
        Discord embed for opponent report notification
    """
    embed = discord.Embed(
        title=f"Match #{match_id} - 📝 Your Opponent Reported",
        description=(
            f"{reporting_player_name} reported: **{report_text}**\n\n"
            "If you're seeing this, it likely means you have not reported the match result yet. "
            "**Please do so as soon as possible.**"
        ),
        color=discord.Color.blurple()
    )
    return embed

