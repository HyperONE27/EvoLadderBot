"""
Admin commands for bot management and intervention.

Provides a comprehensive admin interface with:
- Inspection tools (snapshots, player/match states)
- Modification commands (conflict resolution, MMR adjustments)
- Simple confirm/cancel flows with all parameters in slash commands

All admin commands and components:
- Start with "Admin" in their name
- Are restricted to admins only (even in public channels)
- Are exempt from DMs-only rule
"""

import discord
from discord import app_commands
from discord.ui import View
from typing import Optional, Set
import json
import io
import time
import polars as pl

from src.backend.services.app_context import admin_service, data_access_service, ranking_service, races_service
from src.backend.services.process_pool_health import get_bot_instance
from src.bot.components.confirm_restart_cancel_buttons import ConfirmButton, CancelButton
from src.bot.config import GLOBAL_TIMEOUT
from src.bot.utils.message_helpers import (
    queue_user_send,
    queue_interaction_edit,
    queue_interaction_response,
    queue_interaction_defer,
    queue_followup,
    queue_edit_original
)
from src.bot.utils.discord_utils import (
    format_discord_timestamp,
    get_current_unix_timestamp,
    get_flag_emote,
    get_race_emote,
    get_rank_emote,
    get_globe_emote,
    get_game_emote,
    send_ephemeral_response
)


# ========== USER RESOLVER HELPER ==========

async def resolve_user_input(user_input: str, interaction: discord.Interaction) -> Optional[dict]:
    """
    Universal user resolver that handles mentions, Discord IDs, and usernames.
    
    Args:
        user_input: User input as @mention, Discord ID (numeric string), or username
        interaction: Discord interaction for client access
        
    Returns:
        Dict with 'discord_uid' and 'username' if successful, None otherwise
        
    Handles:
        - @mentions: <@123456789> or <@!123456789>
        - Discord IDs: "123456789"
        - Usernames: "notatruckdriver" (searches registered players in bot DB)
    """
    # Try to parse as mention first
    if user_input.startswith('<@') and user_input.endswith('>'):
        user_id_str = user_input.strip('<@!>')
        try:
            user_id = int(user_id_str)
            # Fetch from Discord to get username
            try:
                discord_user = await interaction.client.fetch_user(user_id)
                return {
                    'discord_uid': user_id,
                    'username': discord_user.name
                }
            except Exception:
                # User exists as ID but couldn't fetch from Discord
                return {
                    'discord_uid': user_id,
                    'username': f"User#{user_id}"
                }
        except ValueError:
            pass
    
    # Try to parse as numeric Discord ID
    try:
        user_id = int(user_input)
        # Fetch from Discord to get username
        try:
            discord_user = await interaction.client.fetch_user(user_id)
            return {
                'discord_uid': user_id,
                'username': discord_user.name
            }
        except Exception:
            # Valid ID format but user doesn't exist
            return None
    except ValueError:
        # Not a numeric ID, try as username
        pass
    
    # Try to resolve as username from bot database
    # Use admin_service.resolve_user which searches player_name, discord_username, battletag, etc.
    user_info = await admin_service.resolve_user(user_input)
    
    if user_info:
        discord_uid = user_info.get('discord_uid')
        # Fetch actual Discord username
        try:
            discord_user = await interaction.client.fetch_user(discord_uid)
            return {
                'discord_uid': discord_uid,
                'username': discord_user.name
            }
        except Exception:
            # Fallback to player_name from DB if Discord fetch fails
            return {
                'discord_uid': discord_uid,
                'username': user_info.get('player_name', f"User#{discord_uid}")
            }
    
    return None


# ========== NOTIFICATION HELPER ==========

async def send_player_notification(discord_uid: int, embed: discord.Embed) -> bool:
    """
    Send a DM notification to a player using the global bot instance.
    
    Args:
        discord_uid: Player's Discord ID
        embed: Discord embed to send
        
    Returns:
        True if sent successfully, False otherwise
    """
    bot_instance = get_bot_instance()
    if not bot_instance:
        print(f"[AdminCommand] ❌ ERROR: Cannot send notification - bot instance not available")
        print(f"[AdminCommand] This should never happen if bot_setup completed successfully")
        return False
    
    print(f"[AdminCommand] ✅ Bot instance available, sending notification to {discord_uid}")
    
    try:
        user = await bot_instance.fetch_user(discord_uid)
        if user:
            await queue_user_send(user, embed=embed)
            print(f"[AdminCommand] Sent notification to user {discord_uid}")
            return True
        else:
            print(f"[AdminCommand] Could not fetch user {discord_uid}")
            return False
    except discord.Forbidden:
        print(f"[AdminCommand] Cannot DM user {discord_uid} (DMs disabled or blocked)")
        return False
    except discord.HTTPException as e:
        print(f"[AdminCommand] HTTP error sending DM to {discord_uid}: {e}")
        return False
    except Exception as e:
        print(f"[AdminCommand] ERROR sending notification to {discord_uid}: {e}")
        return False


# ========== FORMATTING UTILITIES ==========

def format_system_stats_embed(snapshot: dict) -> discord.Embed:
    """
    Format system stats into an embed (Memory, DataFrames, Write Queue, Process Pool).
    
    Returns discord.Embed with system stats only.
    """
    embed = discord.Embed(
        title="🔍 Admin System Snapshot",
        description=f"**Timestamp:** {snapshot['timestamp']}",
        color=discord.Color.blue()
    )
    
    # Memory field
    if 'error' in snapshot['memory']:
        memory_text = snapshot['memory']['error']
    else:
        memory_text = f"RSS: {snapshot['memory']['rss_mb']:.1f} MB\nUsage: {snapshot['memory']['percent']:.1f}%"
    embed.add_field(name='💾 Memory', value=memory_text, inline=True)
    
    # DataFrames field
    df_lines = []
    for df_name, df_stats in snapshot['data_frames'].items():
        df_lines.append(f"**{df_name}**: {df_stats['rows']:,} rows ({df_stats['size_mb']:.2f} MB)")
    embed.add_field(name='📊 DataFrames', value='\n'.join(df_lines), inline=False)
    
    # Write Queue field
    wq = snapshot['write_queue']
    success_rate = (wq['total_completed'] / wq['total_queued'] * 100) if wq['total_queued'] > 0 else 100.0
    wq_text = f"Depth: {wq['depth']}\nCompleted: {wq['total_completed']}\nSuccess: {success_rate:.1f}%"
    embed.add_field(name='📝 Write Queue', value=wq_text, inline=True)
    
    # Process Pool field
    pp_text = f"Workers: {snapshot['process_pool'].get('workers', 0)}\nRestarts: {snapshot['process_pool'].get('restart_count', 0)}"
    embed.add_field(name='⚙️ Process Pool', value=pp_text, inline=True)
    
    return embed


def format_queue_embed(snapshot: dict) -> discord.Embed:
    """
    Format queue players into a separate embed with description (not fields).
    
    Returns discord.Embed showing up to 30 players in queue.
    Character budget: 63 chars per player, ~1900 chars for 30 players.
    """
    queue_size = snapshot['queue']['size']
    embed = discord.Embed(
        title="🎮 Queue Status",
        color=discord.Color.green()
    )
    
    if queue_size == 0:
        embed.description = "No players currently in queue."
    else:
        players = snapshot['queue'].get('players', [])
        player_count = len(players)
        
        # Show up to 30 players
        displayed_players = players[:30]
        player_lines = [f"  • {p}" for p in displayed_players]
        
        description = f"**Players in Queue:** {queue_size}\n" + "\n".join(player_lines)
        
        # Add "... and X more" if truncated
        if player_count > 30:
            description += f"\n_... and {player_count - 30} more_"
        
        embed.description = description
    
    return embed


def format_matches_embed(snapshot: dict) -> discord.Embed:
    """
    Format active matches into a separate embed with description (not fields).
    
    Returns discord.Embed showing up to 15 active matches.
    Character budget: 68 chars per match, ~1000 chars for 15 matches.
    Total 3 embeds: stays under 6000 char limit with buffer.
    """
    match_count = snapshot['matches']['active']
    embed = discord.Embed(
        title="⚔️ Active Matches",
        color=discord.Color.orange()
    )
    
    if match_count == 0:
        embed.description = "No active matches."
    else:
        matches = snapshot['matches'].get('match_list', [])
        match_list_count = len(matches)
        
        # Show up to 15 matches
        displayed_matches = matches[:15]
        match_lines = [f"  • {m}" for m in displayed_matches]
        
        description = f"**Active Matches:** {match_count}\n" + "\n".join(match_lines)
        
        # Add "... and X more" if truncated
        if match_list_count > 15:
            description += f"\n_... and {match_list_count - 15} more_"
        
        embed.description = description
    
    return embed


def format_conflict_match(conflict: dict) -> str:
    """Format conflict match for human reading."""
    
    def format_report(report):
        if report is None:
            return "Not reported"
        report_map = {0: "Draw", 1: "I won", 2: "I lost", -1: "Aborted", -3: "I aborted"}
        return report_map.get(report, f"Unknown ({report})")
    
    lines = [
        f"**Match #{conflict['match_id']} - Conflict**",
        f"Map: {conflict['map']} | Server: {conflict['server']}",
        f"Played: {conflict['played_at']}",
        "",
        f"**Player 1:** {conflict['player_1']['name']}",
        f"  Race: {conflict['player_1']['race']}",
        f"  Reported: {format_report(conflict['player_1']['report'])}",
        f"  Replay: {'✅' if conflict['player_1']['replay'] else '❌'}",
        "",
        f"**Player 2:** {conflict['player_2']['name']}",
        f"  Race: {conflict['player_2']['race']}",
        f"  Reported: {format_report(conflict['player_2']['report'])}",
        f"  Replay: {'✅' if conflict['player_2']['replay'] else '❌'}"
    ]
    
    return "\n".join(lines)


