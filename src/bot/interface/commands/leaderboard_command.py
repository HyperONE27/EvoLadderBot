import discord
from discord import app_commands
import json
import os
from src.utils.country_region_utils import CountryLookup
from src.utils.strings_utils import format_race_name

country_lookup = CountryLookup()


# API Call / Data Handling
async def get_leaderboard_data(
    page: int = 1,
    country_filter: list = None,
    race_filter: list = None,
    page_size: int = 20,
    best_race_only: bool = False
) -> dict:
    """
    Get leaderboard data from mock JSON file.
    """
    # Load mock data
    try:
        with open("data/misc/leaderboard.json", "r") as f:
            all_players = json.load(f)
    except FileNotFoundError:
        return {
            "players": [],
            "total_pages": 1,
            "current_page": page,
            "total_players": 0
        }
    
    # Apply filters
    filtered_players = all_players.copy()
    
    # Filter by country
    if country_filter:
        filtered_players = [p for p in filtered_players if p["country"] in country_filter]
    
    # Filter by race
    if race_filter:
        filtered_players = [p for p in filtered_players if p["race"] in race_filter]
    
    # Apply best race only filtering if enabled
    if best_race_only:
        # Group by player_id and keep only the highest ELO entry for each player
        player_best_races = {}
        for player in filtered_players:
            player_id = player["player_id"]
            if player_id not in player_best_races or player["elo"] > player_best_races[player_id]["elo"]:
                player_best_races[player_id] = player
        filtered_players = list(player_best_races.values())
    
    # Sort by ELO (descending)
    filtered_players.sort(key=lambda x: x["elo"], reverse=True)
    
    # Calculate pagination
    total_players = len(filtered_players)
    total_pages = max(1, (total_players + page_size - 1) // page_size)
    
    # Get page data
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_players = filtered_players[start_idx:end_idx]
    
    return {
        "players": page_players,
        "total_pages": total_pages,
        "current_page": page,
        "total_players": total_players
    }


# Register Command
def register_leaderboard_command(tree: app_commands.CommandTree):
    """Register the leaderboard command"""
    @tree.command(
        name="leaderboard",
        description="View the MMR leaderboard"
    )
    async def leaderboard(interaction: discord.Interaction):
        await leaderboard_command(interaction)
    
    return leaderboard


# UI Elements
async def leaderboard_command(interaction: discord.Interaction):
    """Handle the /leaderboard slash command"""
    view = LeaderboardView()
    
    # Get initial data to set proper button states
    data = await get_leaderboard_data(page=1, page_size=view.page_size, best_race_only=view.best_race_only)
    
    # Update button states based on data
    total_pages = data.get("total_pages", 1)
    for item in view.children:
        if isinstance(item, PreviousPageButton):
            item.disabled = view.current_page <= 1
        elif isinstance(item, NextPageButton):
            item.disabled = view.current_page >= total_pages
    
    await interaction.response.send_message(embed=view.get_embed(data), view=view, ephemeral=True)


class CountryFilterPage1Select(discord.ui.Select):
    """First dropdown to filter by country of citizenship/nationality (countries 1-25)"""
    
    def __init__(self, countries, selected_countries=None):
        self.selected_values = selected_countries or []
        
        # Get first 25 common countries
        page_countries = countries[:25]
        options = []
        
        # Add first 25 common countries as options with default selection
        for country in page_countries:
            is_default = country['code'] in self.selected_values
            options.append(
                discord.SelectOption(
                    label=country['name'],
                    value=country['code'],
                    description="",
                    default=is_default
                )
            )
        
        # Set placeholder based on current selections
        placeholder = "Filter by country (Page 1)..."
        if self.selected_values:
            country_names = []
            for country_code in self.selected_values:
                country_name = next(
                    (c['name'] for c in countries if c['code'] == country_code),
                    country_code
                )
                country_names.append(country_name)
            if country_names:
                placeholder = f"Selected: {', '.join(country_names)}"
        
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=25,
            options=options,
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.country_filter = self.values
        self.view.country_page1_selection = self.values
        
        # Reset to page 1 when filter changes
        self.view.current_page = 1
        
        # Update the view
        await self.view.update_view(interaction)


class CountryFilterPage2Select(discord.ui.Select):
    """Second dropdown to filter by country of citizenship/nationality (countries 26-50)"""
    
    def __init__(self, countries, selected_countries=None):
        self.selected_values = selected_countries or []
        
        # Get countries 26-50 (indices 25-49)
        page_countries = countries[25:50] if len(countries) > 25 else []
        options = []
        
        # Add countries 26-50 as options with default selection
        for country in page_countries:
            is_default = country['code'] in self.selected_values
            options.append(
                discord.SelectOption(
                    label=country['name'],
                    value=country['code'],
                    description="",
                    default=is_default
                )
            )
        
        # Set placeholder based on current selections
        placeholder = "Filter by country (Page 2)..."
        if self.selected_values:
            country_names = []
            for country_code in self.selected_values:
                country_name = next(
                    (c['name'] for c in countries if c['code'] == country_code),
                    country_code
                )
                country_names.append(country_name)
            if country_names:
                placeholder = f"Selected: {', '.join(country_names)}"
        
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=25,
            options=options,
            row=3
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.country_filter = self.values
        self.view.country_page2_selection = self.values
        
        # Reset to page 1 when filter changes
        self.view.current_page = 1
        
        # Update the view
        await self.view.update_view(interaction)


class RaceFilterSelect(discord.ui.Select):
    """Multiselect dropdown to filter by race"""
    
    def __init__(self, selected_races=None):
        self.selected_values = selected_races or []
        
        options = []
        # Create options with default=False, then set default=True for selected ones
        all_options = [
            ("BW Terran", "bw_terran", ""),
            ("BW Zerg", "bw_zerg", ""),
            ("BW Protoss", "bw_protoss", ""),
            ("SC2 Terran", "sc2_terran", ""),
            ("SC2 Zerg", "sc2_zerg", ""),
            ("SC2 Protoss", "sc2_protoss", "")
        ]
        
        for label, value, description in all_options:
            is_default = value in self.selected_values
            options.append(
                discord.SelectOption(
                    label=label,
                    value=value,
                    description=description,
                    default=is_default
                )
            )
        
        # Set placeholder based on current selections
        placeholder = "Filter by race (multiselect)..."
        if self.selected_values:
            race_names = []
            for race in self.selected_values:
                if race == "bw_terran":
                    race_names.append("BW Terran")
                elif race == "bw_zerg":
                    race_names.append("BW Zerg")
                elif race == "bw_protoss":
                    race_names.append("BW Protoss")
                elif race == "sc2_terran":
                    race_names.append("SC2 Terran")
                elif race == "sc2_zerg":
                    race_names.append("SC2 Zerg")
                elif race == "sc2_protoss":
                    race_names.append("SC2 Protoss")
            if race_names:
                placeholder = f"Selected: {', '.join(race_names)}"
        
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=6,
            options=options,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        selected_values = self.values
        if not selected_values:
            self.view.race_filter = None
        else:
            self.view.race_filter = selected_values
        
        # Reset to page 1 when filter changes
        self.view.current_page = 1
        
        # Update the view
        await self.view.update_view(interaction)


class LeaderboardView(discord.ui.View):
    """Main leaderboard view with pagination and filtering"""
    
    def __init__(self, current_page=1, country_filter=None, race_filter=None, country_page1_selection=None, country_page2_selection=None, best_race_only=False):
        super().__init__(timeout=300)
        self.current_page = current_page
        self.page_size = 20
        self.country_filter = country_filter or []
        self.race_filter = race_filter
        self.best_race_only = best_race_only
        
        # Track which country page has selections
        self.country_page1_selection = country_page1_selection or []
        self.country_page2_selection = country_page2_selection or []
        
        # Get countries for filter
        self.countries = country_lookup.get_common_countries()
        
        # Add pagination and clear buttons (at the top, right under embed)
        # Note: Button states will be properly set in update_view based on actual data
        self.add_item(PreviousPageButton(disabled=True))  # Start disabled, will be enabled if not page 1
        self.add_item(NextPageButton(disabled=True))      # Start disabled, will be enabled if not last page
        self.add_item(BestRaceOnlyButton(disabled=False, best_race_only=self.best_race_only))  # Toggle for best race only mode
        self.add_item(ClearFiltersButton())
        
        # Add filter dropdowns (race first, then countries)
        self.add_item(RaceFilterSelect(self.race_filter))
        self.add_item(CountryFilterPage1Select(self.countries, self.country_page1_selection))
        self.add_item(CountryFilterPage2Select(self.countries, self.country_page2_selection))


    async def update_view(self, interaction: discord.Interaction):
        """Update the view with current filters and page"""
        # Combine country selections from both pages
        self.country_filter = self.country_page1_selection + self.country_page2_selection
        
        # Get leaderboard data from mock data
        data = await get_leaderboard_data(
            page=self.current_page,
            country_filter=self.country_filter,
            race_filter=self.race_filter,
            page_size=self.page_size,
            best_race_only=self.best_race_only
        )
        
        # Create a new view with current selections to maintain state
        new_view = LeaderboardView(
            current_page=self.current_page,
            country_filter=self.country_filter,
            race_filter=self.race_filter,
            country_page1_selection=self.country_page1_selection,
            country_page2_selection=self.country_page2_selection,
            best_race_only=self.best_race_only
        )
        
        # Update button states based on data
        total_pages = data.get("total_pages", 1)
        for item in new_view.children:
            if isinstance(item, PreviousPageButton):
                item.disabled = self.current_page <= 1
            elif isinstance(item, NextPageButton):
                item.disabled = self.current_page >= total_pages
        
        await interaction.response.edit_message(embed=new_view.get_embed(data), view=new_view)

    def _format_race_name(self, race: str) -> str:
        """Format race name with proper capitalization"""
        return format_race_name(race)

    def get_embed(self, data: dict = None) -> discord.Embed:
        """Get the leaderboard embed"""
        if data is None:
            data = {
                "players": [],
                "total_pages": 1,
                "current_page": self.current_page,
                "total_players": 0
            }
        
        embed = discord.Embed(
            title="🏆 Player Leaderboard",
            description="Sorted by MMR in descending order",
            color=discord.Color.gold()
        )
        
        # Add filter information
        filter_text = "**Filters:\n** "
        
        # Race filter - maintain dropdown order (BW TZP, then SC2 TZP)
        if self.race_filter:
            if isinstance(self.race_filter, list):
                # Define the order as it appears in dropdowns
                race_order = ["bw_terran", "bw_zerg", "bw_protoss", "sc2_terran", "sc2_zerg", "sc2_protoss"]
                # Filter selected races and maintain order
                ordered_races = [race for race in race_order if race in self.race_filter]
                race_display = ", ".join([self._format_race_name(race) for race in ordered_races])
            else:
                race_display = self._format_race_name(self.race_filter)
            filter_text += f"Race: `{race_display}`\n"
        else:
            filter_text += "Race: `All`\n"
        
        # Country filter - maintain alphabetical order with "Other" at the end
        if self.country_filter:
            # Get all countries in the same order as dropdowns (alphabetical with Other at end)
            all_country_codes = [c['code'] for c in self.countries]
            # Filter selected countries and maintain order
            ordered_countries = [code for code in all_country_codes if code in self.country_filter]
            country_names = []
            for country_code in ordered_countries:
                country_name = next(
                    (c['name'] for c in self.countries if c['code'] == country_code),
                    country_code
                )
                country_names.append(country_name)
            filter_text += f"Country: `{', '.join(country_names)}`\n"
        else:
            filter_text += "Country: `All`\n"
        
        embed.add_field(name="", value=filter_text, inline=False)
        
        # Add leaderboard content
        if data.get("players"):
            leaderboard_text = "```\n"
            for i, player in enumerate(data["players"], 1):
                rank = (self.current_page - 1) * self.page_size + i
                player_id = player.get('player_id', 'Unknown')
                elo = player.get('elo', 0)
                race = format_race_name(player.get('race', 'Unknown'))
                country = player.get('country', 'Unknown')
                leaderboard_text += f"{rank:2d}. {player_id} - {elo} ELO ({race}, {country})\n"
            leaderboard_text += "```"
        else:
            leaderboard_text = "```\nNo players found.\n```"
        
        embed.add_field(
            name="Leaderboard",
            value=leaderboard_text,
            inline=False
        )
        
        
        # Add page information
        total_pages = data.get("total_pages", 1)
        total_players = data.get("total_players", 0)
        embed.set_footer(text=f"Page {self.current_page}/{total_pages} • {total_players} total players")
        
        return embed


class PreviousPageButton(discord.ui.Button):
    """Previous page button for leaderboard pagination"""
    
    def __init__(self, disabled=False):
        super().__init__(
            label="⬅️ Previous Page",
            style=discord.ButtonStyle.secondary,
            row=0,
            disabled=disabled
        )
    
    async def callback(self, interaction: discord.Interaction):
        if self.view.current_page > 1:
            self.view.current_page -= 1
            await self.view.update_view(interaction)


class NextPageButton(discord.ui.Button):
    """Next page button for leaderboard pagination"""
    
    def __init__(self, disabled=False):
        super().__init__(
            label="Next Page ➡️",
            style=discord.ButtonStyle.secondary,
            row=0,
            disabled=disabled
        )
    
    async def callback(self, interaction: discord.Interaction):
        # For now, just increment page (will be limited by actual data later)
        self.view.current_page += 1
        await self.view.update_view(interaction)


class BestRaceOnlyButton(discord.ui.Button):
    """Toggle best race only mode button"""
    
    def __init__(self, disabled=False, best_race_only=False):
        # Set initial state based on best_race_only parameter
        if best_race_only:
            label = "☑️ Best Race Only"
            style = discord.ButtonStyle.primary
        else:
            label = "🟪 Best Race Only"
            style = discord.ButtonStyle.secondary
        
        super().__init__(
            label=label,
            style=style,
            row=0,
            disabled=disabled
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Toggle best race only mode
        self.view.best_race_only = not self.view.best_race_only
        
        # Update button label and style based on state
        if self.view.best_race_only:
            self.label = "☑️ Best Race Only"
            self.style = discord.ButtonStyle.primary
        else:
            self.label = "🟪 Best Race Only"
            self.style = discord.ButtonStyle.secondary
        
        # Reset to page 1 when toggling
        self.view.current_page = 1
        
        # Update the view
        await self.view.update_view(interaction)


class ClearFiltersButton(discord.ui.Button):
    """Clear all filters button"""
    
    def __init__(self):
        super().__init__(
            label="🗑️ Clear All Filters",
            style=discord.ButtonStyle.danger,
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Clear all filter selections
        self.view.race_filter = None
        self.view.country_filter = []
        self.view.country_page1_selection = []
        self.view.country_page2_selection = []
        self.view.best_race_only = False
        self.view.current_page = 1
        
        # Reset best race only button
        for item in self.view.children:
            if isinstance(item, BestRaceOnlyButton):
                item.label = "🟪 Best Race Only"
                item.style = discord.ButtonStyle.primary
        
        await self.view.update_view(interaction)
