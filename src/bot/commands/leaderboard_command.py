import discord
from discord import app_commands
from src.backend.services.command_guard_service import CommandGuardError
from src.backend.services.leaderboard_service import LeaderboardService  # For type hints
from src.backend.services.app_context import (
    command_guard_service as guard_service,
    leaderboard_service
)
from src.bot.utils.discord_utils import send_ephemeral_response
from src.bot.components.command_guard_embeds import create_command_guard_error_embed
from src.bot.config import GLOBAL_TIMEOUT
from src.backend.services.performance_service import FlowTracker


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
    flow = FlowTracker("leaderboard_command", user_id=interaction.user.id)
    
    try:
        flow.checkpoint("guard_checks_start")
        player = guard_service.ensure_player_record(interaction.user.id, interaction.user.name)
        guard_service.require_tos_accepted(player)
        flow.checkpoint("guard_checks_complete")
    except CommandGuardError as exc:
        flow.complete("guard_check_failed")
        error_embed = create_command_guard_error_embed(exc)
        await send_ephemeral_response(interaction, embed=error_embed)
        return
    
    flow.checkpoint("create_view_start")
    view = LeaderboardView(leaderboard_service)
    flow.checkpoint("create_view_complete")
    
    # Get initial data to set proper button states
    flow.checkpoint("fetch_leaderboard_data_start")
    data = await leaderboard_service.get_leaderboard_data(page_size=20)
    flow.checkpoint("fetch_leaderboard_data_complete")
    
    # Update button states based on data
    flow.checkpoint("update_button_states_start")
    total_pages = data.get("total_pages", 1)
    current_page = data.get("current_page", 1)
    button_states = leaderboard_service.get_button_states(total_pages)
    
    for item in view.children:
        if isinstance(item, PreviousPageButton):
            item.disabled = button_states["previous_disabled"]
        elif isinstance(item, NextPageButton):
            item.disabled = button_states["next_disabled"]
        elif isinstance(item, PageNavigationSelect):
            # Replace with updated pagination dropdown
            view.remove_item(item)
            view.add_item(PageNavigationSelect(total_pages, current_page))
    
    flow.checkpoint("update_button_states_complete")
    
    flow.checkpoint("send_response_start")
    await send_ephemeral_response(interaction, embed=view.get_embed(data), view=view)
    flow.checkpoint("send_response_complete")
    
    flow.complete("success")


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
        self.view.leaderboard_service.update_country_filter(self.values, self.view.leaderboard_service.country_page2_selection)
        
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
        self.view.leaderboard_service.update_country_filter(self.view.leaderboard_service.country_page1_selection, self.values)
        
        # Update the view
        await self.view.update_view(interaction)


class RaceFilterSelect(discord.ui.Select):
    """Multiselect dropdown to filter by race"""
    
    def __init__(self, leaderboard_service, selected_races=None):
        self.selected_values = selected_races or []
        
        options = []
        # Get race options from service
        all_options = leaderboard_service.race_service.get_race_options_for_dropdown()
        
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
            for race_code in self.selected_values:
                race_name = leaderboard_service.race_service.get_race_name(race_code)
                race_names.append(race_name)
            if race_names:
                placeholder = f"Selected: {', '.join(race_names)}"
        
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=len(all_options),
            options=options,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        selected_values = self.values
        if not selected_values:
            self.view.leaderboard_service.update_race_filter(None)
        else:
            self.view.leaderboard_service.update_race_filter(selected_values)
        
        # Update the view
        await self.view.update_view(interaction)


