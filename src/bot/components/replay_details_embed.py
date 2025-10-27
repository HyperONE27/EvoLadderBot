import discord
from typing import Dict, Any, Optional

from src.backend.services.races_service import RacesService
from src.bot.utils.discord_utils import get_race_emote


class ReplayDetailsEmbed:
    """Class for creating replay details embeds."""

    @staticmethod
    def get_success_embed(replay_data: Dict[str, Any], verification_results: Optional[Dict[str, Any]] = None) -> discord.Embed:
        """Creates a gray embed with details of a parsed replay."""
        # Extract data
        p1_name = replay_data.get('player_1_name')
        p2_name = replay_data.get('player_2_name')
        p1_race_str = replay_data['player_1_race']
        p2_race_str = replay_data['player_2_race']
        winner_result = replay_data.get('result')
        map_name = replay_data.get('map_name')
        duration_seconds = replay_data.get('duration')
        observers = replay_data.get('observers')
        
        p1_race_emote = get_race_emote(p1_race_str)
        p2_race_emote = get_race_emote(p2_race_str)

        # Determine winner
        if winner_result == 1:
            winner_text = f"🏆 {p1_race_emote} {p1_name}"
        elif winner_result == 2:
            winner_text = f"🏆 {p2_race_emote} {p2_name}"
        else:
            winner_text = f"⚖️ Draw"
            
        # Format duration
        minutes, seconds = divmod(duration_seconds, 60)
        duration_text = f"{minutes:02d}:{seconds:02d}"

        # List observers, if any
        if observers:
            observers_text = "⚠️ " + ", ".join(observers)
        else:
            observers_text = "✅ None"
        
        # Format map name
        if "(" in map_name:
            map_name = map_name.replace(" (", "\n(", 1)

        embed = discord.Embed(
            title="📄 Replay Details",
            description="Summary of the uploaded replay for the match.",
            color=discord.Color.light_grey()
        )
        
        embed.add_field(
            name="Matchup",
            value=f"**{p1_race_emote} {p1_name}** vs **{p2_race_emote} {p2_name}**",
            inline=False
        )

        embed.add_field(name="Map", value=map_name, inline=True)
        embed.add_field(name="Duration", value=duration_text, inline=True)
        embed.add_field(name="Winner", value=winner_text, inline=True)

        embed.add_field(
            name="Observers Present",
            value=observers_text,
            inline=False
        )
        
        # --- Replay Verification Section ---
        verification_text = ""
        if verification_results is None:
            verification_text = "⏳ Verifying details..."
        else:
            # Detailed messages for each verification check
            check_messages = {
                "races_match": ("Races match", "Races played correspond to races queued with.", "Races played DO NOT correspond to races queued with."),
                "map_match": ("Map name matches", "Map used corresponds to the map assigned.", "Map used DOES NOT correspond to the map assigned."),
                "timestamp_match": ("Timestamp matches", "Match was initiated within the allowed time window.", "Match was NOT initiated within the allowed time window."),
                "observers_ok": ("No observers", "No unverified observers detected.", "Unauthorized observers detected."),
            }

            lines = []
            for key, (name, pass_msg, fail_msg) in check_messages.items():
                result = verification_results.get(key)
                if result is True:
                    lines.append(f"- {name}: ✅ {pass_msg}")
                elif result is False:
                    lines.append(f"- {name}: ❌ {fail_msg}")
            
            # Add winner detection status
            if verification_results.get("all_ok"):
                lines.append("- Winner detection: ✅ Match details verified, automatically reporting the winner.")
                lines.append("\n✅ No issues detected.")
            else:
                lines.append("- Winner detection: ❌ Details not verified, please report winner manually.")
                lines.append("\n⚠️ One or more match parameters were incorrect.")
            
            verification_text = "\n".join(lines)
        
        embed.add_field(
            name="**Replay Verification**",
            value=verification_text,
            inline=False
        )
        
        return embed

    @staticmethod
    def get_error_embed(error_message: str) -> discord.Embed:
        """Creates a red error embed for a replay parsing failure."""
        embed = discord.Embed(
            title="❌ Replay Parsing Failed",
            description=f"The uploaded file could not be parsed as a valid SC2Replay.\nPlease try again with a different file.",
            color=discord.Color.red()
        )
        embed.add_field(
            name="Error Details",
            value=f"```{error_message}```",
            inline=False
        )
        return embed