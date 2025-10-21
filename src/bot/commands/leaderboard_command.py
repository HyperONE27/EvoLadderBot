from typing import List, Optional

import discord
from discord import app_commands

from src.backend.services.app_context import (
    command_guard_service as guard_service,
    leaderboard_service,
)
from src.backend.services.command_guard_service import CommandGuardError
from src.backend.services.leaderboard_service import LeaderboardService  # For type hints
from src.backend.services.performance_service import FlowTracker
from src.bot.components.command_guard_embeds import create_command_guard_error_embed
from src.bot.config import GLOBAL_TIMEOUT
from src.bot.utils.discord_utils import get_flag_emote, get_race_emote, send_ephemeral_response


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
    # Pass bot's process pool for offloading heavy computation
    process_pool = getattr(interaction.client, 'process_pool', None)
    data = await leaderboard_service.get_leaderboard_data(
        country_filter=view.country_filter,
        race_filter=view.race_filter,
        best_race_only=view.best_race_only,
        current_page=view.current_page,
        page_size=40,
        process_pool=process_pool
    )
    flow.checkpoint("fetch_leaderboard_data_complete")
    
    # Update button states based on data
    flow.checkpoint("update_button_states_start")
    total_pages = data.get("total_pages", 1)
    current_page = data.get("current_page", 1)
    button_states = leaderboard_service.get_button_states(current_page, total_pages)
    
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
    
    flow.checkpoint("embed_generation_start")
    embed = view.get_embed(data)
    flow.checkpoint("embed_generation_complete")
    
    flow.checkpoint("discord_api_call_start")
    import time
    discord_api_start = time.perf_counter()
    await send_ephemeral_response(interaction, embed=embed, view=view)
    discord_api_end = time.perf_counter()
    discord_api_time = (discord_api_end - discord_api_start) * 1000
    print(f"[Initial Command] Discord API call: {discord_api_time:.2f}ms")
    if discord_api_time > 100:
        print(f"⚠️  SLOW Discord API (initial): {discord_api_time:.2f}ms")
    elif discord_api_time > 50:
        print(f"🟡 Moderate Discord API (initial): {discord_api_time:.2f}ms")
    flow.checkpoint("discord_api_call_complete")
    
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
            flag_emote = get_flag_emote(country['code'])
            options.append(
                discord.SelectOption(
                    label=country['name'],
                    value=country['code'],
                    description="",
                    emoji=flag_emote,
                    default=is_default
                )
            )
        
        # Static placeholder - selected values will show in the dropdown
        placeholder = "Filter by country (Page 1)..."
        
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=25,
            options=options,
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        # Update VIEW state (not service)
        self.view.country_page1_selection = self.values
        self.view.country_filter = self.values + self.view.country_page2_selection
        self.view.current_page = 1  # Reset to first page
        
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
            flag_emote = get_flag_emote(country['code'])
            options.append(
                discord.SelectOption(
                    label=country['name'],
                    value=country['code'],
                    description="",
                    emoji=flag_emote,
                    default=is_default
                )
            )
        
        # Static placeholder - selected values will show in the dropdown
        placeholder = "Filter by country (Page 2)..."
        
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=25,
            options=options,
            row=3
        )

    async def callback(self, interaction: discord.Interaction):
        # Update VIEW state (not service)
        self.view.country_page2_selection = self.values
        self.view.country_filter = self.view.country_page1_selection + self.values
        self.view.current_page = 1  # Reset to first page
        
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
            race_emote = get_race_emote(value)
            options.append(
                discord.SelectOption(
                    label=label,
                    value=value,
                    description=description,
                    emoji=race_emote,
                    default=is_default
                )
            )
        
        # Static placeholder - selected values will show in the dropdown
        placeholder = "Filter by race (multiselect)..."
        
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=len(all_options),
            options=options,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        # Update VIEW state (not service)
        selected_values = self.values
        if not selected_values:
            self.view.race_filter = None
        else:
            self.view.race_filter = selected_values
        self.view.current_page = 1  # Reset to first page
        
        # Update the view
        await self.view.update_view(interaction)