def format_player_state(state: dict, discord_user: discord.User = None) -> discord.Embed:
    """
    Format player state into a profile-style embed matching /profile layout.
    All data is pre-calculated by the backend; this function ONLY formats it.
    
    Args:
        state: Player state dictionary from backend
        discord_user: Optional Discord User object for avatar
    
    Returns:
        discord.Embed with formatted player state
    """
    from datetime import timezone
    
    def format_report(report):
        if report is None:
            return "Not reported"
        report_map = {0: "Draw", 1: "I won", 2: "I lost", -1: "Aborted", -3: "I aborted"}
        return report_map.get(report, f"Unknown ({report})")
    
    info = state['player_info']
    if not info:
        embed = discord.Embed(
            title="❌ Player Not Found",
            color=discord.Color.red()
        )
        return embed
    
    # Determine embed color based on setup status
    if info.get('completed_setup'):
        color = discord.Color.green()
        status_icon = "✅"
    else:
        color = discord.Color.orange()
        status_icon = "⚠️"
    
    embed = discord.Embed(
        title=f"{status_icon} [Admin] Player Profile: {info.get('player_name', 'Unknown')}",
        color=color
    )
    
    # Set thumbnail to user avatar if available
    if discord_user and discord_user.display_avatar:
        embed.set_thumbnail(url=discord_user.display_avatar.url)
    
    # Basic Information
    basic_info_parts = [
        f"- **User ID:** <@{info['discord_uid']}>",
        f"- **Player Name:** {info['player_name']}",
        f"- **BattleTag:** {info.get('battletag', 'Not set')}"
    ]
    
    # Alternative IDs if they exist
    alt_ids = []
    if info.get('alt_player_name_1'):
        alt_ids.append(info['alt_player_name_1'])
    if info.get('alt_player_name_2'):
        alt_ids.append(info['alt_player_name_2'])
    
    if alt_ids:
        basic_info_parts.append(f"- **Alt IDs:** {', '.join(alt_ids)}")
    
    basic_info = "\n".join(basic_info_parts)
    embed.add_field(name="📋 Basic Information", value=basic_info, inline=False)
    
    # Add spacing between sections
    embed.add_field(name="", value="\u3164", inline=False)
    
    # Location Information (using pre-calculated data from backend)
    location_parts = []
    region_globe_emote = "🌐"
    
    if info.get('country') and info.get('country_name'):
        country_emote = get_flag_emote(info['country'])
        location_parts.append(f"- **Citizenship / Nationality:** {country_emote} {info['country_name']}")
    
    if info.get('region') and info.get('region_name'):
        if info.get('region_globe_emote'):
            region_globe_emote = get_globe_emote(info['region_globe_emote'])
        location_parts.append(f"- **Region of Residence:** {info['region_name']}")
    
    if location_parts:
        location_info = "\n".join(location_parts)
        embed.add_field(name=f"{region_globe_emote} Location", value=location_info, inline=False)
        embed.add_field(name="", value="\u3164", inline=False)
    
    # MMR Information (using pre-calculated data from backend)
    mmr_data = state['mmrs']
    if mmr_data:
        # Convert dict to list of dicts for processing
        mmr_list = [{"race": race, **record} for race, record in mmr_data.items()]
        
        # Sort MMR data by pre-calculated sort_order
        sorted_mmr_data = sorted(mmr_list, key=lambda m: m.get('sort_order', 999))
        
        # Separate BW and SC2 races using pre-calculated flags
        bw_mmrs = [m for m in sorted_mmr_data if m.get('is_bw', False)]
        sc2_mmrs = [m for m in sorted_mmr_data if m.get('is_sc2', False)]
        
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
            
            last_played_dt = mmr_entry.get('last_played')
            if last_played_dt:
                if last_played_overall is None or last_played_dt > last_played_overall:
                    last_played_overall = last_played_dt
        
        # Add Overall Statistics section
        if total_games_played > 0:
            overall_win_rate = (total_games_won / total_games_played * 100) if total_games_played > 0 else 0
            overall_stats = f"- **Total Games:** {total_games_played}\n"
            overall_stats += f"- **Record:** {total_games_won}W-{total_games_lost}L-{total_games_drawn}D\n"
            overall_stats += f"- **Win Rate:** {overall_win_rate:.1f}%"
            
            if last_played_overall:
                if last_played_overall.tzinfo is None:
                    last_played_overall = last_played_overall.replace(tzinfo=timezone.utc)
                discord_ts = f"<t:{int(last_played_overall.timestamp())}:f>"
                overall_stats += f"\n- **Last Played:** {discord_ts}"
            
            embed.add_field(name="📈 Overall Statistics", value=overall_stats, inline=False)
            embed.add_field(name="", value="\u3164", inline=False)
        
        # BW MMRs (using pre-calculated data from backend)
        if bw_mmrs:
            bw_text = ""
            for mmr_entry in bw_mmrs:
                race_code = mmr_entry['race']
                race_name = mmr_entry.get('race_name', race_code)  # Pre-calculated in backend
                race_emote = get_race_emote(race_code)
                
                rank = mmr_entry.get('rank')  # Pre-calculated in backend
                rank_emote = get_rank_emote(rank)
                
                mmr_value = int(mmr_entry['mmr'])
                games_played = mmr_entry.get('games_played', 0)
                games_won = mmr_entry.get('games_won', 0)
                games_lost = mmr_entry.get('games_lost', 0)
                games_drawn = mmr_entry.get('games_drawn', 0)
                
                if games_played == 0:
                    bw_text += f"- {rank_emote} {race_emote} **{race_name}:** No MMR • No games played\n"
                else:
                    bw_text += f"- {rank_emote} {race_emote} **{race_name}:** {mmr_value} MMR"
                    win_rate = (games_won / games_played * 100) if games_played > 0 else 0
                    bw_text += f" • {games_won}W-{games_lost}L-{games_drawn}D ({win_rate:.1f}%)\n"
                    
                    # Add time-stratified stats if available
                    if info.get('time_stats') and race_code in info['time_stats']:
                        time_stats = info['time_stats'][race_code]
                        for period in ['14d', '30d', '90d']:
                            stats = time_stats.get(period, {'wins': 0, 'losses': 0, 'draws': 0, 'total': 0})
                            w, l, d, total = stats['wins'], stats['losses'], stats['draws'], stats['total']
                            wr = (w / total * 100) if total > 0 else 0.0
                            period_label = {'14d': 'Last 14 days', '30d': 'Last 30 days', '90d': 'Last 90 days'}[period]
                            bw_text += f"  - **{period_label}:** {w}W-{l}L-{d}D ({wr:.1f}%)\n"
                    
                    last_played_dt = mmr_entry.get('last_played')
                    if last_played_dt:
                        if last_played_dt.tzinfo is None:
                            last_played_dt = last_played_dt.replace(tzinfo=timezone.utc)
                        discord_ts = f"<t:{int(last_played_dt.timestamp())}:f>"
                        bw_text += f"  - **Last Played:** {discord_ts}\n"
            
            bw_emote = get_game_emote('brood_war')
            embed.add_field(name=f"{bw_emote} Brood War MMR", value=bw_text.strip(), inline=False)
        
        # SC2 MMRs (using pre-calculated data from backend)
        if sc2_mmrs:
            if bw_mmrs:
                embed.add_field(name="", value="\u3164", inline=False)
            
            sc2_text = ""
            for mmr_entry in sc2_mmrs:
                race_code = mmr_entry['race']
                race_name = mmr_entry.get('race_name', race_code)  # Pre-calculated in backend
                race_emote = get_race_emote(race_code)
                
                rank = mmr_entry.get('rank')  # Pre-calculated in backend
                rank_emote = get_rank_emote(rank)
                
                mmr_value = int(mmr_entry['mmr'])
                games_played = mmr_entry.get('games_played', 0)
                games_won = mmr_entry.get('games_won', 0)
                games_lost = mmr_entry.get('games_lost', 0)
                games_drawn = mmr_entry.get('games_drawn', 0)
                
                if games_played == 0:
                    sc2_text += f"- {rank_emote} {race_emote} **{race_name}:** No MMR • No games played\n"
                else:
                    sc2_text += f"- {rank_emote} {race_emote} **{race_name}:** {mmr_value} MMR"
                    win_rate = (games_won / games_played * 100) if games_played > 0 else 0
                    sc2_text += f" • {games_won}W-{games_lost}L-{games_drawn}D ({win_rate:.1f}%)\n"
                    
                    # Add time-stratified stats if available
                    if info.get('time_stats') and race_code in info['time_stats']:
                        time_stats = info['time_stats'][race_code]
                        for period in ['14d', '30d', '90d']:
                            stats = time_stats.get(period, {'wins': 0, 'losses': 0, 'draws': 0, 'total': 0})
                            w, l, d, total = stats['wins'], stats['losses'], stats['draws'], stats['total']
                            wr = (w / total * 100) if total > 0 else 0.0
                            period_label = {'14d': 'Last 14 days', '30d': 'Last 30 days', '90d': 'Last 90 days'}[period]
                            sc2_text += f"  - **{period_label}:** {w}W-{l}L-{d}D ({wr:.1f}%)\n"
                    
                    last_played_dt = mmr_entry.get('last_played')
                    if last_played_dt:
                        if last_played_dt.tzinfo is None:
                            last_played_dt = last_played_dt.replace(tzinfo=timezone.utc)
                        discord_ts = f"<t:{int(last_played_dt.timestamp())}:f>"
                        sc2_text += f"  - **Last Played:** {discord_ts}\n"
            
            sc2_emote = get_game_emote('starcraft_2')
            embed.add_field(name=f"{sc2_emote} StarCraft II MMR", value=sc2_text.strip(), inline=False)

    # Account Status (matching /profile format)
    embed.add_field(name="", value="\u3164", inline=False)
    status_parts = []
    
    if info.get('accepted_tos'):
        status_parts.append("- ✅ Terms of Service accepted")
    else:
        status_parts.append("- ❌ Terms of Service not accepted")
    
    if info.get('completed_setup'):
        status_parts.append("- ✅ Setup completed")
    else:
        status_parts.append("- ⚠️ Setup incomplete")
    
    # Remaining aborts
    remaining_aborts = info.get('remaining_aborts', 3)
    status_parts.append(f"- 🚫 {remaining_aborts}/3 match aborts remaining")
    
    status_text = "\n".join(status_parts)
    embed.add_field(name="📊 Account Status", value=status_text, inline=False)

    # Admin-specific: Queue Status
    embed.add_field(name="", value="\u3164", inline=False)
    queue_status = f"**In Queue:** {'✅ Yes' if state['queue_status']['in_queue'] else '❌ No'}"
    if state['queue_status']['details']:
        details = state['queue_status']['details']
        queue_status += f"\n**Wait Time:** {details['wait_time']:.0f}s\n**Races:** {', '.join(details['races'])}"
    embed.add_field(name="🎯 Queue Status", value=queue_status, inline=False)
    
    # Admin-specific: Most Recent Matches (compact format to avoid 1024 char limit)
    if state['active_matches']:
        embed.add_field(name="", value="\u3164", inline=False)
        match_text = ""
        # Show max 5 matches, include player IDs
        for match in state['active_matches'][:5]:
            opponent_id = match['opponent_discord_uid']
            opponent_name = match['opponent_name']
            my = format_report(match['my_report'])
            their = format_report(match['their_report'])
            match_text += f"• **#{match['match_id']}** vs <@{opponent_id}> ({opponent_name}): Me={my}, Them={their}\n"
        
        if len(state['active_matches']) > 5:
            match_text += f"... and {len(state['active_matches']) - 5} more matches"
        
        embed.add_field(name="📜 Most Recent Matches", value=match_text.strip(), inline=False)
    
    # Footer with Discord ID
    embed.set_footer(text=f"Discord ID: {info.get('player_name', 'Unknown')} • {info['discord_uid']}")
    
    return embed


