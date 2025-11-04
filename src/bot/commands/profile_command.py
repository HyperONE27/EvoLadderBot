import discord
from discord import app_commands
from src.backend.services.command_guard_service import CommandGuardError
from src.backend.services.app_context import (
    command_guard_service as guard_service,
    user_info_service,
    countries_service,
    regions_service,
    races_service,
    ranking_service
)
from src.bot.utils.discord_utils import send_ephemeral_response, get_race_emote, get_flag_emote, get_game_emote, get_rank_emote, get_globe_emote
from src.bot.components.command_guard_embeds import create_command_guard_error_embed
from src.bot.components.confirm_restart_cancel_buttons import ConfirmRestartCancelButtons
from src.bot.utils.command_decorators import dm_only
from src.backend.services.performance_service import FlowTracker
from datetime import datetime, timezone


# API Call / Data Handling
@dm_only
async def profile_command(interaction: discord.Interaction):
    """Handle the /profile slash command"""
    flow = FlowTracker("profile_command", user_id=interaction.user.id)
    
    try:
        # Guard checks
        flow.checkpoint("guard_checks_start")
        player = guard_service.ensure_player_record(interaction.user.id, interaction.user.name)
        flow.checkpoint("guard_checks_complete")
    except CommandGuardError as exc:
        flow.complete("guard_check_failed")
        error_embed = create_command_guard_error_embed(exc)
        await send_ephemeral_response(interaction, embed=error_embed)
        return
    
    # Get player data
    flow.checkpoint("fetch_player_data_start")
    player_data = user_info_service.get_player(interaction.user.id)
    if not player_data:
        flow.complete("player_not_found")
        error_embed = discord.Embed(
            title="❌ Profile Not Found",
            description=f"No profile found for {interaction.user.mention}",
            color=discord.Color.red()
        )
        await send_ephemeral_response(interaction, embed=error_embed)
        return
    
    flow.checkpoint("fetch_player_data_complete")
    
    # Get MMR data for all races from DataAccessService (in-memory, instant)
    flow.checkpoint("fetch_mmr_data_start")
    from src.backend.services.data_access_service import DataAccessService
    data_service = DataAccessService()
    mmr_data = data_service.get_all_player_mmrs(interaction.user.id)
    flow.checkpoint("fetch_mmr_data_complete")
    
    # Create profile embed
    flow.checkpoint("create_embed_start")
    embed = create_profile_embed(interaction.user, player_data, mmr_data)
    flow.checkpoint("create_embed_complete")
    
    # Create view with cancel button only
    flow.checkpoint("create_view_start")
    class ProfileView(discord.ui.View):
        pass
    
    profile_view = ProfileView(timeout=300)
    
    # Add cancel button using the abstraction
    cancel_buttons = ConfirmRestartCancelButtons.create_buttons(
        reset_target=profile_view,
        include_confirm=False,
        include_restart=False,
        include_cancel=True,
        cancel_label="Close"
    )
    
    for button in cancel_buttons:
        profile_view.add_item(button)
    
    flow.checkpoint("create_view_complete")
    
    # Send response
    flow.checkpoint("send_response_start")
    await send_ephemeral_response(interaction, embed=embed, view=profile_view)
    flow.checkpoint("send_response_complete")
    
    flow.complete("success")