class LeaderboardView(discord.ui.View):
    """Main leaderboard view with pagination and filtering - ISOLATED state per user"""
    
    def __init__(self, 
                 leaderboard_service: LeaderboardService,
                 current_page: int = 1,
                 country_filter: Optional[List[str]] = None,
                 race_filter: Optional[List[str]] = None,
                 best_race_only: bool = False,
                 rank_filter: Optional[str] = None,
                 country_page1_selection: Optional[List[str]] = None,
                 country_page2_selection: Optional[List[str]] = None):
        super().__init__(timeout=GLOBAL_TIMEOUT)
        self.leaderboard_service = leaderboard_service
        
        # Get countries for filter from service
        self.countries = leaderboard_service.country_service.get_common_countries()
        
        # Per-user filter state (ISOLATED - not shared between users)
        self.current_page: int = current_page
        self.country_filter: List[str] = country_filter if country_filter is not None else []
        self.race_filter: Optional[List[str]] = race_filter
        self.best_race_only: bool = best_race_only
        self.rank_filter: Optional[str] = rank_filter
        self.country_page1_selection: List[str] = country_page1_selection if country_page1_selection is not None else []
        self.country_page2_selection: List[str] = country_page2_selection if country_page2_selection is not None else []
        
        # Add pagination and clear buttons (at the top, right under embed)
        self.add_item(PreviousPageButton(disabled=True))
        self.add_item(NextPageButton(disabled=True))
        self.add_item(RankFilterButton(disabled=False, rank_filter=self.rank_filter))
        self.add_item(BestRaceOnlyButton(disabled=False, best_race_only=self.best_race_only))
        self.add_item(ClearFiltersButton())
        
        # Add filter dropdowns (race first, then countries)
        self.add_item(RaceFilterSelect(self.leaderboard_service, self.race_filter))
        self.add_item(CountryFilterPage1Select(self.countries, self.country_page1_selection))
        self.add_item(CountryFilterPage2Select(self.countries, self.country_page2_selection))
        
        # Add pagination dropdown
        self.add_item(PageNavigationSelect(1, 1))

    async def update_view(self, interaction: discord.Interaction):
        """Update the view with current filters and page"""
        import time
        filter_start = time.perf_counter()
        
        # Get leaderboard data from backend service with VIEW's state
        # Pass bot's process pool for offloading heavy computation
        process_pool = getattr(interaction.client, 'process_pool', None)
        data = await self.leaderboard_service.get_leaderboard_data(
            country_filter=self.country_filter,
            race_filter=self.race_filter,
            best_race_only=self.best_race_only,
            rank_filter=self.rank_filter,
            current_page=self.current_page,
            page_size=40,
            process_pool=process_pool
        )
        
        data_fetch_time = time.perf_counter()
        print(f"[Filter Perf] Data fetch: {(data_fetch_time - filter_start)*1000:.2f}ms")
        
        # Create a new view with current selections to maintain state
        new_view = LeaderboardView(
            leaderboard_service=self.leaderboard_service,
            current_page=self.current_page,
            country_filter=self.country_filter,
            race_filter=self.race_filter,
            best_race_only=self.best_race_only,
            rank_filter=self.rank_filter,
            country_page1_selection=self.country_page1_selection,
            country_page2_selection=self.country_page2_selection
        )
        
        view_creation_time = time.perf_counter()
        print(f"[Filter Perf] View creation: {(view_creation_time - data_fetch_time)*1000:.2f}ms")
        
        # Update button states based on data
        total_pages = data.get("total_pages", 1)
        current_page = data.get("current_page", 1)
        button_states = self.leaderboard_service.get_button_states(current_page, total_pages)
        
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
        
        button_update_time = time.perf_counter()
        print(f"[Filter Perf] Button updates: {(button_update_time - view_creation_time)*1000:.2f}ms")
        
        # Generate embed
        embed = new_view.get_embed(data)
        embed_generation_time = time.perf_counter()
        print(f"[Filter Perf] Embed generation: {(embed_generation_time - button_update_time)*1000:.2f}ms")
        
        # Discord API call - this is where the lag might be
        discord_api_start = time.perf_counter()
        await interaction.response.edit_message(embed=embed, view=new_view)
        discord_api_end = time.perf_counter()
        
        discord_api_time = (discord_api_end - discord_api_start) * 1000
        total_time = (discord_api_end - filter_start) * 1000
        
        print(f"[Filter Perf] Discord API call: {discord_api_time:.2f}ms")
        print(f"[Filter Perf] TOTAL FILTER OPERATION: {total_time:.2f}ms")
        
        # Alert if Discord API is slow
        if discord_api_time > 100:
            print(f"⚠️  SLOW Discord API: {discord_api_time:.2f}ms")
        elif discord_api_time > 50:
            print(f"🟡 Moderate Discord API: {discord_api_time:.2f}ms")

    def get_embed(self, data: dict = None) -> discord.Embed:
        """Get the leaderboard embed"""
        import time
        start_time = time.perf_counter()
        
        if data is None:
            data = {
                "players": [],
                "total_pages": 1,
                "current_page": self.current_page,
                "total_players": 0
            }
        
        checkpoint_1 = time.perf_counter()
        print(f"[Embed Perf] Data validation: {(checkpoint_1 - start_time)*1000:.2f}ms")
        
        embed = discord.Embed(
            title="🏆 Player Leaderboard",
            description="",
            color=discord.Color.gold()
        )
        
        checkpoint_2 = time.perf_counter()
        print(f"[Embed Perf] Embed creation: {(checkpoint_2 - checkpoint_1)*1000:.2f}ms")
        
        # Add filter information using backend service with VIEW state
        filter_info = self.leaderboard_service.get_filter_info(
            race_filter=self.race_filter,
            country_filter=self.country_filter,
            best_race_only=self.best_race_only
        )
        
        checkpoint_3 = time.perf_counter()
        print(f"[Embed Perf] Get filter info: {(checkpoint_3 - checkpoint_2)*1000:.2f}ms")
        
        # Race filter
        race_names = filter_info.get("race_names", [])
        if race_names:
            race_display = ", ".join(race_names)
            race_text = f"**Race:** `{race_display}`"
        else:
            race_text = "**Race:** `All`"
        
        # Country filter
        country_names = filter_info.get("country_names", [])
        if country_names:
            country_display = ", ".join(country_names)
            country_text = f"**Country:** `{country_display}`"
        else:
            country_text = "**Country:** `All`"
        
        # Add filters stacked vertically
        embed.add_field(name="", value=race_text + "\n" + country_text, inline=False)
        
        checkpoint_4 = time.perf_counter()
        print(f"[Embed Perf] Add filter fields: {(checkpoint_4 - checkpoint_3)*1000:.2f}ms")
        
        # Add leaderboard content using backend service
        players = data.get("players", [])
        page_size = 40  # Discord-specific page size (8 sections of 5)
        current_page = data.get("current_page", 1)
        formatted_players = self.leaderboard_service.get_leaderboard_data_formatted(
            players, current_page, page_size
        )
        
        checkpoint_5 = time.perf_counter()
        print(f"[Embed Perf] Format players: {(checkpoint_5 - checkpoint_4)*1000:.2f}ms")
        
        if not formatted_players:
            embed.add_field(
                name="Leaderboard",
                value="No players found.",
                inline=False
            )
            checkpoint_8 = time.perf_counter()
        else:
            # Split players into chunks of 5 to avoid Discord's 1024 character limit
            players_per_field = 5
            
            checkpoint_6 = time.perf_counter()
            print(f"[Embed Perf] Prepare formatting: {(checkpoint_6 - checkpoint_5)*1000:.2f}ms")
            
            # OPTIMIZATION: Batch emote lookups to reduce function call overhead
            emote_fetch_start = time.perf_counter()
            
            # Pre-fetch all emotes in one pass
            rank_emotes = {}
            race_emotes = {}
            flag_emotes = {}
            
            for player in formatted_players:
                mmr_rank = player.get('mmr_rank', 'u_rank')
                race_code = player.get('race_code', '')
                country = player.get('country', '')
                
                # Cache emotes to avoid repeated lookups
                if mmr_rank not in rank_emotes:
                    rank_emotes[mmr_rank] = self._get_rank_emote(mmr_rank)
                if race_code not in race_emotes:
                    race_emotes[race_code] = self._get_race_emote(race_code)
                if country not in flag_emotes:
                    flag_emotes[country] = self._get_flag_emote(country)
            
            emote_fetch_time = (time.perf_counter() - emote_fetch_start)
            
            # Prepare all chunks with pre-fetched emotes
            chunks = []
            text_format_time = 0.0
            
            for i in range(0, len(formatted_players), players_per_field):
                chunk = formatted_players[i:i + players_per_field]
                field_text = ""
                
                for player in chunk:
                    format_start = time.perf_counter()
                    
                    # Use pre-fetched emotes (no function calls)
                    rank_emote = rank_emotes[player.get('mmr_rank', 'u_rank')]
                    race_emote = race_emotes[player.get('race_code', '')]
                    flag_emote = flag_emotes[player.get('country', '')]
                    
                    # Format rank with backticks and proper alignment (4 chars + period)
                    rank_padded = f"{player['rank']:>4d}"
                    
                    # Format player name with padding to 12 chars (12 max)
                    player_name = player['player_id']
                    player_name_padded = f"{player_name:<12}"
                    
                    # Format MMR
                    mmr_value = player['mmr']
                    
                    field_text += f"`{rank_padded}.` {rank_emote} {race_emote} {flag_emote} `{player_name_padded}` `{mmr_value}`\n"
                    text_format_time += (time.perf_counter() - format_start)
                
                chunks.append(field_text)
            
            checkpoint_7 = time.perf_counter()
            print(f"[Embed Perf] Generate chunks - Total: {(checkpoint_7 - checkpoint_6)*1000:.2f}ms")
            print(f"[Embed Perf]   -> Emote fetching: {emote_fetch_time*1000:.2f}ms")
            print(f"[Embed Perf]   -> Text formatting: {text_format_time*1000:.2f}ms")
            
            # Add fields in 2x4 grid layout
            # Left column gets titles (1-10, 11-20, etc), right column gets invisible names
            for i in range(0, len(chunks), 2):
                left_field_text = chunks[i]
                
                # Calculate pair index (0, 1, 2, 3...)
                pair_index = i // 2
                
                # Each pair represents 10 players (2 chunks * 5 players)
                pair_start = (current_page - 1) * page_size + pair_index * 10 + 1
                pair_end = pair_start + 9
                combined_field_name = f"Leaderboard ({pair_start}-{pair_end})"
                
                # Add left field with combined title
                embed.add_field(name=combined_field_name, value=left_field_text, inline=True)
                
                # Add right field with invisible name (zero-width space)
                if i + 1 < len(chunks):
                    right_field_text = chunks[i + 1]
                    embed.add_field(name="\u200b", value=right_field_text, inline=True)
                
                # Add row separator after each pair (except the last)
                if i + 2 < len(chunks):
                    embed.add_field(
                        name=" ",  # Single space (minimal)
                        value=" ",  # Single space (minimal)
                        inline=False
                    )
            
            checkpoint_8 = time.perf_counter()
            print(f"[Embed Perf] Add fields to embed: {(checkpoint_8 - checkpoint_7)*1000:.2f}ms")
        
        # Add page information using backend service
        total_pages = data.get("total_pages", 1)
        total_players = data.get("total_players", 0)
        pagination_info = self.leaderboard_service.get_pagination_info(current_page, total_pages, total_players)
        footer_text = f"Page {pagination_info['current_page']}/{pagination_info['total_pages']} • {pagination_info['total_players']} total players"
        embed.set_footer(text=footer_text)
        
        checkpoint_9 = time.perf_counter()
        print(f"[Embed Perf] Add footer: {(checkpoint_9 - checkpoint_8)*1000:.2f}ms")
        
        total_time = (checkpoint_9 - start_time) * 1000
        print(f"[Embed Perf] TOTAL EMBED GENERATION: {total_time:.2f}ms")
        
        return embed

    def _get_race_emote(self, race_code: str) -> str:
        """Get the Discord emote for a race code."""
        from src.bot.utils.discord_utils import get_race_emote
        return get_race_emote(race_code)
    
    def _get_flag_emote(self, country_code: str) -> str:
        """Get the Discord flag emote for a country code."""
        from src.bot.utils.discord_utils import get_flag_emote
        return get_flag_emote(country_code)
    
    def _get_rank_emote(self, rank: str) -> str:
        """Get the Discord rank emote for a rank code."""
        from src.bot.utils.discord_utils import get_rank_emote
        return get_rank_emote(rank)


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
        if self.view.current_page > 1:
            self.view.current_page -= 1
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
        self.view.current_page += 1
        await self.view.update_view(interaction)