# Load admin IDs from admins.json
def _load_admin_ids() -> Set[int]:
    """Load admin Discord IDs from data/misc/admins.json."""
    try:
        with open('data/misc/admins.json', 'r', encoding='utf-8') as f:
            admins_data = json.load(f)
        
        admin_ids = {
            admin['discord_id'] 
            for admin in admins_data 
            if isinstance(admin, dict) 
            and 'discord_id' in admin
            and isinstance(admin['discord_id'], int)
        }
        
        print(f"[AdminCommands] Loaded {len(admin_ids)} admin(s)")
        return admin_ids
    
    except FileNotFoundError:
        print("[AdminCommands] WARNING: admins.json not found. No admins loaded.")
        return set()
    except Exception as e:
        print(f"[AdminCommands] ERROR loading admins: {e}")
        return set()


def _load_owner_ids() -> Set[int]:
    """Load owner Discord IDs from data/misc/admins.json."""
    try:
        with open('data/misc/admins.json', 'r', encoding='utf-8') as f:
            admins_data = json.load(f)
        
        owner_ids = {
            admin['discord_id'] 
            for admin in admins_data 
            if isinstance(admin, dict) 
            and 'discord_id' in admin
            and isinstance(admin['discord_id'], int)
            and admin.get('role') == 'owner'
        }
        
        print(f"[AdminCommands] Loaded {len(owner_ids)} owner(s)")
        return owner_ids
    
    except FileNotFoundError:
        print("[AdminCommands] WARNING: admins.json not found. No owners loaded.")
        return set()
    except Exception as e:
        print(f"[AdminCommands] ERROR loading owners: {e}")
        return set()


# Global set of admin and owner IDs (loaded once at module import)
ADMIN_IDS = _load_admin_ids()
OWNER_IDS = _load_owner_ids()


def is_admin(interaction: discord.Interaction) -> bool:
    """Check if user is an admin (loaded from admins.json)."""
    return interaction.user.id in ADMIN_IDS


def is_owner(interaction: discord.Interaction) -> bool:
    """Check if user is an owner (loaded from admins.json)."""
    return interaction.user.id in OWNER_IDS


