import discord
from typing import Dict, Any, Optional
from datetime import datetime

from src.backend.core.types import VerificationResult
from src.backend.core.config import REPLAY_TIMESTAMP_WINDOW_MINUTES
from src.backend.services.races_service import RacesService
from src.bot.utils.discord_utils import get_race_emote


class ReplayDetailsEmbed:
    """Class for creating replay details embeds."""

    @staticmethod
    def get_success_embed(
        replay_data: Dict[str, Any], 
        verification_results: Optional[VerificationResult] = None
    ) -> discord.Embed:
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
            winner_text = f"🥇 {p1_race_emote} {p1_name}"
        elif winner_result == 2:
            winner_text = f"🥇 {p2_race_emote} {p2_name}"
        else:
            winner_text = f"⚖️ Draw"
            
        # Format duration
        minutes, seconds = divmod(duration_seconds, 60)
        duration_text = f"{minutes:02d}:{seconds:02d}"

        # List observers, if any
        if observers:
            observers_text = "⚠️ " + ", ".join(observers)
        else:
            observers_text = "✅ No observers present"
        
        # Format map name
        if "(" in map_name:
            map_name = map_name.replace(" (", "\n(", 1)

        embed = discord.Embed(
            title="📄 Replay Details",
            description="Summary of the uploaded replay for the match.",
            color=discord.Color.light_grey()
        )
        
        # Add a line for spacing
        embed.add_field(name="", value="\u3164", inline=False)

        # Row 1: Matchup + Timestamp
        embed.add_field(
            name="⚔️ Matchup",
            value=f"**{p1_race_emote} {p1_name}** vs\n**{p2_race_emote} {p2_name}**",
            inline=True
        )

        embed.add_field(name="🏆 Result", value=winner_text, inline=True)
        embed.add_field(name="🗺️ Map", value=map_name, inline=True)

        # Add timestamp
        if replay_data.get("replay_date"):
            try:
                replay_dt = datetime.fromisoformat(
                    replay_data["replay_date"].replace('+00', '+00:00')
                )
                formatted_ts = replay_dt.strftime("%d %b %Y, %H:%M:%S UTC")
                unix_timestamp = int(replay_dt.timestamp())
                discord_ts = f"<t:{unix_timestamp}>"
                embed.add_field(
                    name="🕒 Game Start Time",
                    value=f"{formatted_ts}\n({discord_ts})",
                    inline=True
                )
            except (ValueError, TypeError):
                # Handle cases where replay_date is not a valid ISO string
                embed.add_field(
                    name="🕒 Game Start Time",
                    value="Invalid date format",
                    inline=True
                )

        embed.add_field(name="🕒 Game Duration", value=duration_text, inline=True)
        embed.add_field(name="🔍 Observers", value=observers_text, inline=True)
        
        # Add a line for spacing
        embed.add_field(name="", value="\u3164", inline=False)

        if verification_results:
            verification_text = ReplayDetailsEmbed._format_verification_results(verification_results)
            embed.add_field(
                name="☑️ Replay Verification",
                value=verification_text,
                inline=False
            )
        
        return embed
    
    @staticmethod
    def _format_verification_results(results: VerificationResult) -> str:
        """
        Formats verification results into a readable string for the embed with dynamic feedback.
        
        Args:
            results: The verification results to format
            
        Returns:
            Formatted string with icons and context-specific descriptions
        """
        lines = []
        
        # Race verification with dynamic feedback
        races_check = results['races']
        if races_check['success']:
            lines.append("- ✅ **Races Match:** Played races correspond to queued races.")
        else:
            races_service = RacesService()
            expected_names = sorted([races_service.get_race_name(code) or code for code in races_check['expected_races']])
            played_names = sorted([races_service.get_race_name(code) or code for code in races_check['played_races']])
            expected = ", ".join(expected_names)
            played = ", ".join(played_names)
            lines.append(f"- ❌ **Races Mismatch:** Expected `{expected}`, but played `{played}`.")
        
        # Map verification with dynamic feedback
        map_check = results['map']
        if map_check['success']:
            lines.append("- ✅ **Map Matches:** Correct map was used.")
        else:
            lines.append(
                f"- ❌ **Map Mismatch:** Expected `{map_check['expected_map']}`, "
                f"but played `{map_check['played_map']}`."
            )
        
        # Timestamp verification with dynamic feedback
        timestamp_check = results['timestamp']
        if timestamp_check['success']:
            time_diff = timestamp_check.get('time_difference_minutes')
            if time_diff is not None:
                lines.append(
                    f"- ✅ **Timestamp Valid:** Match started within {abs(time_diff):.1f} minutes of assignment "
                    f"(within {REPLAY_TIMESTAMP_WINDOW_MINUTES}-minute window)."
                )
        else:
            if timestamp_check.get('error'):
                lines.append(f"- ❌ **Timestamp Invalid:** Could not verify timestamp. Reason: `{timestamp_check['error']}`")
            else:
                time_diff = timestamp_check.get('time_difference_minutes')
                if time_diff is not None:
                    if time_diff < 0:
                        lines.append(
                            f"- ❌ **Timestamp Invalid:** Match started {abs(time_diff):.1f} minutes **before** assignment "
                            f"(must be between 0 and {REPLAY_TIMESTAMP_WINDOW_MINUTES} minutes after assignment)."
                        )
                    else:
                        lines.append(
                            f"- ❌ **Timestamp Invalid:** Match started {time_diff:.1f} minutes **after** assignment "
                            f"(exceeds {REPLAY_TIMESTAMP_WINDOW_MINUTES}-minute window)."
                        )
                else:
                    lines.append("- ❌ **Timestamp Invalid:** An unknown timestamp error occurred.")

        # Observer verification with dynamic feedback
        observers_check = results['observers']
        if observers_check['success']:
            lines.append("- ✅ **No Observers:** No unauthorized observers detected.")
        else:
            observer_names = ", ".join(observers_check['observers_found'])
            lines.append(f"- ❌ **Observers Detected:** Unauthorized observers found: `{observer_names}`.")
        
        # Overall status
        all_ok = all([
            races_check['success'],
            map_check['success'],
            timestamp_check['success'],
            observers_check['success']
        ])
        
        lines.append("")  # Empty line for spacing
        if all_ok:
            lines.append(
                "✅ **Verification Complete:** All checks passed. "
                "Please report the match result manually."
            )
        else:
            lines.append(
                "⚠️ **Verification Issues:** One or more checks failed. "
                "Please review the issues above and ensure match parameters are correct for future games."
            )
        
        return "\n".join(lines)

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