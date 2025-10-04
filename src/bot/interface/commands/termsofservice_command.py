import discord
from discord import app_commands
from src.backend.services.user_info_service import UserInfoService, get_user_info, log_user_action
from components.confirm_embed import ConfirmEmbedView

user_info_service = UserInfoService()


# API Call / Data Handling
async def termsofservice_command(interaction: discord.Interaction):
    """Show the terms of service"""
    # Ensure player exists in database
    user_info_service.ensure_player_exists(interaction.user.id, interaction.user.name)
    
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
        # Update in backend that user has confirmed the terms of service
        success = user_info_service.accept_terms_of_service(user_info["id"])
        
        if not success:
            error_embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while confirming your acceptance. Please try again.",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(
                embed=error_embed,
                view=None
            )
            return
        
        # Log the confirmation
        log_user_action(user_info, "confirmed terms of service")

        # Show post-confirmation view
        post_confirm_view = ConfirmEmbedView(
            title="Terms of Service Confirmed",
            description="Thank you for confirming the EvoLadderBot Terms of Service.",
            mode="post_confirmation",
            reset_target=None  # No restart option for TOS
        )
        post_confirm_view.embed.set_footer(
            text="You may now use all EvoLadderBot features.",
            icon_url="https://cdn.discordapp.com/emojis/1234567890123456789.png"
        )
        await interaction.response.edit_message(embed=post_confirm_view.embed, view=post_confirm_view)

    # Create custom cancel callback for terms of service
    async def cancel_callback(interaction: discord.Interaction):
        # Log the decline
        log_user_action(user_info, "declined terms of service")

        # Create custom decline embed
        decline_embed = discord.Embed(
            title="❌ Terms of Service Declined",
            description="Since you have declined the Terms of Service, you may not use EvoLadderBot services.",
            color=discord.Color.red()
        )
        decline_embed.set_footer(
            text="You may use /termsofservice to review the terms again if you change your mind.",
            icon_url="https://cdn.discordapp.com/emojis/1234567890123456789.png"
        )

        await interaction.response.edit_message(embed=decline_embed, view=None)

    # Create custom view with only confirm and cancel buttons (no restart)
    class TOSConfirmView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=300)
        
        @discord.ui.button(label="I Accept These Terms", emoji="✅", style=discord.ButtonStyle.success)
        async def accept_terms(self, interaction: discord.Interaction, button: discord.ui.Button):
            await confirm_callback(interaction)
        
        @discord.ui.button(label="I Decline These Terms", emoji="❌", style=discord.ButtonStyle.danger)
        async def decline_terms(self, interaction: discord.Interaction, button: discord.ui.Button):
            await cancel_callback(interaction)

    confirm_view = TOSConfirmView()

    # Send the full terms of service first
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