def admin_only():
    """
    Decorator to restrict commands to admins.
    
    Note: Admin commands are exempt from DMs-only rule and can be used anywhere.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        if not is_admin(interaction):
            await queue_interaction_response(
                interaction,
                embed=discord.Embed(
                    title="🚫 Admin Access Denied",
                    description="This command is restricted to administrators.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return False
        return True
    
    return app_commands.check(predicate)


def owner_only():
    """
    Decorator to restrict commands to owners.
    
    Owner-only commands are the highest privilege level.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        if not is_owner(interaction):
            await queue_interaction_response(
                interaction,
                embed=discord.Embed(
                    title="🚫 Owner Access Denied",
                    description="This command is restricted to bot owners.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return False
        return True
    
    return app_commands.check(predicate)


class AdminConfirmationView(View):
    """
    Admin confirmation view with caller-specific restrictions.
    
    Buttons can only be interacted with by the specific admin who initiated the command,
    even if other admins are present. This prevents accidental or unauthorized interactions.
    
    IMPORTANT: interaction_check properly handles unauthorized clicks WITHOUT consuming
    the view's interaction lifecycle, so the authorized admin can still interact later.
    """
    
    def __init__(self, timeout: int = None):
        """
        Initialize admin confirmation view.
        
        Args:
            timeout: View timeout in seconds (default: GLOBAL_TIMEOUT from config)
        """
        super().__init__(timeout=timeout or GLOBAL_TIMEOUT)
        self._original_admin_id: Optional[int] = None
    
    def set_admin(self, admin_id: int):
        """Set the admin who initiated this view (the only one who can interact with buttons)."""
        self._original_admin_id = admin_id
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Ensure only the original admin who initiated the command can interact with buttons.
        
        This method handles unauthorized interactions by:
        1. Deferring the interaction (prevents "interaction failed" error)
        2. Sending an ephemeral followup (shows helpful message to unauthorized user)
        3. Returning False (prevents button callback from running)
        4. Keeping the view alive (authorized admin can still interact)
        """
        if interaction.user.id != self._original_admin_id:
            # Defer first to acknowledge the interaction without consuming response
            try:
                await queue_interaction_defer(interaction, ephemeral=True)
            except discord.errors.NotFound:
                # Interaction already acknowledged (shouldn't happen, but handle gracefully)
                pass
            
            # Send ephemeral followup instead of response to avoid consuming interaction
            try:
                await queue_followup(
                    interaction,
                    embed=discord.Embed(
                        title="🚫 Admin Button Restricted",
                        description=f"Only <@{self._original_admin_id}> can interact with these buttons.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
            except Exception as e:
                print(f"[AdminConfirmationView] Failed to send rejection message: {e}")
            
            # Return False to prevent callback execution
            # The view remains active for the authorized admin
            return False
        
        return True
    
    async def on_timeout(self):
        """
        Handle view timeout - disable all buttons and provide feedback.
        
        This is called when the view times out (default 5 minutes).
        Note: We can't edit the message here as we don't have a reference to it,
        but the buttons will automatically be disabled by Discord.
        """
        self.clear_items()
        print(f"🧹 [AdminConfirmationView] Timed out and cleaned up for admin {self._original_admin_id}")


class AdminDismissView(discord.ui.View):
    """Simple dismissal view for informational admin commands."""
    
    def __init__(self, timeout: int = None):
        """Initialize view with a timeout and interaction check."""
        super().__init__(timeout=timeout or GLOBAL_TIMEOUT)
        self._original_admin_id: Optional[int] = None
        self._interaction_to_delete: Optional[discord.Interaction] = None
    
    def set_admin(self, admin_id: int):
        """Set the admin who initiated this view (the only one who can interact with buttons)."""
        self._original_admin_id = admin_id
    
    def set_interaction(self, interaction: discord.Interaction):
        """Store the interaction for deletion purposes."""
        self._interaction_to_delete = interaction
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original admin can interact with buttons."""
        if interaction.user.id != self._original_admin_id:
            try:
                await queue_interaction_defer(interaction, ephemeral=True)
            except discord.errors.NotFound:
                pass
            
            try:
                await queue_followup(
                    interaction,
                    embed=discord.Embed(
                        title="🚫 Admin Button Restricted",
                        description=f"Only <@{self._original_admin_id}> can interact with these buttons.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
            except Exception as e:
                print(f"[AdminDismissView] Failed to send rejection message: {e}")
            
            return False
        
        return True
    
    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.secondary, emoji="🗑️")
    async def dismiss_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Dismiss and delete the admin info message."""
        try:
            await interaction.response.defer()
            if self._interaction_to_delete:
                await self._interaction_to_delete.delete_original_response()
            else:
                await interaction.message.delete()
            self.stop()
            self.clear_items()
            print(f"🧹 [AdminDismissView] Cleaned up for admin {self._original_admin_id}")
        except Exception as e:
            print(f"[AdminDismissView] Failed to delete message: {e}")
            try:
                await queue_followup(
                    interaction,
                    content="❌ Failed to delete message.",
                    ephemeral=True
                )
            except:
                pass


def register_admin_commands(tree: app_commands.CommandTree):
    """Register all admin commands."""
    
    admin_group = app_commands.Group(
        name="admin",
        description="Administrative tools for bot management (Admin Only)"
    )
    
    @admin_group.command(name="snapshot", description="[Admin] Get system state snapshot")
    @admin_only()
    async def admin_snapshot(interaction: discord.Interaction):
        """Display comprehensive system snapshot."""
        await queue_interaction_defer(interaction)
        
        snapshot = admin_service.get_system_snapshot()
        
        # Create 3 separate embeds
        embed_stats = format_system_stats_embed(snapshot)
        embed_queue = format_queue_embed(snapshot)
        embed_matches = format_matches_embed(snapshot)
        
        # Create dismiss view for this informational command
        view = AdminDismissView()
        view.set_admin(interaction.user.id)
        view.set_interaction(interaction)
        
        # Send all 3 embeds
        await queue_followup(interaction, embeds=[embed_stats, embed_queue, embed_matches], view=view)
    
    @admin_group.command(name="player", description="[Admin] View player state")
    @app_commands.describe(user="Player's @mention, username, or Discord ID")
    @admin_only()
    async def admin_player(interaction: discord.Interaction, user: str):
        """Display complete player state."""
        await queue_interaction_defer(interaction)
        
        # Resolve user input (mention, ID, or username)
        user_info = await resolve_user_input(user, interaction)
        
        if user_info is None:
            await queue_followup(
                interaction,
                content=f"❌ Could not find user: {user}",
            )
            return
        
        uid = user_info['discord_uid']
        state = await admin_service.get_player_full_state(uid)
        
        # Try to get the Discord user object for avatar
        try:
            discord_user = await interaction.client.fetch_user(uid)
        except:
            discord_user = None
        
        embed = format_player_state(state, discord_user)
        
        # Create dismiss view for this informational command
        view = AdminDismissView()
        view.set_admin(interaction.user.id)
        view.set_interaction(interaction)
        
        await queue_followup(interaction, embed=embed, view=view)
    
    @admin_group.command(name="match", description="[Admin] View match state")
    @app_commands.describe(match_id="Match ID")
    @admin_only()
    async def admin_match(interaction: discord.Interaction, match_id: int):
        """Display complete match state."""
        await queue_interaction_defer(interaction)
        
        state = admin_service.get_match_full_state(match_id)
        
        if 'error' in state:
            await queue_followup(
                interaction,
                content=f"Error: {state['error']}",
            )
            return
        
        import json
        formatted = json.dumps(state, indent=2, default=str)
        
        files_to_attach = [
            discord.File(
                io.BytesIO(formatted.encode()),
                filename=f"admin_match_{match_id}.json"
            )
        ]
        
        match_data = state['match_data']
        p1_info = state['players']['player_1']
        p2_info = state['players']['player_2']
        
        # Get player names
        p1_name = p1_info.get('player_name', 'Unknown') if p1_info else 'Unknown'
        p2_name = p2_info.get('player_name', 'Unknown') if p2_info else 'Unknown'
        
        # Get races from match data
        p1_race = match_data.get('player_1_race', 'unknown')
        p2_race = match_data.get('player_2_race', 'unknown')
        
        # Get countries
        p1_country = p1_info.get('country', 'unknown') if p1_info else 'unknown'
        p2_country = p2_info.get('country', 'unknown') if p2_info else 'unknown'
        
        # Get emojis
        p1_flag = get_flag_emote(p1_country)
        p2_flag = get_flag_emote(p2_country)
        p1_race_emote = get_race_emote(p1_race)
        p2_race_emote = get_race_emote(p2_race)
        
        # Get ranks
        p1_rank = ranking_service.get_letter_rank(match_data['player_1_discord_uid'], p1_race)
        p2_rank = ranking_service.get_letter_rank(match_data['player_2_discord_uid'], p2_race)
        p1_rank_emote = get_rank_emote(p1_rank)
        p2_rank_emote = get_rank_emote(p2_rank)
        
        # Get MMRs
        p1_mmr = match_data.get('player_1_mmr', 1500)
        p2_mmr = match_data.get('player_2_mmr', 1500)
        
        # Format match result
        match_result = match_data.get('match_result')
        if match_result == 1:
            result_str = f"🏆 {p1_name} won"
        elif match_result == 2:
            result_str = f"🏆 {p2_name} won"
        elif match_result == 0:
            result_str = "⚖️ Draw"
        elif match_result == -1:
            result_str = "❌ Aborted"
        elif match_result == -2:
            result_str = "⚠️ Conflict"
        else:
            result_str = "⏳ In Progress"
        
        embed = discord.Embed(
            title=f"🔍 Admin Match #{match_id} State",
            description=(
                f"**{p1_rank_emote} {p1_flag} {p1_race_emote} {p1_name}** (MMR: {int(p1_mmr)}) "
                f"vs **{p2_rank_emote} {p2_flag} {p2_race_emote} {p2_name}** (MMR: {int(p2_mmr)})\n\n"
                f"**Result:** {result_str}\n"
                f"**Player 1 UID:** `{match_data['player_1_discord_uid']}`\n"
                f"**Player 2 UID:** `{match_data['player_2_discord_uid']}`"
            ),
            color=discord.Color.blue()
        )
        
        # Empty spacer
        embed.add_field(name="", value="\u3164", inline=False)
        
        # Add reports field
        p1_report = state['reports']['player_1']
        p2_report = state['reports']['player_2']
        
        def format_report_code(code: int, p1_name: str, p2_name: str) -> str:
            """Format a report code into human-readable text.
            
            Report codes:
            1 = Player 1 won
            2 = Player 2 won
            0 = Draw
            -3 = Manual abort
            -4 = No response (automatic abandon)
            """
            if code is None:
                return "Not Reported"
            elif code == 1:
                return f"{p1_name} Won"
            elif code == 2:
                return f"{p2_name} Won"
            elif code == 0:
                return "Draw"
            elif code == -1:
                return "Aborted"
            elif code == -3:
                return "Aborted"
            elif code == -4:
                return "No Response"
            else:
                return f"Unknown ({code})"
        
        embed.add_field(
            name="📊 Original Player Reports",
            value=(
                f"**{p1_name}:** {format_report_code(p1_report, p1_name, p2_name)}\n"
                f"**{p2_name}:** {format_report_code(p2_report, p1_name, p2_name)}"
            ),
            inline=True
        )
        
        # Add admin resolution status
        updated_at = match_data.get('updated_at')
        if updated_at:
            # Convert ISO timestamp to Unix timestamp for Discord formatting
            from datetime import datetime
            try:
                # Handle both string ISO timestamps and numeric timestamps
                if isinstance(updated_at, (int, float)):
                    unix_timestamp = int(updated_at)
                elif isinstance(updated_at, str):
                    # Handle various string formats
                    dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00').replace('+00', '+00:00'))
                    unix_timestamp = int(dt.timestamp())
                else:
                    # Fallback for unexpected types
                    admin_status = f"✅ Yes\n{updated_at}"
                    unix_timestamp = None
                
                if unix_timestamp:
                    admin_status = f"✅ Yes\n<t:{unix_timestamp}:F>"
                else:
                    admin_status = f"✅ Yes\n{updated_at}"
            except (ValueError, AttributeError, TypeError) as e:
                # Fallback if parsing fails
                admin_status = f"✅ Yes\n{updated_at}"
                print(f"[Admin Match] Failed to parse updated_at: {e}, value: {updated_at}, type: {type(updated_at)}")
        else:
            admin_status = "❌ No"
        
        embed.add_field(
            name="🛡️ Admin Resolved",
            value=admin_status,
            inline=True
        )
        
        # Add MMR change field if match is finalized
        mmr_change = match_data.get('mmr_change')
        if mmr_change is not None and mmr_change != 0:
            # Calculate final MMRs
            p1_new_mmr = p1_mmr + mmr_change
            p2_new_mmr = p2_mmr - mmr_change
            
            mmr_sign_p1 = "+" if mmr_change >= 0 else ""
            mmr_sign_p2 = "+" if -mmr_change >= 0 else ""
            
            embed.add_field(
                name="📈 MMR Changes",
                value=(
                    f"**{p1_name}:** `{mmr_sign_p1}{mmr_change}` ({int(p1_mmr)} → {int(p1_new_mmr)})\n"
                    f"**{p2_name}:** `{mmr_sign_p2}{-mmr_change}` ({int(p2_mmr)} → {int(p2_new_mmr)})"
                ),
                inline=False
            )
        
        # Add raw match data for technical reference
        raw_data = {
            "match_id": match_id,
            "player_1_discord_uid": match_data.get('player_1_discord_uid'),
            "player_2_discord_uid": match_data.get('player_2_discord_uid'),
            "player_1_name": p1_name,
            "player_2_name": p2_name,
            "player_1_race": p1_race,
            "player_2_race": p2_race,
            "player_1_country": p1_country,
            "player_2_country": p2_country,
            "player_1_report": p1_report,
            "player_2_report": p2_report,
            "match_result": match_data.get('match_result'),
            "mmr_change": match_data.get('mmr_change'),
            "played_at": match_data.get('played_at'),
            "updated_at": match_data.get('updated_at'),
            "map": match_data.get('map_played'),
            "server": match_data.get('server_used')
        }
        
        raw_data_str = json.dumps(raw_data, indent=2, default=str)
        # Truncate if too long (Discord field limit is 1024 chars)
        if len(raw_data_str) > 1000:
            raw_data_str = raw_data_str[:997] + "..."
        
        embed.add_field(
            name="📋 Raw Match Data",
            value=f"```json\n{raw_data_str}\n```",
            inline=False
        )
        
        # Add monitoring details (user-friendly explanations)
        monitoring = state['monitoring']
        
        # Build monitoring text with explanations
        monitoring_text = ""
        
        if monitoring['is_monitored']:
            monitoring_text += "✅ **Match Completion:** Bot is watching this match for completion\n"
        else:
            monitoring_text += "❌ **Match Completion:** Bot is NOT watching this match\n"
        
        if monitoring['is_processed']:
            monitoring_text += "✅ **Finalized:** Match results have been finalized\n"
        else:
            monitoring_text += "⏳ **Finalized:** Match results are NOT yet finalized\n"
        
        if monitoring['has_waiter']:
            monitoring_text += "⏰ **Pending Notification:** Players are waiting for final notification\n"
        else:
            monitoring_text += "💤 **Pending Notification:** No pending notifications\n"
        
        if monitoring['has_lock']:
            monitoring_text += "🔒 **Processing:** Match is currently being processed"
        else:
            monitoring_text += "🔓 **Processing:** Match is NOT being processed"
        
        embed.add_field(
            name="🔍 Backend Status (Technical)",
            value=monitoring_text,
            inline=False
        )
        
        # Add replay info if available
        replays = state['replays']
        if replays['player_1'] or replays['player_2']:
            replay_text = ""
            if replays['player_1']:
                replay_text += f"**{p1_name}:** ✅ Uploaded\n"
            else:
                replay_text += f"**{p1_name}:** ❌ Not uploaded\n"
            
            if replays['player_2']:
                replay_text += f"**{p2_name}:** ✅ Uploaded"
            else:
                replay_text += f"**{p2_name}:** ❌ Not uploaded"
            
            embed.add_field(
                name="🎬 Replay Status",
                value=replay_text,
                inline=False
            )
        
        # Get replay embeds with full verification (exactly as players see them)
        replay_embed_data = await admin_service.get_replay_embeds_for_match(match_id)
        
        replay_embeds = []
        if replay_embed_data['player_1_embed']:
            replay_embeds.append(replay_embed_data['player_1_embed'])
        if replay_embed_data['player_2_embed']:
            replay_embeds.append(replay_embed_data['player_2_embed'])
        
        # Create embeds list - main embed first, then replay embeds
        all_embeds = [embed] + replay_embeds
        
        # Fetch replay files from backend service
        replay_files = await admin_service.fetch_match_replay_files(match_id)
        
        # Add replay files to attachments if they exist
        if replay_files['player_1_replay']:
            files_to_attach.append(discord.File(
                io.BytesIO(replay_files['player_1_replay']),
                filename=f"match_{match_id}_{replay_files['player_1_name']}.SC2Replay"
            ))
        
        if replay_files['player_2_replay']:
            files_to_attach.append(discord.File(
                io.BytesIO(replay_files['player_2_replay']),
                filename=f"match_{match_id}_{replay_files['player_2_name']}.SC2Replay"
            ))
        
        # Create dismiss view for this informational command
        view = AdminDismissView()
        view.set_admin(interaction.user.id)
        view.set_interaction(interaction)
        
        await queue_followup(
            interaction,
            content=f"Match #{match_id} State",
            embeds=all_embeds if all_embeds else [embed],
            files=files_to_attach,  # Changed from file= to files=
            view=view
        )
    
    # Helper function to create confirmation views
    def _create_admin_confirmation(
        interaction: discord.Interaction,
        title: str,
        description: str,
        confirm_callback,
        color=discord.Color.orange()
    ) -> tuple:
        """Create an admin confirmation view with buttons."""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        
        view = AdminConfirmationView()
        view.set_admin(interaction.user.id)
        
        confirm_btn = ConfirmButton(confirm_callback, label="Admin Confirm", row=0)
        cancel_btn = CancelButton(reset_target=None, label="Admin Cancel", row=0)
        
        view.add_item(confirm_btn)
        view.add_item(cancel_btn)
        
        return embed, view
    
    @admin_group.command(name="resolve", description="[Admin] Manually resolve a match conflict")
    @app_commands.describe(
        match_id="Match ID with conflict",
        winner="Winner (1=player1, 2=player2, 0=draw, -1=invalidate)",
        reason="Reason for resolution"
    )
    @app_commands.choices(winner=[
        app_commands.Choice(name="Player 1 Wins", value=1),
        app_commands.Choice(name="Player 2 Wins", value=2),
        app_commands.Choice(name="Draw", value=0),
        app_commands.Choice(name="Invalidate (No MMR change)", value=-1)
    ])
    @admin_only()
    async def admin_resolve(
        interaction: discord.Interaction,
        match_id: int,
        winner: app_commands.Choice[int],
        reason: str
    ):
        """Resolve match conflict with confirmation."""
        winner_map = {1: 'player_1_win', 2: 'player_2_win', 0: 'draw', -1: 'invalidate'}
        resolution = winner_map[winner.value]
        
        # Fetch match data first to get player names and UIDs for confirmation embed
        from src.backend.services.app_context import data_access_service
        match_data = data_access_service.get_match(match_id)
        if not match_data:
            await queue_interaction_response(
                interaction,
                embed=discord.Embed(
                    title="❌ Match Not Found",
                    description=f"Match #{match_id} does not exist.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return
        
        # Get player info
        p1_info = data_access_service.get_player_info(match_data['player_1_discord_uid'])
        p2_info = data_access_service.get_player_info(match_data['player_2_discord_uid'])
        p1_name = p1_info.get('player_name', 'Unknown') if p1_info else 'Unknown'
        p2_name = p2_info.get('player_name', 'Unknown') if p2_info else 'Unknown'
        p1_uid = match_data['player_1_discord_uid']
        p2_uid = match_data['player_2_discord_uid']
        
        async def confirm_callback(button_interaction: discord.Interaction):
            await queue_interaction_defer(button_interaction)
            
            from src.backend.services.app_context import admin_service
            
            result = await admin_service.resolve_match_conflict(
                match_id=match_id,
                resolution=resolution,
                admin_discord_id=interaction.user.id,
                reason=reason
            )
            
            if result['success']:
                # Backend provides ALL data - frontend just displays it
                                
                md = result.get('match_data', {})
                notif = result.get('notification_data', {})
                
                p1_uid = md.get('player_1_uid')
                p2_uid = md.get('player_2_uid')
                p1_name = md.get('player_1_name')
                p2_name = md.get('player_2_name')
                p1_race = md.get('player_1_race')
                p2_race = md.get('player_2_race')
                p1_country = md.get('player_1_country')
                p2_country = md.get('player_2_country')
                map_name = md.get('map_name')
                
                # Get emojis
                p1_flag = get_flag_emote(p1_country) if p1_country else '🏳️'
                p2_flag = get_flag_emote(p2_country) if p2_country else '🏳️'
                p1_race_emote = get_race_emote(p1_race)
                p2_race_emote = get_race_emote(p2_race)
                
                p1_rank = md.get('player_1_rank')
                p2_rank = md.get('player_2_rank')
                p1_rank_emote = get_rank_emote(p1_rank) if p1_rank else '⚪'
                p2_rank_emote = get_rank_emote(p2_rank) if p2_rank else '⚪'
                
                mmr_change = result.get('mmr_change', 0)
                p1_old_mmr = md.get('player_1_mmr_before', 0)
                p2_old_mmr = md.get('player_2_mmr_before', 0)
                p1_new_mmr = md.get('player_1_mmr_after', 0)
                p2_new_mmr = md.get('player_2_mmr_after', 0)
                
                # Send notifications to both players (styled EXACTLY like Result Finalized embed)
                for player_uid in notif['players']:
                    # Determine result display
                    if notif['resolution'] == 'player_1_win':
                        result_value = f"🏆 **{p1_rank_emote} {p1_flag} {p1_race_emote} {p1_name}**"
                    elif notif['resolution'] == 'player_2_win':
                        result_value = f"🏆 **{p2_rank_emote} {p2_flag} {p2_race_emote} {p2_name}**"
                    elif notif['resolution'] == 'draw':
                        result_value = "⚖️ **Draw**"
                    elif notif['resolution'] == 'invalidate':
                        result_value = "❌ **Match Invalidated**"
                    else:
                        result_value = notif['resolution']
                    
                    player_embed = discord.Embed(
                        title=f"⚖️ Match #{match_id} Admin Resolution",
                        description=f"**{p1_rank_emote} {p1_flag} {p1_race_emote} {p1_name} ({int(p1_old_mmr)} → {int(p1_new_mmr)})** vs **{p2_rank_emote} {p2_flag} {p2_race_emote} {p2_name} ({int(p2_old_mmr)} → {int(p2_new_mmr)})**",
                        color=discord.Color.gold()
                    )
                    
                    # Empty spacer field (matches Result Finalized exactly)
                    player_embed.add_field(name="", value="\u3164", inline=False)
                    
                    # Result field (inline)
                    player_embed.add_field(
                        name="**Result:**",
                        value=result_value,
                        inline=True
                    )
                    
                    # MMR Changes field (inline)
                    p1_sign = "+" if mmr_change >= 0 else ""
                    p2_sign = "+" if -mmr_change >= 0 else ""
                    player_embed.add_field(
                        name="**MMR Changes:**",
                        value=f"- {p1_name}: `{p1_sign}{mmr_change} ({int(p1_old_mmr)} → {int(p1_new_mmr)})`\n- {p2_name}: `{p2_sign}{-mmr_change} ({int(p2_old_mmr)} → {int(p2_new_mmr)})`",
                        inline=True
                    )
                    
                    # Admin intervention field (new, full width)
                    player_embed.add_field(
                        name="⚠️ **Admin Intervention:**",
                        value=f"**Resolved by:** {notif['admin_name']}\n**Reason:** {notif['reason']}",
                        inline=False
                    )
                    
                    await send_player_notification(player_uid, player_embed)
                
                # Admin confirmation (styled EXACTLY like Result Finalized)
                # Determine result display
                if result['resolution'] == 'player_1_win':
                    result_value = f"🏆 **{p1_rank_emote} {p1_flag} {p1_race_emote} {p1_name}**"
                elif result['resolution'] == 'player_2_win':
                    result_value = f"🏆 **{p2_rank_emote} {p2_flag} {p2_race_emote} {p2_name}**"
                elif result['resolution'] == 'draw':
                    result_value = "⚖️ **Draw**"
                elif result['resolution'] == 'invalidate':
                    result_value = "❌ **Match Invalidated**"
                else:
                    result_value = result['resolution']
                
                result_embed = discord.Embed(
                    title=f"✅ Match #{match_id} Admin Resolution",
                    description=f"**{p1_rank_emote} {p1_flag} {p1_race_emote} {p1_name} ({int(p1_old_mmr)} → {int(p1_new_mmr)})** vs **{p2_rank_emote} {p2_flag} {p2_race_emote} {p2_name} ({int(p2_old_mmr)} → {int(p2_new_mmr)})**",
                    color=discord.Color.green()
                )
                
                # Empty spacer field (matches Result Finalized exactly)
                result_embed.add_field(name="", value="\u3164", inline=False)
                
                # Result field (inline)
                result_embed.add_field(
                    name="**Result:**",
                    value=result_value,
                    inline=True
                )
                
                # MMR Changes field (inline)
                p1_sign = "+" if mmr_change >= 0 else ""
                p2_sign = "+" if -mmr_change >= 0 else ""
                result_embed.add_field(
                    name="**MMR Changes:**",
                    value=f"- {p1_name}: `{p1_sign}{mmr_change} ({int(p1_old_mmr)} → {int(p1_new_mmr)})`\n- {p2_name}: `{p2_sign}{-mmr_change} ({int(p2_old_mmr)} → {int(p2_new_mmr)})`",
                    inline=True
                )
                
                # Admin intervention field (new, full width)
                result_embed.add_field(
                    name="⚠️ **Admin Intervention:**",
                    value=f"**Resolved by:** {interaction.user.name}\n**Reason:** {reason}",
                    inline=False
                )
                
                # Forward resolution to admin channel
                await admin_service.forward_match_completion_to_admin_channel(
                    result_embed,
                    match_id
                )
            else:
                result_embed = discord.Embed(
                    title="❌ Admin: Resolution Failed",
                    description=f"Error: {result.get('error')}",
                    color=discord.Color.red()
                )
            
            await queue_edit_original(button_interaction, embed=result_embed, view=None)
        
        # Create detailed confirmation message with player info
        confirmation_description = (
            f"**Match ID:** {match_id}\n"
            f"**Player 1:** {p1_name} (`{p1_uid}`)\n"
            f"**Player 2:** {p2_name} (`{p2_uid}`)\n\n"
            f"**Resolution:** {winner.name}\n"
            f"**Reason:** {reason}\n\n"
            f"This will update the match result and MMR. Confirm?"
        )
        
        embed, view = _create_admin_confirmation(
            interaction,
            "⚠️ Admin: Confirm Match Resolution",
            confirmation_description,
            confirm_callback
        )
        
        await queue_interaction_response(interaction, embed=embed, view=view)
    
    @admin_group.command(name="adjust_mmr", description="[Admin] Adjust player MMR")
    @app_commands.describe(
        user="Player's @mention, username, or Discord ID",
        race="Race (e.g., bw_terran, sc2_zerg)",
        operation="How to adjust the MMR",
        value="MMR value to set/add/subtract",
        reason="Reason for adjustment"
    )
    @app_commands.choices(operation=[
        app_commands.Choice(name="Set to specific value", value="set"),
        app_commands.Choice(name="Add to current MMR", value="add"),
        app_commands.Choice(name="Subtract from current MMR", value="subtract")
    ])
    @admin_only()
    async def admin_adjust_mmr(
        interaction: discord.Interaction,
        user: str,
        race: str,
        operation: app_commands.Choice[str],
        value: int,
        reason: str
    ):
        """Adjust player MMR with confirmation."""
        # Resolve user input (mention, ID, or username)
        user_info = await resolve_user_input(user, interaction)
        
        if user_info is None:
            await queue_interaction_response(
                interaction,
                content=f"❌ Could not find user: {user}",
                ephemeral=True
            )
            return
        
        uid = user_info['discord_uid']
        
        # Get player name from database
        player_info = data_access_service.get_player_info(uid)
        player_name = player_info.get('player_name') if player_info else user_info['username']
        
        operation_type = operation.value
        
        # Get current MMR for confirmation display
        current_mmr = data_access_service.get_player_mmr(uid, race)
        
        # Calculate what the new MMR will be
        if operation_type == 'set':
            new_mmr = value
            change = value - current_mmr if current_mmr else 0
        elif operation_type == 'add':
            new_mmr = current_mmr + value if current_mmr else value
            change = value
        else:  # subtract
            new_mmr = current_mmr - value if current_mmr else -value
            change = -value
        
        async def confirm_callback(button_interaction: discord.Interaction):
            await queue_interaction_defer(button_interaction)
            
            result = await admin_service.adjust_player_mmr(
                discord_uid=uid,
                race=race,
                operation=operation_type,
                value=value,
                admin_discord_id=interaction.user.id,
                reason=reason
            )
            
            if result['success']:
                # Send player notification
                if 'notification_data' in result:
                    notif = result['notification_data']
                    operation_text = {
                        'set': f"set to {notif['value']}",
                        'add': f"increased by {notif['value']}",
                        'subtract': f"decreased by {notif['value']}"
                    }.get(notif['operation'], f"adjusted (operation: {notif['operation']})")
                    
                                        
                    race_name = races_service.get_race_name(race)
                    race_emote = get_race_emote(race)
                    
                    change = result['change']
                    sign = "+" if change >= 0 else ""
                    
                    player_embed = discord.Embed(
                        title="📊 Admin Action: MMR Adjusted",
                        description=f"Your **{race_emote} {race_name}** MMR has been adjusted by an administrator.",
                        color=discord.Color.blue()
                    )
                    
                    player_embed.add_field(
                        name="📊 Old MMR",
                        value=f"`{int(result['old_mmr'])}`",
                        inline=True
                    )
                    player_embed.add_field(
                        name="📈 New MMR",
                        value=f"`{int(result['new_mmr'])}`",
                        inline=True
                    )
                    player_embed.add_field(
                        name="📉 Change",
                        value=f"`{sign}{change}`",
                        inline=True
                    )
                    
                    player_embed.add_field(
                        name="",
                        value="\u3164",
                        inline=False
                    )
                    
                    player_embed.add_field(
                        name="📝 Reason",
                        value=notif['reason'],
                        inline=False
                    )
                    player_embed.add_field(
                        name="👤 Admin",
                        value=notif['admin_name'],
                        inline=False
                    )
                    
                    await send_player_notification(notif['player_uid'], player_embed)
                
                # Get race details for better display
                                
                race_name = races_service.get_race_name(race)
                race_emote = get_race_emote(race)
                
                change = result['change']
                sign = "+" if change >= 0 else ""
                
                result_embed = discord.Embed(
                    title="✅ Admin: MMR Adjustment Complete",
                    description=f"**Player:** <@{uid}> ({player_name})\n**Race:** {race_emote} {race_name}",
                    color=discord.Color.green()
                )
                
                # MMR change inline fields
                result_embed.add_field(
                    name="📊 Old MMR",
                    value=f"`{int(result['old_mmr'])}`",
                    inline=True
                )
                result_embed.add_field(
                    name="📈 New MMR",
                    value=f"`{int(result['new_mmr'])}`",
                    inline=True
                )
                result_embed.add_field(
                    name="📉 Change",
                    value=f"`{sign}{change}`",
                    inline=True
                )
                
                # Admin details
                result_embed.add_field(
                    name="⚙️ Operation",
                    value=operation.name,
                    inline=True
                )
                result_embed.add_field(
                    name="👤 Admin",
                    value=interaction.user.name,
                    inline=True
                )
                result_embed.add_field(
                    name="", 
                    value="",
                    inline=True
                )
                
                # Reason (full width)
                result_embed.add_field(
                    name="📝 Reason",
                    value=reason,
                    inline=False
                )
            else:
                result_embed = discord.Embed(
                    title="❌ Admin: Adjustment Failed",
                    description=f"Error: {result.get('error')}",
                    color=discord.Color.red()
                )
            
            await queue_edit_original(button_interaction, embed=result_embed, view=None)
        
        operation_desc = {
            'set': f"Set to {value}",
            'add': f"Add {value:+}",
            'subtract': f"Subtract {value}"
        }.get(operation_type, f"Operation: {operation_type}")
        
        embed, view = _create_admin_confirmation(
            interaction,
            "⚠️ Admin: Confirm MMR Adjustment",
            f"**Player:** <@{uid}>\n**Race:** {race}\n**Current MMR:** {current_mmr if current_mmr else 'Not set'}\n**Operation:** {operation_desc}\n**New MMR:** {new_mmr}\n**Change:** {change:+}\n**Reason:** {reason}\n\nThis will immediately update the player's MMR. Confirm?",
            confirm_callback
        )
        
        await queue_interaction_response(interaction, embed=embed, view=view)
    
    @admin_group.command(name="remove_queue", description="[Admin] Force remove player from queue")
    @app_commands.describe(
        user="Player's @mention, username, or Discord ID",
        reason="Reason for removal"
    )
    @admin_only()
    async def admin_remove_queue(
        interaction: discord.Interaction,
        user: str,
        reason: str
    ):
        """Force remove a player from the matchmaking queue with confirmation."""
        # Resolve user input (mention, ID, or username)
        user_info = await resolve_user_input(user, interaction)
        
        if user_info is None:
            await queue_interaction_response(
                interaction,
                content=f"❌ Could not find user: {user}",
                ephemeral=True
            )
            return
        
        uid = user_info['discord_uid']
        
        # Get player name from database
        player_info = data_access_service.get_player_info(uid)
        player_name = player_info.get('player_name') if player_info else user_info['username']
        
        async def confirm_callback(button_interaction: discord.Interaction):
            await queue_interaction_defer(button_interaction)
            
            result = await admin_service.force_remove_from_queue(
                discord_uid=uid,
                admin_discord_id=interaction.user.id,
                reason=reason
            )
            
            if result['success']:
                # Send player notification
                if 'notification_data' in result:
                    notif = result['notification_data']
                    player_embed = discord.Embed(
                        title="🚨 Admin Action: Removed from Queue",
                        description="You have been removed from the matchmaking queue by an administrator.",
                        color=discord.Color.orange()
                    )
                    
                    player_embed.add_field(
                        name="",
                        value="\u3164",
                        inline=False
                    )
                    
                    player_embed.add_field(
                        name="📝 Reason",
                        value=notif['reason'],
                        inline=False
                    )
                    player_embed.add_field(
                        name="👤 Admin",
                        value=notif['admin_name'],
                        inline=False
                    )
                    
                    player_embed.add_field(
                        name="",
                        value="\u3164",
                        inline=False
                    )
                    
                    player_embed.add_field(
                        name="ℹ️ Note",
                        value="You can rejoin the queue at any time with `/queue`.",
                        inline=False
                    )
                    
                    await send_player_notification(notif['player_uid'], player_embed)
                
                result_embed = discord.Embed(
                    title="✅ Admin: Queue Removal Complete",
                    description=f"**Player:** <@{uid}> ({player_name})\n**Status:** Removed from matchmaking queue",
                    color=discord.Color.green()
                )
                
                result_embed.add_field(
                    name="👤 Admin",
                    value=interaction.user.name,
                    inline=True
                )
                result_embed.add_field(
                    name="📝 Reason",
                    value=reason,
                    inline=False
                )
            else:
                result_embed = discord.Embed(
                    title="❌ Admin: Removal Failed",
                    description=f"Error: {result.get('error')}",
                    color=discord.Color.red()
                )
            
            await queue_edit_original(button_interaction, embed=result_embed, view=None)
        
        embed, view = _create_admin_confirmation(
            interaction,
            "⚠️ Admin: Confirm Queue Removal",
            f"**Player:** <@{uid}>\n**Reason:** {reason}\n\nThis will immediately remove the player from the queue. Confirm?",
            confirm_callback
        )
        
        await queue_interaction_response(interaction, embed=embed, view=view)
    
    @admin_group.command(name="unblock_queue", description="[Admin] Reset player state to idle (fixes stuck players)")
    @app_commands.describe(
        user="Player's @mention, username, or Discord ID",
        reason="Reason for unblocking"
    )
    @admin_only()
    async def admin_unblock_queue(
        interaction: discord.Interaction,
        user: str,
        reason: str
    ):
        """Reset a player's state to idle with confirmation."""
        # Resolve user input (mention, ID, or username)
        user_info = await resolve_user_input(user, interaction)
        
        if user_info is None:
            await queue_interaction_response(
                interaction,
                content=f"❌ Could not find user: {user}",
                ephemeral=True
            )
            return
        
        uid = user_info['discord_uid']
        
        # Get player name from database
        player_info = data_access_service.get_player_info(uid)
        player_name = player_info.get('player_name') if player_info else user_info['username']
        
        async def confirm_callback(button_interaction: discord.Interaction):
            await queue_interaction_defer(button_interaction)
            
            result = await admin_service.unblock_player_state(
                discord_uid=uid,
                admin_discord_id=interaction.user.id,
                reason=reason
            )
            
            if result['success']:
                result_embed = discord.Embed(
                    title="✅ Admin: Player Unblocked",
                    description=f"**Player:** <@{uid}> ({player_name})\n**Status:** State reset to idle\n**Previous State:** {result.get('old_state', 'unknown')}",
                    color=discord.Color.green()
                )
                
                result_embed.add_field(
                    name="👤 Admin",
                    value=interaction.user.name,
                    inline=True
                )
                result_embed.add_field(
                    name="📝 Reason",
                    value=reason,
                    inline=False
                )
            else:
                result_embed = discord.Embed(
                    title="❌ Admin: Unblock Failed",
                    description=f"Error: {result.get('error')}",
                    color=discord.Color.red()
                )
            
            await queue_edit_original(button_interaction, embed=result_embed, view=None)
        
        embed, view = _create_admin_confirmation(
            interaction,
            "⚠️ Admin: Confirm Player Unblock",
            f"**Player:** <@{uid}>\n**Reason:** {reason}\n\nThis will reset the player's state to 'idle', allowing them to queue again. Confirm?",
            confirm_callback
        )
        
        await queue_interaction_response(interaction, embed=embed, view=view)
    
    @admin_group.command(name="ban", description="[Admin] Toggle ban status for a player")
    @app_commands.describe(
        user="Player's @mention, username, or Discord ID",
        reason="Reason for the ban/unban"
    )
    @admin_only()
    async def admin_ban(
        interaction: discord.Interaction,
        user: str,
        reason: str
    ):
        """Toggle ban status for a player."""
        # Resolve user input (mention, ID, or username)
        user_info = await resolve_user_input(user, interaction)
        
        if user_info is None:
            await queue_interaction_response(
                interaction,
                content=f"❌ Could not find user: {user}",
                ephemeral=True
            )
            return
        
        uid = user_info['discord_uid']
        
        # Get player name from database
        player_info = data_access_service.get_player_info(uid)
        player_name = player_info.get('player_name') if player_info else user_info['username']
        
        # Check current status
        current_banned = data_access_service.get_is_banned(uid)
        action = "unban" if current_banned else "ban"
        
        async def confirm_callback(button_interaction: discord.Interaction):
            await queue_interaction_defer(button_interaction)
            
            result = await admin_service.toggle_ban_status(
                discord_uid=uid,
                admin_discord_id=interaction.user.id,
                reason=reason
            )
            
            if result['success']:
                action_past = "banned" if result["new_status"] else "unbanned"
                
                # Send notification to the player
                if 'notification' in result:
                    notif = result['notification']
                    action_desc = "banned" if result["new_status"] else "unbanned"
                    
                    player_embed = discord.Embed(
                        title=f"{'🚫' if result['new_status'] else '✅'} Account {action_desc.title()}",
                        description=f"Your account has been {action_desc} by an administrator.",
                        color=discord.Color.red() if result["new_status"] else discord.Color.green()
                    )
                    
                    player_embed.add_field(
                        name="📝 Reason",
                        value=notif['reason'],
                        inline=False
                    )
                    
                    player_embed.add_field(
                        name="👤 Admin",
                        value=notif['admin_name'],
                        inline=False
                    )
                    
                    if not result["new_status"]:  # If unbanned
                        player_embed.add_field(
                            name="ℹ️ Note",
                            value="You can now use all bot commands again.",
                            inline=False
                        )
                    
                    await send_player_notification(notif['player_uid'], player_embed)
                
                result_embed = discord.Embed(
                    title=f"✅ Admin: Player {action_past.title()}",
                    description=f"**Player:** <@{uid}> ({player_name})\n**Status:** {action_past.title()}\n**Previous Status:** {'Banned' if result['old_status'] else 'Not Banned'}",
                    color=discord.Color.green()
                )
                
                result_embed.add_field(
                    name="👤 Admin",
                    value=interaction.user.name,
                    inline=True
                )
                result_embed.add_field(
                    name="📝 Reason",
                    value=reason,
                    inline=False
                )
            else:
                result_embed = discord.Embed(
                    title="❌ Admin: Ban Toggle Failed",
                    description=f"Error: {result.get('error', 'Unknown error')}",
                    color=discord.Color.red()
                )
            
            await queue_edit_original(button_interaction, embed=result_embed, view=None)
        
        embed, view = _create_admin_confirmation(
            interaction,
            f"⚠️ Admin: Confirm {action.title()}",
            f"**Player:** <@{uid}> ({player_name})\n**Current Status:** {'Banned' if current_banned else 'Not Banned'}\n**Action:** {action.title()}\n**Reason:** {reason}\n\nThis will immediately {'unban' if current_banned else 'ban'} this player. Confirm?",
            confirm_callback
        )
        
        await queue_interaction_response(interaction, embed=embed, view=view)
    
    @admin_group.command(name="reset_aborts", description="[Admin] Reset player's abort count")
    @app_commands.describe(
        user="Player's @mention, username, or Discord ID",
        new_count="New abort count",
        reason="Reason for reset"
    )
    @admin_only()
    async def admin_reset_aborts(
        interaction: discord.Interaction,
        user: str,
        new_count: int,
        reason: str
    ):
        """Reset a player's abort count with confirmation."""
        # Resolve user input (mention, ID, or username)
        user_info = await resolve_user_input(user, interaction)
        
        if user_info is None:
            await queue_interaction_response(
                interaction,
                content=f"❌ Could not find user: {user}",
                ephemeral=True
            )
            return
        
        uid = user_info['discord_uid']
        
        # Get player name from database
        player_info = data_access_service.get_player_info(uid)
        player_name = player_info.get('player_name') if player_info else user_info['username']
        
        # Get current abort count for confirmation display
        current_aborts = data_access_service.get_remaining_aborts(uid)
        
        async def confirm_callback(button_interaction: discord.Interaction):
            await queue_interaction_defer(button_interaction)
            
            result = await admin_service.reset_player_aborts(
                discord_uid=uid,
                new_count=new_count,
                admin_discord_id=interaction.user.id,
                reason=reason
            )
            
            if result['success']:
                # Send player notification
                if 'notification_data' in result:
                    notif = result['notification_data']
                    player_embed = discord.Embed(
                        title="🔄 Admin Action: Abort Count Reset",
                        description="Your abort count has been reset by an administrator.",
                        color=discord.Color.blue()
                    )
                    
                    player_embed.add_field(
                        name="🔴 Old Count",
                        value=f"`{result['old_count']}`",
                        inline=True
                    )
                    player_embed.add_field(
                        name="🟢 New Count",
                        value=f"`{result['new_count']}`",
                        inline=True
                    )
                    player_embed.add_field(
                        name="📊 Change",
                        value=f"`{result['new_count'] - result['old_count']:+}`",
                        inline=True
                    )
                    
                    player_embed.add_field(
                        name="",
                        value="\u3164",
                        inline=False
                    )
                    
                    player_embed.add_field(
                        name="📝 Reason",
                        value=notif['reason'],
                        inline=False
                    )
                    player_embed.add_field(
                        name="👤 Admin",
                        value=notif['admin_name'],
                        inline=False
                    )
                    
                    await send_player_notification(notif['player_uid'], player_embed)
                
                result_embed = discord.Embed(
                    title="✅ Admin: Abort Count Reset Complete",
                    description=f"**Player:** <@{uid}> ({player_name})\n**Status:** Abort count has been reset",
                    color=discord.Color.green()
                )
                
                # Abort count change inline
                result_embed.add_field(
                    name="🔴 Old Count",
                    value=f"`{result['old_count']}`",
                    inline=True
                )
                result_embed.add_field(
                    name="🟢 New Count",
                    value=f"`{result['new_count']}`",
                    inline=True
                )
                result_embed.add_field(
                    name="📊 Change",
                    value=f"`{result['new_count'] - result['old_count']:+}`",
                    inline=True
                )
                
                # Admin details
                result_embed.add_field(
                    name="👤 Admin",
                    value=interaction.user.name,
                    inline=True
                )
                result_embed.add_field(
                    name="📝 Reason",
                    value=reason,
                    inline=False
                )
            else:
                result_embed = discord.Embed(
                    title="❌ Admin: Reset Failed",
                    description=f"Error: {result.get('error')}",
                    color=discord.Color.red()
                )
            
            await queue_edit_original(button_interaction, embed=result_embed, view=None)
        
        embed, view = _create_admin_confirmation(
            interaction,
            "⚠️ Admin: Confirm Abort Reset",
            f"**Player:** <@{uid}>\n**Current Aborts:** {current_aborts}\n**New Count:** {new_count}\n**Reason:** {reason}\n\nThis will update the player's abort counter. Confirm?",
            confirm_callback
        )
        
        await queue_interaction_response(interaction, embed=embed, view=view)
    
    @admin_group.command(name="clear_queue", description="[Admin] EMERGENCY: Clear entire queue")
    @app_commands.describe(reason="Reason for clearing queue")
    @admin_only()
    async def admin_clear_queue(interaction: discord.Interaction, reason: str):
        """Emergency command to clear the entire matchmaking queue with confirmation."""
        
        async def confirm_callback(button_interaction: discord.Interaction):
            await queue_interaction_defer(button_interaction)
            
            result = await admin_service.emergency_clear_queue(
                admin_discord_id=interaction.user.id,
                reason=reason
            )
            
            if result['success']:
                # Send notifications to all removed players
                if 'notification_data' in result:
                    notif = result['notification_data']
                    player_embed = discord.Embed(
                        title="🚨 Admin Action: Queue Cleared",
                        description="The matchmaking queue has been cleared by an administrator.",
                        color=discord.Color.red()
                    )
                    
                    player_embed.add_field(
                        name="",
                        value="\u3164",
                        inline=False
                    )
                    
                    player_embed.add_field(
                        name="📝 Reason",
                        value=notif['reason'],
                        inline=False
                    )
                    player_embed.add_field(
                        name="👤 Admin",
                        value=notif['admin_name'],
                        inline=False
                    )
                    
                    player_embed.add_field(
                        name="",
                        value="\u3164",
                        inline=False
                    )
                    
                    player_embed.add_field(
                        name="ℹ️ Note",
                        value="You can rejoin the queue at any time with `/queue`.",
                        inline=False
                    )
                    
                    for player_id in notif['player_uids']:
                        await send_player_notification(player_id, player_embed)
                
                player_count = result['players_removed']
                
                result_embed = discord.Embed(
                    title="🚨 Admin: EMERGENCY Queue Clear Complete",
                    description=f"**Status:** Matchmaking queue has been completely cleared\n**Impact:** {player_count} player(s) removed",
                    color=discord.Color.red()
                )
                
                result_embed.add_field(
                    name="👥 Players Removed",
                    value=f"`{player_count}`",
                    inline=True
                )
                result_embed.add_field(
                    name="👤 Admin",
                    value=interaction.user.name,
                    inline=True
                )
                result_embed.add_field(
                    name="", 
                    value="",
                    inline=True
                )
                
                result_embed.add_field(
                    name="📝 Reason",
                    value=reason,
                    inline=False
                )
                
                result_embed.add_field(
                    name="ℹ️ Note",
                    value="All affected players have been notified and can rejoin at any time.",
                    inline=False
                )
            else:
                result_embed = discord.Embed(
                    title="❌ Admin: Clear Failed",
                    description=f"Error: {result.get('error')}",
                    color=discord.Color.red()
                )
            
            await queue_edit_original(button_interaction, embed=result_embed, view=None)
        
        embed, view = _create_admin_confirmation(
            interaction,
            "🚨 Admin: EMERGENCY Confirm Queue Clear",
            f"**Reason:** {reason}\n\n⚠️ **WARNING:** This will remove ALL players from the queue!\n\nThis action cannot be undone. Confirm?",
            confirm_callback,
            color=discord.Color.red()
        )
        
        await queue_interaction_response(interaction, embed=embed, view=view)
    
    tree.add_command(admin_group)
    
    # ========== OWNER COMMANDS ==========
    
    owner_group = app_commands.Group(
        name="owner",
        description="Owner-only commands (Highest Privilege)"
    )
    
    @owner_group.command(name="admin", description="[Owner] Toggle admin status for a user")
    @app_commands.describe(
        user="User's @mention, username, or Discord ID to toggle admin status"
    )
    @owner_only()
    async def owner_admin(interaction: discord.Interaction, user: str):
        """Toggle admin status for a user (owner-only)."""
        # Resolve user input (mention, ID, or username)
        user_info = await resolve_user_input(user, interaction)
        
        if user_info is None:
            await queue_interaction_response(
                interaction,
                content=f"❌ Could not find user: {user}",
                ephemeral=True
            )
            return
        
        user_id = user_info['discord_uid']
        username = user_info['username']
        
        # Check if user is owner
        if user_id in OWNER_IDS:
            await queue_interaction_response(
                interaction,
                content=f"❌ Cannot modify owner status for {username}.",
                ephemeral=True
            )
            return
        
        # Check current admin status
        is_currently_admin = user_id in ADMIN_IDS
        action = "remove" if is_currently_admin else "add"
        
        async def confirm_callback(button_interaction: discord.Interaction):
            # Toggle admin status
            result = await admin_service.toggle_admin_status(
                discord_uid=user_id,
                username=username,
                owner_discord_id=interaction.user.id
            )
            
            if result['success']:
                action_past = result['action']  # 'added' or 'removed'
                
                # Reload admin IDs in memory
                global ADMIN_IDS
                ADMIN_IDS = _load_admin_ids()
                
                # Send notification to the affected user
                player_embed = discord.Embed(
                    title=f"{'👑' if action_past == 'added' else '📋'} Admin Status {action_past.title()}",
                    description=f"Your admin status has been {action_past} by a bot owner.",
                    color=discord.Color.gold() if action_past == 'added' else discord.Color.blue()
                )
                
                player_embed.add_field(
                    name="👤 Owner",
                    value=interaction.user.name,
                    inline=True
                )
                
                player_embed.add_field(
                    name="⚙️ Status",
                    value="Admin" if action_past == 'added' else "Regular User",
                    inline=True
                )
                
                if action_past == 'added':
                    player_embed.add_field(
                        name="ℹ️ Note",
                        value="You now have admin access to all bot commands.",
                        inline=False
                    )
                else:
                    player_embed.add_field(
                        name="ℹ️ Note",
                        value="You no longer have admin access to bot commands.",
                        inline=False
                    )
                
                await send_player_notification(user_id, player_embed)
                
                # Send confirmation to owner
                result_embed = discord.Embed(
                    title=f"✅ Admin Status {'Added' if action_past == 'added' else 'Removed'}",
                    description=f"**User:** {username} (<@{user_id}>)\n**Status:** Admin permissions {action_past}",
                    color=discord.Color.green() if action_past == 'added' else discord.Color.orange()
                )
                
                result_embed.add_field(
                    name="👤 Owner",
                    value=interaction.user.name,
                    inline=True
                )
                
                result_embed.add_field(
                    name="⚙️ Action",
                    value=action_past.title(),
                    inline=True
                )
                
                result_embed.add_field(
                    name="ℹ️ Note",
                    value=f"{'The user now has admin access to all bot commands.' if action_past == 'added' else 'The user no longer has admin access.'}",
                    inline=False
                )
            else:
                result_embed = discord.Embed(
                    title="❌ Owner: Admin Toggle Failed",
                    description=f"Error: {result.get('error')}",
                    color=discord.Color.red()
                )
            
            # Use queue_interaction_edit to acknowledge button click and edit in one atomic operation
            await queue_interaction_edit(button_interaction, embed=result_embed, view=None)
        
        embed, view = _create_admin_confirmation(
            interaction,
            f"👑 Owner: Confirm Admin Status Change",
            f"**User:** {username} (<@{user_id}>)\n**Action:** {action.title()} admin permissions\n\nAre you sure?",
            confirm_callback,
            color=discord.Color.gold()
        )
        
        await queue_interaction_response(interaction, embed=embed, view=view)
    
    tree.add_command(owner_group)