class LeaderboardView(discord.ui.View):
    """Main leaderboard view with pagination and filtering"""
    
    def __init__(self, leaderboard_service: LeaderboardService):
        super().__init__(timeout=GLOBAL_TIMEOUT)
        self.leaderboard_service = leaderboard_service
        
        # Get countries for filter from service
        self.countries = leaderboard_service.country_service.get_common_countries()
        
        # Add pagination and clear buttons (at the top, right under embed)
        # Note: Button states will be properly set in update_view based on actual data
        self.add_item(PreviousPageButton(disabled=True))  # Start disabled, will be enabled if not page 1
        self.add_item(NextPageButton(disabled=True))      # Start disabled, will be enabled if not last page
        self.add_item(BestRaceOnlyButton(disabled=False, best_race_only=self.leaderboard_service.best_race_only))  # Toggle for best race only mode
        self.add_item(ClearFiltersButton())
        
        # Add filter dropdowns (race first, then countries)
        self.add_item(RaceFilterSelect(self.leaderboard_service, self.leaderboard_service.race_filter))
        self.add_item(CountryFilterPage1Select(self.countries, self.leaderboard_service.country_page1_selection))
        self.add_item(CountryFilterPage2Select(self.countries, self.leaderboard_service.country_page2_selection))
        
        # Add pagination dropdown (will be updated with actual page data in update_view)
        self.add_item(PageNavigationSelect(1, 1))  # Placeholder, will be updated


    async def update_view(self, interaction: discord.Interaction):
        """Update the view with current filters and page"""
        # Get leaderboard data from backend service
        data = await self.leaderboard_service.get_leaderboard_data(page_size=20)
        
        # Create a new view with current selections to maintain state
        new_view = LeaderboardView(self.leaderboard_service)
        
        # Update button states based on data
        total_pages = data.get("total_pages", 1)
        current_page = data.get("current_page", 1)
        button_states = self.leaderboard_service.get_button_states(total_pages)
        
        # Update button states and pagination dropdown
        for item in new_view.children:
            if isinstance(item, PreviousPageButton):
                item.disabled = button_states["previous_disabled"]
            elif isinstance(item, NextPageButton):
                item.disabled = button_states["next_disabled"]
            elif isinstance(item, PageNavigationSelect):
                # Replace with updated pagination dropdown
                new_view.remove_item(item)
                new_view.add_item(PageNavigationSelect(total_pages, current_page))
        
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
                "current_page": self.leaderboard_service.current_page,
                "total_players": 0
            }
        
        embed = discord.Embed(
            title="🏆 Player Leaderboard",
            description="",
            color=discord.Color.gold()
        )
        
        # Add filter information using backend service
        filter_info = self.leaderboard_service.get_filter_info()
        filter_text = "**Filters:**\n"
        
        # Race filter
        race_names = filter_info.get("race_names", [])
        if race_names:
            race_count = len(race_names)
            filter_text += f"Race: `{race_count} selected`\n"
        else:
            filter_text += "Race: `All`\n"
        
        # Country filter
        country_names = filter_info.get("country_names", [])
        if country_names:
            country_count = len(country_names)
            filter_text += f"Country: `{country_count} selected`\n"
        else:
            filter_text += "Country: `All`\n"
        
        embed.add_field(name="", value=filter_text, inline=False)
        
        # Add leaderboard content using backend service
        players = data.get("players", [])
        page_size = 20  # Discord-specific page size
        formatted_players = self.leaderboard_service.get_leaderboard_data_formatted(players, page_size)
        
        if not formatted_players:
            leaderboard_text = "No players found."
        else:
            leaderboard_text = ""
            for player in formatted_players:
                # Get race emote and flag emote
                race_emote = self._get_race_emote(player.get('race_code', ''))
                flag_emote = self._get_flag_emote(player.get('country', ''))
                
                # Format: - 1. {race_emote} {flag_emote} Master88 ({MMR number})
                leaderboard_text += f"- {player['rank']}. {race_emote} {flag_emote} {player['player_id']} ({player['mmr']})\n"
        
        embed.add_field(
            name="Leaderboard",
            value=leaderboard_text,
            inline=False
        )
        
        # Add page information using backend service
        total_pages = data.get("total_pages", 1)
        total_players = data.get("total_players", 0)
        pagination_info = self.leaderboard_service.get_pagination_info(total_pages, total_players)
        footer_text = f"Page {pagination_info['current_page']}/{pagination_info['total_pages']} • {pagination_info['total_players']} total players"
        embed.set_footer(text=footer_text)
        
        return embed

    def _get_race_emote(self, race_code: str) -> str:
        """Get the Discord emote for a race code."""
        from src.bot.utils.discord_utils import get_race_emote
        return get_race_emote(race_code)
    
    def _get_flag_emote(self, country_code: str) -> str:
        """Get the Discord flag emote for a country code."""
        from src.bot.utils.discord_utils import get_flag_emote
        return get_flag_emote(country_code)


