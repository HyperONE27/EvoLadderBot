import discord
from typing import List, Dict, Optional, Callable
import math

class PaginatedCountrySelect(discord.ui.Select):
    """Paginated country selector for common countries"""
    
    def __init__(self, countries: List[Dict], page: int = 0, callback_func: Callable = None):
        self.all_countries = countries
        self.page = page
        self.callback_func = callback_func
        
        # Calculate pagination (25 per page)
        items_per_page = 25
        total_pages = math.ceil(len(countries) / items_per_page)
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(countries))
        
        options = []
        for country in countries[start_idx:end_idx]:
            emoji = "🌍" if country['code'] != "XX" else "❓"
            options.append(discord.SelectOption(
                label=country['name'],
                value=country['code'],
                emoji=emoji
            ))
        
        placeholder = f"Select your country... (Page {page + 1}/{total_pages})"
        
        super().__init__(
            placeholder=placeholder,
            options=options,
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction, self.values[0])


class RegionSelect(discord.ui.Select):
    """Region selector dropdown"""
    
    def __init__(self, regions: List[Dict], callback_func: Callable = None):
        self.callback_func = callback_func
        
        options = []
        for region in regions:
            options.append(discord.SelectOption(
                label=region['name'],
                value=region['code'],
                emoji="📍"
            ))
        
        super().__init__(
            placeholder="Select your region of residence...",
            options=options,
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction, self.values[0])