def create_profile_embed(user: discord.User, player_data: dict, mmr_data: list) -> discord.Embed:
    """Create an embed displaying player profile information."""
    
    # Determine embed color based on setup status
    if player_data.get('completed_setup'):
        color = discord.Color.green()
        status_icon = "✅"
    else:
        color = discord.Color.orange()
        status_icon = "⚠️"
    
    embed = discord.Embed(
        title=f"{status_icon} Player Profile: {player_data.get('player_name', user.name)}",
        color=color
    )
    
    # Set thumbnail to user avatar
    if user.display_avatar:
        embed.set_thumbnail(url=user.display_avatar.url)
    
    # Basic Information
    basic_info_parts = [
        f"- **User ID:** {user.mention}",
        f"- **Player Name:** {player_data['player_name']}",
        f"- **BattleTag:** {player_data['battletag']}"
    ]
    
    # Alternative IDs if they exist
    alt_ids = []
    if player_data.get('alt_player_name_1'):
        alt_ids.append(player_data['alt_player_name_1'])
    if player_data.get('alt_player_name_2'):
        alt_ids.append(player_data['alt_player_name_2'])
    
    if alt_ids:
        basic_info_parts.append(f"- **Alt IDs:** {', '.join(alt_ids)}")
    
    basic_info = "\n".join(basic_info_parts)
    embed.add_field(name="📋 Basic Information", value=basic_info, inline=False)
    
    # Add spacing between sections
    embed.add_field(name="\n\n", value="\n\n", inline=False)
    
    # Location Information
    location_parts = []
    if player_data.get('country'):
        country = countries_service.get_country_by_code(player_data['country'])
        if country:
            country_name = country.get('name', player_data['country'])
            country_emote = get_flag_emote(player_data['country'])
            location_parts.append(f"- **Citizenship / Nationality:** {country_emote} {country_name}")
    
    if player_data.get('region'):
        region_name = regions_service.get_region_name(player_data['region'])
        if region_name:
            # Get the full region data to access the globe_emote field
            region_data = regions_service.get_region_by_code(player_data['region'])
            if region_data and region_data.get('globe_emote'):
                # Use the globe_emote from regions data if available
                region_globe_emote = get_globe_emote(region_data.get('globe_emote'))
            location_parts.append(f"- **Region of Residence:** {region_name}")
    
    if location_parts:
        location_info = "\n".join(location_parts)
        embed.add_field(name=f"{region_globe_emote} Location", value=location_info, inline=False)
        # Add spacing between sections
        embed.add_field(name="\n\n", value="\n\n", inline=False)
    
    # MMR Information
    if mmr_data:
        # Get the canonical race order
        race_order = races_service.get_race_order()
        
        # Convert dict to list of dicts for processing (now with full records)
        mmr_list = [{"race": race, **record} for race, record in mmr_data.items()]
        
        # Sort MMR data by race order
        def race_sort_key(mmr_entry):
            race_code = mmr_entry['race']
            try:
                return race_order.index(race_code)
            except ValueError:
                return len(race_order)  # Put unknown races at the end
        
        sorted_mmr_data = sorted(mmr_list, key=race_sort_key)
        
        # Separate BW and SC2 races (already in correct order)
        bw_mmrs = [m for m in sorted_mmr_data if m['race'].startswith('bw_')]
        sc2_mmrs = [m for m in sorted_mmr_data if m['race'].startswith('sc2_')]
        
        # Calculate overall statistics
        total_games_played = 0
        total_games_won = 0
        total_games_lost = 0
        total_games_drawn = 0
        last_played_overall = None
        
        for mmr_entry in sorted_mmr_data:
            total_games_played += mmr_entry.get('games_played', 0)
            total_games_won += mmr_entry.get('games_won', 0)
            total_games_lost += mmr_entry.get('games_lost', 0)
            total_games_drawn += mmr_entry.get('games_drawn', 0)
            
            # Track the most recent last_played timestamp
            last_played_dt = mmr_entry.get('last_played')
            if last_played_dt:
                if last_played_overall is None or last_played_dt > last_played_overall:
                    last_played_overall = last_played_dt
        
        # Add Overall Statistics section if player has played games
        if total_games_played > 0:
            overall_win_rate = (total_games_won / total_games_played * 100) if total_games_played > 0 else 0
            overall_stats = f"- **Total Games:** {total_games_played}\n"
            overall_stats += f"- **Record:** {total_games_won}W-{total_games_lost}L-{total_games_drawn}D\n"
            overall_stats += f"- **Win Rate:** {overall_win_rate:.1f}%"
            
            # Add last played date if available
            if last_played_overall:
                if last_played_overall.tzinfo is None:
                    last_played_overall = last_played_overall.replace(tzinfo=timezone.utc)
                discord_ts = f"<t:{int(last_played_overall.timestamp())}:f>"
                overall_stats += f"\n- **Last Played:** {discord_ts}"
            
            embed.add_field(name="📈 Overall Statistics", value=overall_stats, inline=False)
            # Add spacing between sections
            embed.add_field(name="\n\n", value="\n\n", inline=False)
        
        # BW MMRs
        if bw_mmrs:
            bw_text = ""
            for mmr_entry in bw_mmrs:
                race_code = mmr_entry['race']
                race_name = races_service.get_race_name(race_code)
                race_emote = get_race_emote(race_code)
                
                # Get rank for this player-race combination
                rank = ranking_service.get_letter_rank(user.id, race_code)
                rank_emote = get_rank_emote(rank)
                
                mmr_value = int(mmr_entry['mmr'])
                games_played = mmr_entry.get('games_played', 0)
                games_won = mmr_entry.get('games_won', 0)
                games_lost = mmr_entry.get('games_lost', 0)
                games_drawn = mmr_entry.get('games_drawn', 0)
                
                # Display "Unranked" for races with 0 games
                if games_played == 0:
                    bw_text += f"- {rank_emote} {race_emote} **{race_name}:** No MMR • No games played"
                else:
                    bw_text += f"- {rank_emote} {race_emote} **{race_name}:** {mmr_value} MMR"
                    
                    # Win/Loss record
                    win_rate = (games_won / games_played * 100) if games_played > 0 else 0
                    bw_text += f" • {games_won}W-{games_lost}L-{games_drawn}D ({win_rate:.1f}%)"
                
                # Add last played information if available
                last_played_dt = mmr_entry.get('last_played')
                if last_played_dt and games_played > 0:
                    # Ensure the datetime object is timezone-aware (it should be UTC)
                    if last_played_dt.tzinfo is None:
                        last_played_dt = last_played_dt.replace(tzinfo=timezone.utc)
                    
                    discord_ts = f"<t:{int(last_played_dt.timestamp())}:f>"
                    bw_text += f"\n  - **Last Played:** {discord_ts}"

                bw_text += "\n"
            
            bw_emote = get_game_emote('brood_war')
            embed.add_field(name=f"{bw_emote} Brood War MMR", value=bw_text.strip(), inline=False)
        
        # SC2 MMRs
        if sc2_mmrs:
            # Add spacing if BW MMRs exist
            if bw_mmrs:
                embed.add_field(name="\n\n", value="\n\n", inline=False)
            sc2_text = ""
            for mmr_entry in sc2_mmrs:
                race_code = mmr_entry['race']
                race_name = races_service.get_race_name(race_code)
                race_emote = get_race_emote(race_code)
                
                # Get rank for this player-race combination
                rank = ranking_service.get_letter_rank(user.id, race_code)
                rank_emote = get_rank_emote(rank)
                
                mmr_value = int(mmr_entry['mmr'])
                games_played = mmr_entry.get('games_played', 0)
                games_won = mmr_entry.get('games_won', 0)
                games_lost = mmr_entry.get('games_lost', 0)
                games_drawn = mmr_entry.get('games_drawn', 0)
                
                # Display "Unranked" for races with 0 games
                if games_played == 0:
                    sc2_text += f"- {rank_emote} {race_emote} **{race_name}:** No MMR • No games played"
                else:
                    sc2_text += f"- {rank_emote} {race_emote} **{race_name}:** {mmr_value} MMR"
                    
                    # Win/Loss record
                    win_rate = (games_won / games_played * 100) if games_played > 0 else 0
                    sc2_text += f" • {games_won}W-{games_lost}L-{games_drawn}D ({win_rate:.1f}%)"

                # Add last played information if available
                last_played_dt = mmr_entry.get('last_played')
                if last_played_dt and games_played > 0:
                    # Ensure the datetime object is timezone-aware (it should be UTC)
                    if last_played_dt.tzinfo is None:
                        last_played_dt = last_played_dt.replace(tzinfo=timezone.utc)
                        
                    discord_ts = f"<t:{int(last_played_dt.timestamp())}:f>"
                    sc2_text += f"\n  - **Last Played:** {discord_ts}"

                sc2_text += "\n"
            
            sc2_emote = get_game_emote('starcraft_2')
            embed.add_field(name=f"{sc2_emote} StarCraft II MMR", value=sc2_text.strip(), inline=False)
    else:
        embed.add_field(
            name="🎮 MMR Information",
            value="No ranked games played yet. Join the queue to start your MMR journey!",
            inline=False
        )
    
    # Add spacing between sections
    embed.add_field(name="\n\n", value="\n\n", inline=False)
    
    # Setup Status
    status_parts = []
    
    if player_data.get('accepted_tos'):
        status_parts.append("- ✅ Terms of Service accepted")
    else:
        status_parts.append("- ❌ Terms of Service not accepted")
    
    if player_data.get('completed_setup'):
        status_parts.append("- ✅ Setup completed")
    else:
        status_parts.append("- ⚠️ Setup incomplete")
    
    # Remaining aborts
    remaining_aborts = player_data.get('remaining_aborts', 3)
    status_parts.append(f"- 🚫 {remaining_aborts}/3 match aborts remaining")
    
    status_text = "\n".join(status_parts)
    embed.add_field(name="📊 Account Status", value=status_text, inline=False)
    
    # Footer
    embed.set_footer(text=f"Discord ID: {user.name} • {user.id}")
    
    return embed


# Register Command
def register_profile_command(tree: app_commands.CommandTree):
    """Register the profile command"""
    @tree.command(
        name="profile",
        description="View your player profile"
    )
    async def profile(interaction: discord.Interaction):
        await profile_command(interaction)
    
    return profile

