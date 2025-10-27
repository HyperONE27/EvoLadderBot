import discord
from typing import Dict, Any, Optional

from src.backend.core.types import VerificationResult
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
        
        if verification_results:
            verification_text = ReplayDetailsEmbed._format_verification_results(verification_results)
            embed.add_field(
                name="Replay Verification",
                value=verification_text,
                inline=False
            )
        
        return embed
    
    @staticmethod
    def _format_verification_results(results: VerificationResult) -> str:
        """
        Formats verification results into a readable string for the embed.
        
        Args:
            results: The verification results to format
            
        Returns:
            Formatted string with icons and descriptions
        """
        all_ok = all(results.values())
        
        lines = [
            f"- Races match: {'✅' if results['races_match'] else '❌'} "
            f"Races played correspond to races queued with.",
            
            f"- Map name matches: {'✅' if results['map_match'] else '❌'} "
            f"Map used corresponds to the map assigned.",
            
            f"- Timestamp matches: {'✅' if results['timestamp_match'] else '❌'} "
            f"Match was initiated within ~20 minutes of match assignment.",
            
            f"- No observers: {'✅' if results['observers_match'] else '❌'} "
            f"No unverified observers detected.",
            
            f"- Winner detection: {'✅' if all_ok else '❌'} "
            f"Match details {'verified' if all_ok else 'NOT verified'}, please report the winner manually."
        ]
        
        summary = ("✅ No issues detected." if all_ok else 
                   "⚠️ One or more match parameters were incorrect. The system will reflect the record.")
        lines.append(f"\n{summary}")
        
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