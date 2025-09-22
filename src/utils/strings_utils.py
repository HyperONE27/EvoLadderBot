def format_race_name(race: str) -> str:
    """
    Format race name with proper capitalization.
    
    Args:
        race: Race string in format like 'bw_terran', 'sc2_zerg', etc.
        
    Returns:
        Properly formatted race name like 'BW Terran', 'SC2 Zerg', etc.
    """
    if not race:
        return "Unknown"
    
    # Split by underscore and capitalize each part
    parts = race.split('_')
    
    if len(parts) == 2:
        game, race_name = parts
        
        # Handle game prefix
        if game.lower() == 'bw':
            game = 'BW'
        elif game.lower() == 'sc2':
            game = 'SC2'
        else:
            game = game.upper()
        
        # Handle race name
        race_name = race_name.capitalize()
        
        return f"{game} {race_name}"
    
    # Fallback for unexpected format
    return race.replace('_', ' ').title()
