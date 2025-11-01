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

from src.backend.services.app_context import admin_service, data_access_service, ranking_service, races_service
from src.backend.services.process_pool_health import get_bot_instance
from src.bot.components.confirm_restart_cancel_buttons import ConfirmButton, CancelButton
from src.bot.config import GLOBAL_TIMEOUT


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
            await user.send(embed=embed)
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

def format_system_snapshot(snapshot: dict) -> dict:
    """
    Format system snapshot into structured embed fields.
    
    Returns dict with 'timestamp' and 'fields' list.
    """
    fields = []
    
    # Memory field
    if 'error' in snapshot['memory']:
        memory_text = snapshot['memory']['error']
    else:
        memory_text = f"RSS: {snapshot['memory']['rss_mb']:.1f} MB\nUsage: {snapshot['memory']['percent']:.1f}%"
    fields.append({'name': '💾 Memory', 'value': memory_text, 'inline': True})
    
    # DataFrames field
    df_lines = []
    for df_name, df_stats in snapshot['data_frames'].items():
        df_lines.append(f"**{df_name}**: {df_stats['rows']:,} rows ({df_stats['size_mb']:.2f} MB)")
    fields.append({'name': '📊 DataFrames', 'value': '\n'.join(df_lines), 'inline': False})
    
    # Queue field (with details)
    queue_size = snapshot['queue']['size']
    queue_text = f"**Players in Queue:** {queue_size}"
    if queue_size > 0 and 'players' in snapshot['queue']:
        # Add first few players
        players = snapshot['queue'].get('players', [])[:5]
        if players:
            queue_text += "\n" + "\n".join([f"  • {p}" for p in players])
            if len(snapshot['queue'].get('players', [])) > 5:
                queue_text += f"\n  ... and {len(snapshot['queue']['players']) - 5} more"
    fields.append({'name': '🎮 Queue Status', 'value': queue_text, 'inline': False})
    
    # Matches field (with details)
    match_count = snapshot['matches']['active']
    match_text = f"**Active Matches:** {match_count}"
    if match_count > 0 and 'match_list' in snapshot['matches']:
        # Add first few matches
        matches = snapshot['matches'].get('match_list', [])[:5]
        if matches:
            match_text += "\n" + "\n".join([f"  • {m}" for m in matches])
            if len(snapshot['matches'].get('match_list', [])) > 5:
                match_text += f"\n  ... and {len(snapshot['matches']['match_list']) - 5} more"
    fields.append({'name': '⚔️ Active Matches', 'value': match_text, 'inline': False})
    
    # Write Queue field
    wq = snapshot['write_queue']
    success_rate = (wq['total_completed'] / wq['total_queued'] * 100) if wq['total_queued'] > 0 else 100.0
    wq_text = f"Depth: {wq['depth']}\nCompleted: {wq['total_completed']}\nSuccess: {success_rate:.1f}%"
    fields.append({'name': '📝 Write Queue', 'value': wq_text, 'inline': True})
    
    # Process Pool field
    pp_text = f"Workers: {snapshot['process_pool'].get('workers', 0)}\nRestarts: {snapshot['process_pool'].get('restart_count', 0)}"
    fields.append({'name': '⚙️ Process Pool', 'value': pp_text, 'inline': True})
    
    return {
        'timestamp': snapshot['timestamp'],
        'fields': fields
    }


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
    from src.bot.utils.discord_utils import (
        get_flag_emote, get_globe_emote, get_race_emote, 
        get_rank_emote, get_game_emote
    )
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
    
    # Admin-specific: Remaining aborts
    basic_info_parts.append(f"- **Remaining Aborts:** {info.get('remaining_aborts', 0)}/3")
    
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
                    
                    last_played_dt = mmr_entry.get('last_played')
                    if last_played_dt:
                        if last_played_dt.tzinfo is None:
                            last_played_dt = last_played_dt.replace(tzinfo=timezone.utc)
                        discord_ts = f"<t:{int(last_played_dt.timestamp())}:f>"
                        sc2_text += f"  - **Last Played:** {discord_ts}\n"
            
            sc2_emote = get_game_emote('starcraft_2')
            embed.add_field(name=f"{sc2_emote} StarCraft II MMR", value=sc2_text.strip(), inline=False)
    
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


# Global set of admin IDs (loaded once at module import)
ADMIN_IDS = _load_admin_ids()


def is_admin(interaction: discord.Interaction) -> bool:
    """Check if user is an admin (loaded from admins.json)."""
    return interaction.user.id in ADMIN_IDS