class PreviousPageButton(discord.ui.Button):
    """Previous page button for leaderboard pagination"""
    
    def __init__(self, disabled=False):
        super().__init__(
            label="Previous Page",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=0,
            disabled=disabled
        )
    
    async def callback(self, interaction: discord.Interaction):
        if self.view.leaderboard_service.current_page > 1:
            self.view.leaderboard_service.set_page(self.view.leaderboard_service.current_page - 1)
            await self.view.update_view(interaction)


class NextPageButton(discord.ui.Button):
    """Next page button for leaderboard pagination"""
    
    def __init__(self, disabled=False):
        super().__init__(
            label="Next Page",
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            row=0,
            disabled=disabled
        )
    
    async def callback(self, interaction: discord.Interaction):
        # For now, just increment page (will be limited by actual data later)
        self.view.leaderboard_service.set_page(self.view.leaderboard_service.current_page + 1)
        await self.view.update_view(interaction)


class BestRaceOnlyButton(discord.ui.Button):
    """Toggle best race only mode button"""
    
    def __init__(self, disabled=False, best_race_only=False):
        # Set initial state based on best_race_only parameter
        if best_race_only:
            emoji = "✅"
            style = discord.ButtonStyle.primary
        else:
            emoji = "🟩"
            style = discord.ButtonStyle.secondary
        
        super().__init__(
            label="Best Race Only",
            emoji=emoji,
            style=style,
            row=0,
            disabled=disabled
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Toggle best race only mode
        self.view.leaderboard_service.toggle_best_race_only()
        
        # Update button emoji and style based on state
        if self.view.leaderboard_service.best_race_only:
            self.emoji = "✅"
            self.style = discord.ButtonStyle.primary
        else:
            self.emoji = "🟩"
            self.style = discord.ButtonStyle.secondary
        
        # Update the view
        await self.view.update_view(interaction)


class ClearFiltersButton(discord.ui.Button):
    """Clear all filters button"""
    
    def __init__(self):
        super().__init__(
            label="Clear All Filters",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Clear all filter selections
        self.view.leaderboard_service.clear_all_filters()
        
        # Reset best race only button
        for item in self.view.children:
            if isinstance(item, BestRaceOnlyButton):
                item.label = "Best Race Only"
                item.emoji = "🟩"
                item.style = discord.ButtonStyle.secondary
        
        await self.view.update_view(interaction)


class PageNavigationSelect(discord.ui.Select):
    """Dropdown for navigating between pages"""
    
    def __init__(self, total_pages: int, current_page: int):
        self.total_pages = total_pages
        self.current_page = current_page
        
        options = []
        
        # Only show individual pages, no ranges
        for page in range(1, total_pages + 1):
            options.append(
                discord.SelectOption(
                    label=f"Page {page}",
                    value=f"page_{page}",
                    default=(page == current_page)
                )
            )
        
        super().__init__(
            placeholder=f"Page {current_page}/{total_pages}",
            min_values=1,
            max_values=1,
            options=options,
            row=4  # Last row
        )
    
    async def callback(self, interaction: discord.Interaction):
        selected_value = self.values[0]
        
        # Direct page navigation
        page_num = int(selected_value.split("_")[1])
        self.view.leaderboard_service.set_page(page_num)
        
        await self.view.update_view(interaction)