class RankFilterButton(discord.ui.Button):
    """Cycle through rank filters: All -> S -> A -> B -> C -> D -> E -> F -> All"""
    
    # Rank cycle order
    RANK_CYCLE = [None, "s_rank", "a_rank", "b_rank", "c_rank", "d_rank", "e_rank", "f_rank"]
    
    def __init__(self, disabled=False, rank_filter=None):
        from src.bot.utils.discord_utils import get_rank_emote
        
        # Determine current state
        if rank_filter is None:
            label = "All Ranks"
            emoji = get_rank_emote("u_rank")
            style = discord.ButtonStyle.secondary
        else:
            # Get the rank letter (e.g., "s_rank" -> "S")
            rank_letter = rank_filter.split("_")[0].upper()
            label = f"{rank_letter}-Rank"
            emoji = get_rank_emote(rank_filter)
            style = discord.ButtonStyle.primary
        
        super().__init__(
            label=label,
            emoji=emoji,
            style=style,
            row=0,
            disabled=disabled
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Cycle to next rank
        current_rank = self.view.rank_filter
        try:
            current_index = self.RANK_CYCLE.index(current_rank)
        except ValueError:
            current_index = 0
        
        # Get next rank (wrap around to beginning)
        next_index = (current_index + 1) % len(self.RANK_CYCLE)
        next_rank = self.RANK_CYCLE[next_index]
        
        # Update view state
        self.view.rank_filter = next_rank
        self.view.current_page = 1  # Reset to first page
        
        # Update the view
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
        # Toggle VIEW state (not service)
        self.view.best_race_only = not self.view.best_race_only
        self.view.current_page = 1  # Reset to first page
        
        # Update button emoji and style based on state
        if self.view.best_race_only:
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
        # Clear VIEW filter state (not service)
        self.view.race_filter = None
        self.view.country_filter = []
        self.view.country_page1_selection = []
        self.view.country_page2_selection = []
        self.view.best_race_only = False
        self.view.rank_filter = None
        self.view.current_page = 1
        
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
        
        # Direct page navigation - update VIEW state
        page_num = int(selected_value.split("_")[1])
        self.view.current_page = page_num
        
        await self.view.update_view(interaction)

