import discord
from discord import app_commands
from src.utils.user_utils import get_user_info, log_user_action
from components.confirm_embed import ConfirmEmbedView


# API Call / Data Handling
async def termsofservice_command(interaction: discord.Interaction):
    """Show the terms of service"""
    user_info = get_user_info(interaction)
    
    # Create the Terms of Service embed
    embed = discord.Embed(
        title="📋 Terms of Service",
        description="Please read and understand our Terms of Service before using EvoLadderBot services.",
        color=discord.Color.blue()
    )
    
    # Add main terms sections
    embed.add_field(
        name="1. Service Description",
        value="EvoLadderBot provides matchmaking services for StarCraft players. By using our services, you agree to participate in fair and respectful gameplay.",
        inline=False
    )
    
    embed.add_field(
        name="2. User Responsibilities",
        value="• Provide accurate player information\n• Maintain respectful behavior in all interactions\n• Report any bugs or issues promptly\n• Follow Discord's Terms of Service",
        inline=False
    )
    
    embed.add_field(
        name="3. Data Collection",
        value="We collect the following information:\n• Discord User ID\n• Player IDs and BattleTags\n• Country and region information\n• Matchmaking preferences\n\nThis data is used solely for matchmaking purposes.",
        inline=False
    )
    
    embed.add_field(
        name="4. Privacy & Security",
        value="• Your data is stored securely\n• We do not share personal information with third parties\n• You can request data deletion at any time\n• All communications are encrypted",
        inline=False
    )
    
    embed.add_field(
        name="5. Prohibited Activities",
        value="• Cheating or exploiting game mechanics\n• Harassment or toxic behavior\n• Sharing false information\n• Attempting to manipulate matchmaking",
        inline=False
    )
    
    embed.add_field(
        name="6. Service Availability",
        value="• Services are provided 'as is'\n• We reserve the right to modify or discontinue services\n• Maintenance may cause temporary downtime\n• No guarantee of continuous availability",
        inline=False
    )
    
    embed.add_field(
        name="7. Limitation of Liability",
        value="EvoLadderBot is not responsible for:\n• Game outcomes or performance\n• Third-party service disruptions\n• User-generated content\n• Indirect or consequential damages",
        inline=False
    )
    
    embed.add_field(
        name="8. Changes to Terms",
        value="We may update these terms at any time. Continued use of our services constitutes acceptance of updated terms. Users will be notified of significant changes.",
        inline=False
    )
    
    embed.add_field(
        name="9. Contact Information",
        value="For questions about these terms or our services, please contact our support team through Discord or our official channels.",
        inline=False
    )
    
    embed.add_field(
        name="10. Acceptance",
        value="By using EvoLadderBot services, you acknowledge that you have read, understood, and agree to be bound by these Terms of Service.",
        inline=False
    )
    
    # Add footer with version and date
    embed.set_footer(
        text="EvoLadderBot Terms of Service v1.0 • Last updated: January 15, 2025",
        icon_url="https://cdn.discordapp.com/emojis/1234567890123456789.png"  # Replace with actual bot icon
    )


    # Log the action
    log_user_action(user_info, "viewed terms of service")

    # Create confirmation callback
    async def confirm_callback(interaction: discord.Interaction):
        # Log the confirmation
        log_user_action(user_info, "confirmed terms of service")

        # TODO: Update in backend that user has confirmed the terms of service
        # async with aiohttp.ClientSession() as session:
        #     await session.patch(
        #         f'http://backend/api/players/{user_info["id"]}',
        #         json={'terms_of_service_confirmed': True, 'discord_user_id': user_info["id"]}
        #     )

        # Show post-confirmation view
        post_confirm_view = ConfirmEmbedView(
            title="Terms of Service Confirmed",
            description="Thank you for confirming the EvoLadderBot Terms of Service.",
            fields=[
                ("User", user_info.get("username", "Unknown")),
                ("Status", "Terms Accepted"),
                ("Access", "Full EvoLadderBot features unlocked")
            ],
            mode="post_confirmation",
            reset_target=None,  # No restart option for TOS
            restart_label="🔄 View Terms Again"
        )
        post_confirm_view.embed.set_footer(
            text="You may now use all EvoLadderBot features.",
            icon_url="https://cdn.discordapp.com/emojis/1234567890123456789.png"
        )
        await interaction.response.edit_message(embed=post_confirm_view.embed, view=post_confirm_view)

    # Create a simple view for the reset target
    class TOSResetView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
        
        @discord.ui.button(label="🔄 View Again", style=discord.ButtonStyle.secondary)
        async def retry(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message(
                "Please use `/termsofservice` command again to view the terms.",
                ephemeral=True
            )

    # Use the new confirm embed system
    confirm_view = ConfirmEmbedView(
        title="Preview Terms Acceptance",
        description="Please review the terms and confirm your acceptance:",
        fields=[
            ("User", user_info.get("username", "Unknown")),
            ("Status", "Ready to confirm")
        ],
        mode="preview",
        confirm_callback=confirm_callback,
        reset_target=TOSResetView(),
        confirm_label="✅ I Accept",
        cancel_label="❌ Decline"
    )

    await interaction.response.send_message(
        embed=embed,
        view=confirm_view,
        ephemeral=True
    )


# Register Command
def register_termsofservice_command(tree: app_commands.CommandTree):
    """Register the termsofservice command.

    Args:
        tree: The app command tree to register the command to.

    Returns:
        The registered command.
    """
    @tree.command(
        name="termsofservice",
        description="Show the terms of service"
    )
    async def termsofservice(interaction: discord.Interaction):
        await termsofservice_command(interaction)

    return termsofservice