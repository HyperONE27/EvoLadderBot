"""
Help command for EvoLadderBot.

Provides a comprehensive overview of all available commands with detailed descriptions.
"""

import discord
from discord import app_commands

from src.bot.utils.discord_utils import send_ephemeral_response


def register_help_command(tree: app_commands.CommandTree):
    """Register the help command"""
    @tree.command(
        name="help",
        description="Get help and information about all available commands"
    )
    async def help(interaction: discord.Interaction):
        await help_command(interaction)
    
    return help


async def help_command(interaction: discord.Interaction):
    """Display help information for all available commands."""
    
    # Create the main help embed
    embed = discord.Embed(
        title="🤖 SC: Evo Complete Ladder Bot Help",
        description="Everything you need to know to get started and play matches",
        color=discord.Color.blue()
    )
    
    # Newbie section first
    embed.add_field(
        name="🆕 **New to the bot? Start here:**",
        value=(
            "**Step 1:** `/termsofservice` - Accept the rules to play\n"
            "**Step 2:** `/setup` - Tell the bot your StarCraft info (race, region, etc.)\n"
            "**Step 3:** `/queue` - Join matchmaking to find opponents\n"
            "**Step 4:** Play your match and report the result\n"
            "**Step 5:** `/leaderboard` - See your rank and progress\n\n"
            "*That's it! You're now playing in the ladder.*"
        ),
        inline=False
    )
    
    # Quick command reference
    embed.add_field(
        name="⚡ **Quick Commands**",
        value=(
            "`/queue` - Find a match\n"
            "`/leaderboard` - See rankings\n"
            "`/profile` - Check your stats\n"
            "`/setup` - Configure your player info\n"
            "`/setcountry` - Update your country\n"
            "`/prune` - Clean up old bot messages"
        ),
        inline=False
    )
    
    # Detailed command explanations
    embed.add_field(
        name="📋 **Command Details**",
        value=(
            "**`/queue`** - Join matchmaking\n\n"
            
            "**`/leaderboard`** - View player rankings\n"
            
            "**`/profile`** - Your player info\n"
            "• Shows your current rank and MMR\n"
            "• Displays match history\n"
            "• Shows win/loss record\n\n"
            
            "**`/setup`** - Configure your profile\n"
            "• Set your race (Terran/Zerg/Protoss)\n"
            "• Choose your region\n"
            "• **Required before you can queue**\n\n"
            
            "**`/setcountry`** - Update your country"
            
            "**`/prune`** - Clean up messages\n"
            "• Removes old bot messages\n"
            "• Keeps channels tidy"
        ),
        inline=False
    )
    
    # How the system works
    embed.add_field(
        name="🎯 **How It Works**",
        value=(
            "**Matchmaking:**\n"
            "• You join `/queue` to find opponents\n"
            "• System matches you with similar skill players\n"
            "• You get 2 minutes to accept or decline\n"
            "• Play your match and report the result\n\n"
            
            "**Ranking System:**\n"
            "• Start at 1500 MMR (F-rank)\n"
            "• Win matches to gain MMR and rank up\n"
            "• Lose matches to lose MMR\n"
            "• Ranks: F → E → D → C → B → A → S\n\n"
            
            "**Cross-Game Play:**\n"
            "• Brood War players vs StarCraft II players\n"
            "• Same ranking system for both games\n"
            "• Fair matchmaking across both games"
        ),
        inline=False
    )
    
    # Tips and troubleshooting
    embed.add_field(
        name="💡 **Tips & Troubleshooting**",
        value=(
            "**Getting Started:**\n"
            "• All commands work in DMs for privacy\n"
            "• You must `/setup` before you can `/queue`\n"
            "• Check `/leaderboard` to see if others are online\n\n"
            
            "**Common Issues:**\n"
            "• Can't queue? Make sure you've done `/setup`\n"
            "• No matches? Try again in 45 seconds\n"
            "• Channel cluttered? Use `/prune` to clean up\n\n"
            
            "**Need More Help?**\n"
            "• Contact server admins for technical issues\n"
            "• Check if other players are online with `/leaderboard`\n"
            "• All commands work in private DMs"
        ),
        inline=False
    )
    
    # Add footer
    embed.set_footer(
        text="EvoLadderBot • Cross-game StarCraft matchmaking • Use commands in DMs for privacy"
    )
    
    # Send the help embed
    await send_ephemeral_response(interaction, embed=embed)
