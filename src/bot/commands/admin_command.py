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

from src.backend.services.app_context import admin_service
from src.backend.services.process_pool_health import _bot_instance
from src.bot.components.confirm_restart_cancel_buttons import ConfirmButton, CancelButton


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
    if not _bot_instance:
        print(f"[AdminCommand] Cannot send notification: bot instance not available")
        return False
    
    try:
        user = await _bot_instance.fetch_user(discord_uid)
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

def format_system_snapshot(snapshot: dict) -> str:
    """Format system snapshot as human-readable text."""
    lines = [
        "=== SYSTEM SNAPSHOT ===",
        f"Timestamp: {snapshot['timestamp']}",
        "",
        "Memory:",
    ]
    
    if 'error' in snapshot['memory']:
        lines.append(f"  {snapshot['memory']['error']}")
    else:
        lines.extend([
            f"  RSS: {snapshot['memory']['rss_mb']:.1f} MB",
            f"  Usage: {snapshot['memory']['percent']:.1f}%",
        ])
    
    lines.append("")
    lines.append("DataFrames:")
    
    for df_name, df_stats in snapshot['data_frames'].items():
        lines.append(f"  {df_name}:")
        lines.append(f"    Rows: {df_stats['rows']:,}")
        lines.append(f"    Size: {df_stats['size_mb']:.2f} MB")
    
    wq = snapshot['write_queue']
    success_rate = (wq['total_completed'] / wq['total_queued'] * 100) if wq['total_queued'] > 0 else 100.0
    
    lines.extend([
        "",
        "Queue:",
        f"  Players: {snapshot['queue']['size']}",
        "",
        "Matches:",
        f"  Active: {snapshot['matches']['active']}",
        "",
        "Write Queue:",
        f"  Depth: {wq['depth']}",
        f"  Completed: {wq['total_completed']}",
        f"  Success Rate: {success_rate:.1f}%",
        "",
        "Process Pool:",
        f"  Workers: {snapshot['process_pool'].get('workers', 0)}",
        f"  Restarts: {snapshot['process_pool'].get('restart_count', 0)}"
    ])
    
    return "\n".join(lines)


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


