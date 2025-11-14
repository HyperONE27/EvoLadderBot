import discord


def create_player_confirmation_embed(match_id: int) -> discord.Embed:
    """
    Create embed shown to a player when they confirm a match.
    
    Args:
        match_id: The match ID
        
    Returns:
        Discord embed for player confirmation feedback
    """
    embed = discord.Embed(
        title=f"Match #{match_id} - ✅ You Confirmed The Match!",
        description=(
            "You have confirmed the match!\n"
            "Once you and your opponent have BOTH confirmed,\n"
            "you can proceed with your lobby game."
        ),
        color=discord.Color.green()
    )
    return embed


def create_opponent_confirmation_embed(match_id: int, confirming_player_name: str) -> discord.Embed:
    """
    Create embed sent to opponent when the other player confirms the match.
    
    Args:
        match_id: The match ID
        confirming_player_name: Name of the player who confirmed
        
    Returns:
        Discord embed for opponent notification
    """
    embed = discord.Embed(
        title=f"Match #{match_id} - ✅ Your Opponent Confirmed The Match!",
        description=(
            f"Your opponent, **{confirming_player_name}**, confirmed the match!\n"
            "Once you and your opponent have BOTH confirmed,\n"
            "you can proceed with your lobby game."
        ),
        color=discord.Color.green()
    )
    return embed

