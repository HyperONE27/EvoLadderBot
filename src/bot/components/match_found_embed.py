import discord


def create_match_found_embed(match_id: int) -> discord.Embed:
    """
    Create a minimal embed shown when a match is found.
    
    Args:
        match_id: The match ID
        
    Returns:
        Discord embed for match found notification
    """
    embed = discord.Embed(
        title=f"Match #{match_id} Found!",
        description="Your match is ready! See below for full details.",
        color=discord.Color.green()
    )
    return embed