def format_player_state(state: dict) -> str:
    """Format player state for human reading."""
    
    def format_report(report):
        if report is None:
            return "Not reported"
        report_map = {0: "Draw", 1: "I won", 2: "I lost", -1: "Aborted", -3: "I aborted"}
        return report_map.get(report, f"Unknown ({report})")
    
    info = state['player_info']
    if not info:
        return "Player not found"
    
    lines = [
        f"=== PLAYER STATE: {info.get('player_name', 'Unknown')} ===",
        f"Discord ID: {info['discord_uid']}",
        f"Country: {info.get('country', 'None')}",
        f"Region: {info.get('region', 'None')}",
        f"Remaining Aborts: {info.get('remaining_aborts', 0)}",
        "",
        "**MMRs:**"
    ]
    
    for race, mmr_data in state['mmrs'].items():
        lines.append(f"  {race}: {mmr_data['mmr']} ({mmr_data['games_played']} games)")
    
    lines.append("")
    lines.append(f"**Queue Status:** {'✅ IN QUEUE' if state['queue_status']['in_queue'] else '❌ Not in queue'}")
    
    if state['queue_status']['details']:
        details = state['queue_status']['details']
        lines.append(f"  Wait time: {details['wait_time']:.0f}s")
        lines.append(f"  Races: {', '.join(details['races'])}")
    
    lines.append("")
    lines.append(f"**Active Matches:** {len(state['active_matches'])}")
    
    for match in state['active_matches']:
        lines.append(f"  Match #{match['match_id']} ({match['status']})")
        lines.append(f"    My report: {format_report(match['my_report'])}")
        lines.append(f"    Their report: {format_report(match['their_report'])}")
    
    return "\n".join(lines)


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
    """
    
    def __init__(self, timeout: int = 60):
        super().__init__(timeout=timeout)
        self._original_admin_id: Optional[int] = None
    
    def set_admin(self, admin_id: int):
        """Set the admin who initiated this view (the only one who can interact with buttons)."""
        self._original_admin_id = admin_id
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original admin who initiated the command can interact with buttons."""
        if interaction.user.id != self._original_admin_id:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🚫 Admin Button Restricted",
                    description=f"Only <@{self._original_admin_id}> can interact with these buttons.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return False
        return True


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
        
        if len(formatted) > 1900:
            file = discord.File(
                io.BytesIO(formatted.encode()),
                filename=f"admin_snapshot_{int(time.time())}.txt"
            )
            await interaction.followup.send(
                content="**Admin System Snapshot**",
                file=file,
            )
        else:
            embed = discord.Embed(
                title="Admin System Snapshot",
                description=f"```\n{formatted}\n```",
                color=discord.Color.blue()
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
        formatted = format_player_state(state)
        
        embed = discord.Embed(
            title="Admin Player State",
            description=formatted,
            color=discord.Color.blue()
        )
        
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
        embed = discord.Embed(
            title=f"Admin Match #{match_id} State",
            description=(
                f"**Status:** {match_data.get('status')}\n"
                f"**Result:** {match_data.get('match_result')}\n"
                f"**Players:** <@{match_data['player_1_discord_uid']}> vs <@{match_data['player_2_discord_uid']}>"
            ),
            color=discord.Color.blue()
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
        
        view = AdminConfirmationView(timeout=60)
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
                # Send notifications to both players
                if 'notification_data' in result:
                    notif = result['notification_data']
                    
                    resolution_text = {
                        'player_1_win': "Player 1 Victory",
                        'player_2_win': "Player 2 Victory",
                        'draw': "Draw",
                        'invalidate': "Match Invalidated (No MMR change)"
                    }.get(notif['resolution'], notif['resolution'])
                    
                    for player_uid in notif['players']:
                        is_player_1 = player_uid == notif['players'][0]
                        
                        player_embed = discord.Embed(
                            title="⚖️ Admin Action: Match Conflict Resolved",
                            description="Your match conflict has been resolved by an administrator.",
                            color=discord.Color.gold()
                        )
                        player_embed.add_field(name="Match ID", value=f"#{notif['match_id']}", inline=True)
                        player_embed.add_field(name="Resolution", value=resolution_text, inline=True)
                        
                        if notif['resolution'] != 'invalidate':
                            mmr_change = notif['mmr_change']
                            mmr_text = f"{mmr_change:+}" if is_player_1 else f"{-mmr_change:+}"
                            player_embed.add_field(name="Your MMR Change", value=mmr_text, inline=False)
                        
                        player_embed.add_field(name="Reason", value=notif['reason'], inline=False)
                        player_embed.add_field(name="Admin", value=notif['admin_name'], inline=False)
                        
                        await send_player_notification(player_uid, player_embed)
                
                result_embed = discord.Embed(
                    title="✅ Admin: Conflict Resolved",
                    description=(
                        f"Match #{match_id} resolved as **{result['resolution']}**\n"
                        f"MMR Change: {result['mmr_change']:+}\n"
                        f"Reason: {reason}"
                    ),
                    color=discord.Color.green()
                )
            else:
                result_embed = discord.Embed(
                    title="❌ Admin: Resolution Failed",
                    description=f"Error: {result.get('error', 'Unknown error')}",
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
                    
                    player_embed = discord.Embed(
                        title="📊 Admin Action: MMR Adjusted",
                        description=f"Your MMR has been {operation_text} by an administrator.",
                        color=discord.Color.blue()
                    )
                    player_embed.add_field(name="Race", value=race, inline=True)
                    player_embed.add_field(name="Old MMR", value=str(int(result['old_mmr'])), inline=True)
                    player_embed.add_field(name="New MMR", value=str(int(result['new_mmr'])), inline=True)
                    player_embed.add_field(name="Change", value=f"{result['change']:+}", inline=False)
                    player_embed.add_field(name="Reason", value=notif['reason'], inline=False)
                    player_embed.add_field(name="Admin", value=notif['admin_name'], inline=False)
                    
                    await send_player_notification(notif['player_uid'], player_embed)
                
                result_embed = discord.Embed(
                    title="✅ Admin: MMR Adjusted",
                    description=(
                        f"Player <@{uid}> | {race}\n"
                        f"Operation: {operation.name}\n"
                        f"Old MMR: {result['old_mmr']}\n"
                        f"New MMR: {result['new_mmr']}\n"
                        f"Change: {result['change']:+}\n"
                        f"Reason: {reason}"
                    ),
                    color=discord.Color.green()
                )
            else:
                result_embed = discord.Embed(
                    title="❌ Admin: Adjustment Failed",
                    description=f"Error: {result.get('error', 'Unknown error')}",
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
            f"**Player:** <@{uid}>\n**Race:** {race}\n**Operation:** {operation_desc}\n**Reason:** {reason}\n\nThis will immediately update the player's MMR. Confirm?",
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
                    player_embed.add_field(name="Reason", value=notif['reason'], inline=False)
                    player_embed.add_field(name="Admin", value=notif['admin_name'], inline=False)
                    player_embed.add_field(name="Note", value="You can rejoin the queue at any time with `/queue`.", inline=False)
                    
                    await send_player_notification(notif['player_uid'], player_embed)
                
                result_embed = discord.Embed(
                    title="✅ Admin: Player Removed",
                    description=f"Removed <@{uid}> from queue.\nReason: {reason}",
                    color=discord.Color.green()
                )
            else:
                result_embed = discord.Embed(
                    title="❌ Admin: Removal Failed",
                    description=f"Error: {result.get('error', 'Unknown error')}",
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
                    player_embed.add_field(name="Old Count", value=str(result['old_count']), inline=True)
                    player_embed.add_field(name="New Count", value=str(result['new_count']), inline=True)
                    player_embed.add_field(name="Reason", value=notif['reason'], inline=False)
                    player_embed.add_field(name="Admin", value=notif['admin_name'], inline=False)
                    
                    await send_player_notification(notif['player_uid'], player_embed)
                
                result_embed = discord.Embed(
                    title="✅ Admin: Aborts Reset",
                    description=(
                        f"Player <@{uid}>\n"
                        f"Old count: {result['old_count']}\n"
                        f"New count: {result['new_count']}\n"
                        f"Reason: {reason}"
                    ),
                    color=discord.Color.green()
                )
            else:
                result_embed = discord.Embed(
                    title="❌ Admin: Reset Failed",
                    description=f"Error: {result.get('error', 'Unknown error')}",
                    color=discord.Color.red()
                )
            
            await button_interaction.edit_original_response(embed=result_embed, view=None)
        
        embed, view = _create_admin_confirmation(
            interaction,
            "⚠️ Admin: Confirm Abort Reset",
            f"**Player:** <@{uid}>\n**New Count:** {new_count}\n**Reason:** {reason}\n\nThis will update the player's abort counter. Confirm?",
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
                    player_embed.add_field(name="Reason", value=notif['reason'], inline=False)
                    player_embed.add_field(name="Admin", value=notif['admin_name'], inline=False)
                    player_embed.add_field(name="Note", value="You can rejoin the queue at any time with `/queue`.", inline=False)
                    
                    for player_id in notif['player_uids']:
                        await send_player_notification(player_id, player_embed)
                
                result_embed = discord.Embed(
                    title="🚨 Admin: EMERGENCY Queue Cleared",
                    description=(
                        f"**Removed {result['players_removed']} player(s) from queue.**\n\n"
                        f"Reason: {reason}"
                    ),
                    color=discord.Color.red()
                )
            else:
                result_embed = discord.Embed(
                    title="❌ Admin: Clear Failed",
                    description=f"Error: {result.get('error', 'Unknown error')}",
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