def admin_only():
    """
    Decorator to restrict commands to admins.
    
    Note: Admin commands are exempt from DMs-only rule and can be used anywhere.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        if not is_admin(interaction):
            await interaction.response.send_message(
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
                await interaction.response.defer(ephemeral=True)
            except discord.errors.NotFound:
                # Interaction already acknowledged (shouldn't happen, but handle gracefully)
                pass
            
            # Send ephemeral followup instead of response to avoid consuming interaction
            try:
                await interaction.followup.send(
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
        print(f"[AdminConfirmationView] View timed out for admin {self._original_admin_id}")


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
        await interaction.response.defer()
        
        snapshot = admin_service.get_system_snapshot()
        formatted = format_system_snapshot(snapshot)
        
        embed = discord.Embed(
            title="🔍 Admin System Snapshot",
            description=f"**Timestamp:** {formatted['timestamp']}",
            color=discord.Color.blue()
        )
        
        # Add all fields
        for field in formatted['fields']:
            embed.add_field(
                name=field['name'],
                value=field['value'],
                inline=field.get('inline', False)
            )
        
        await interaction.followup.send(embed=embed)
    
    @admin_group.command(name="player", description="[Admin] View player state")
    @app_commands.describe(user="Player's @username, username, or Discord ID")
    @admin_only()
    async def admin_player(interaction: discord.Interaction, user: str):
        """Display complete player state."""
        await interaction.response.defer()
        
        # Resolve user input to Discord ID
        user_info = await admin_service.resolve_user(user)
        
        if user_info is None:
            await interaction.followup.send(
                f"❌ Could not find user: {user}",
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
        
        await interaction.followup.send(embed=embed)
    
    @admin_group.command(name="match", description="[Admin] View match state")
    @app_commands.describe(match_id="Match ID")
    @admin_only()
    async def admin_match(interaction: discord.Interaction, match_id: int):
        """Display complete match state."""
        await interaction.response.defer()
        
        state = admin_service.get_match_full_state(match_id)
        
        if 'error' in state:
            await interaction.followup.send(
                content=f"Error: {state['error']}",
            )
            return
        
        import json
        formatted = json.dumps(state, indent=2, default=str)
        
        file = discord.File(
            io.BytesIO(formatted.encode()),
            filename=f"admin_match_{match_id}.json"
        )
        
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
        from src.bot.utils.discord_utils import get_flag_emote, get_race_emote, get_rank_emote
        from src.backend.services.app_context import ranking_service
        
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
        
        def format_report_code(code):
            if code is None:
                return "⏳ Not Reported"
            elif code == 1:
                return "✅ I Won"
            elif code == 2:
                return "❌ I Lost"
            elif code == 0:
                return "⚖️ Draw"
            elif code == -1:
                return "🚫 Aborted"
            elif code == -3:
                return "🚫 I Aborted"
            elif code == -4:
                return "⏰ No Response"
            else:
                return f"❓ Unknown ({code})"
        
        embed.add_field(
            name="📊 Player Reports",
            value=(
                f"**{p1_name}:** {format_report_code(p1_report)}\n"
                f"**{p2_name}:** {format_report_code(p2_report)}"
            ),
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
                inline=True
            )
        
        # Add field interpretation guide (multiline for readability)
        embed.add_field(
            name="📖 Field Guide",
            value=(
                "**player_X_report:**\n"
                "  1=Won, 2=Lost, 0=Draw, -1=Aborted,\n"
                "  -3=I Aborted, -4=No Response, null=Not Reported\n\n"
                "**match_result:**\n"
                "  1=P1 Won, 2=P2 Won, 0=Draw, -1=Aborted,\n"
                "  -2=Conflict, null=In Progress\n\n"
                "**match_result_confirmation_status:**\n"
                "  0=None, 1=P1 Only, 2=P2 Only, 3=Both"
            ),
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
        
        await interaction.followup.send(
            embed=embed,
            file=file,
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
        
        async def confirm_callback(button_interaction: discord.Interaction):
            await button_interaction.response.defer()
            
            result = await admin_service.resolve_match_conflict(
                match_id=match_id,
                resolution=resolution,
                admin_discord_id=interaction.user.id,
                reason=reason
            )
            
            if result['success']:
                # Backend provides ALL data - frontend just displays it
                from src.bot.utils.discord_utils import get_flag_emote, get_rank_emote, get_race_emote
                
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
            else:
                result_embed = discord.Embed(
                    title="❌ Admin: Resolution Failed",
                    description=f"Error: {result.get('error')}",
                    color=discord.Color.red()
                )
            
            await button_interaction.edit_original_response(embed=result_embed, view=None)
        
        embed, view = _create_admin_confirmation(
            interaction,
            "⚠️ Admin: Confirm Match Resolution",
            f"**Match ID:** {match_id}\n**Resolution:** {winner.name}\n**Reason:** {reason}\n\nThis will update the match result and MMR. Confirm?",
            confirm_callback
        )
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @admin_group.command(name="adjust_mmr", description="[Admin] Adjust player MMR")
    @app_commands.describe(
        user="Player's @username, username, or Discord ID",
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
        # Resolve user input to Discord ID
        user_info = await admin_service.resolve_user(user)
        
        if user_info is None:
            await interaction.response.send_message(
                f"❌ Could not find user: {user}",
                ephemeral=True
            )
            return
        
        uid = user_info['discord_uid']
        player_name = user_info['player_name']
        
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
            await button_interaction.response.defer()
            
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
                    
                    from src.bot.utils.discord_utils import get_race_emote
                    
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
                from src.bot.utils.discord_utils import get_race_emote
                
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
            
            await button_interaction.edit_original_response(embed=result_embed, view=None)
        
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
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @admin_group.command(name="remove_queue", description="[Admin] Force remove player from queue")
    @app_commands.describe(
        user="Player's @username, username, or Discord ID",
        reason="Reason for removal"
    )
    @admin_only()
    async def admin_remove_queue(
        interaction: discord.Interaction,
        user: str,
        reason: str
    ):
        """Force remove a player from the matchmaking queue with confirmation."""
        # Resolve user input to Discord ID
        user_info = await admin_service.resolve_user(user)
        
        if user_info is None:
            await interaction.response.send_message(
                f"❌ Could not find user: {user}",
                ephemeral=True
            )
            return
        
        uid = user_info['discord_uid']
        player_name = user_info['player_name']
        
        async def confirm_callback(button_interaction: discord.Interaction):
            await button_interaction.response.defer()
            
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
            
            await button_interaction.edit_original_response(embed=result_embed, view=None)
        
        embed, view = _create_admin_confirmation(
            interaction,
            "⚠️ Admin: Confirm Queue Removal",
            f"**Player:** <@{uid}>\n**Reason:** {reason}\n\nThis will immediately remove the player from the queue. Confirm?",
            confirm_callback
        )
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @admin_group.command(name="reset_aborts", description="[Admin] Reset player's abort count")
    @app_commands.describe(
        user="Player's @username, username, or Discord ID",
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
        # Resolve user input to Discord ID
        user_info = await admin_service.resolve_user(user)
        
        if user_info is None:
            await interaction.response.send_message(
                f"❌ Could not find user: {user}",
                ephemeral=True
            )
            return
        
        uid = user_info['discord_uid']
        player_name = user_info['player_name']
        
        # Get current abort count for confirmation display
        current_aborts = data_access_service.get_remaining_aborts(uid)
        
        async def confirm_callback(button_interaction: discord.Interaction):
            await button_interaction.response.defer()
            
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
            
            await button_interaction.edit_original_response(embed=result_embed, view=None)
        
        embed, view = _create_admin_confirmation(
            interaction,
            "⚠️ Admin: Confirm Abort Reset",
            f"**Player:** <@{uid}>\n**Current Aborts:** {current_aborts}\n**New Count:** {new_count}\n**Reason:** {reason}\n\nThis will update the player's abort counter. Confirm?",
            confirm_callback
        )
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @admin_group.command(name="clear_queue", description="[Admin] EMERGENCY: Clear entire queue")
    @app_commands.describe(reason="Reason for clearing queue")
    @admin_only()
    async def admin_clear_queue(interaction: discord.Interaction, reason: str):
        """Emergency command to clear the entire matchmaking queue with confirmation."""
        
        async def confirm_callback(button_interaction: discord.Interaction):
            await button_interaction.response.defer()
            
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
            
            await button_interaction.edit_original_response(embed=result_embed, view=None)
        
        embed, view = _create_admin_confirmation(
            interaction,
            "🚨 Admin: EMERGENCY Confirm Queue Clear",
            f"**Reason:** {reason}\n\n⚠️ **WARNING:** This will remove ALL players from the queue!\n\nThis action cannot be undone. Confirm?",
            confirm_callback,
            color=discord.Color.red()
        )
        
        await interaction.response.send_message(embed=embed, view=view)
    
    tree.add_command(admin_group)

