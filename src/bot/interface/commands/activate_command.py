import discord
from discord import app_commands
from components.confirm_embed import ConfirmEmbedView
from components.error_embed import ErrorEmbedException, create_simple_error_view


# API Call / Data Handling
def submit_activation_code(user_id: int, code: str) -> dict:
    """
    Stub function: bundle inputs and forward to backend later.
    For now, just logs and echoes the code.
    """
    print(f"[TERMINAL] Activation attempt by {user_id} with code: {code}")
    
    # Example validation that could trigger an error
    if len(code) < 3:
        raise ErrorEmbedException(
            title="Invalid Activation Code",
            description="The activation code you provided is too short.",
            error_fields=[
                ("Provided Code", code),
                ("Minimum Length", "3 characters"),
                ("Your Code Length", f"{len(code)} characters")
            ]
        )
    
    if code.lower() == "error":
        raise ErrorEmbedException(
            title="Activation Failed",
            description="The activation code is invalid or has expired.",
            error_fields=[
                ("Error Code", "INVALID_CODE"),
                ("Reason", "Code not found in database"),
                ("Suggestion", "Please check your code and try again")
            ]
        )
    
    return {"status": "ok", "code": code}


# Register Command
def register_activate_command(tree: app_commands.CommandTree):
    @tree.command(
        name="activate",
        description="Enter your activation code for ladder access"
    )
    async def activate(interaction: discord.Interaction):
        print(f"[TERMINAL] /activate started by {interaction.user.id}")
        await interaction.response.send_modal(ActivateModal())


# UI Elements
class ActivateModal(discord.ui.Modal, title="Enter Activation Code"):
    code_input = discord.ui.TextInput(
        label="Activation Code",
        placeholder="Paste your code here",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            result = submit_activation_code(interaction.user.id, self.code_input.value)

            # Show preview with confirm/restart/cancel options
            async def confirm_callback(interaction: discord.Interaction):
                # Process the activation
                # TODO: Add actual backend processing here
                
                # Show post-confirmation view
                post_confirm_view = ConfirmEmbedView(
                    title="Activation Complete",
                    description="Your activation code has been processed successfully.",
                    fields=[("Entered Code", result["code"])],
                    mode="post_confirmation",
                    reset_target=ActivateModal(),
                    restart_label="🔄 Activate Another"
                )
                await interaction.response.edit_message(embed=post_confirm_view.embed, view=post_confirm_view)

            confirm_view = ConfirmEmbedView(
                title="Preview Activation",
                description="Please review your activation code before confirming:",
                fields=[("Entered Code", result["code"])],
                mode="preview",
                confirm_callback=confirm_callback,
                reset_target=ActivateModal()
            )
            await interaction.response.send_message(embed=confirm_view.embed, view=confirm_view, ephemeral=True)
            
        except ErrorEmbedException as e:
            # Handle custom error exceptions
            error_view = create_simple_error_view(
                title=e.title,
                description=e.description,
                error_fields=e.error_fields,
                reset_target=ActivateModal()
            )
            await interaction.response.send_message(embed=error_view.embed, view=error_view, ephemeral=True)
            
        except Exception as e:
            # Handle unexpected errors
            error_view = create_simple_error_view(
                title="Unexpected Error",
                description="An unexpected error occurred while processing your activation code.",
                error_fields=[
                    ("Error Type", type(e).__name__),
                    ("Error Message", str(e)),
                    ("Suggestion", "Please try again or contact support if the issue persists")
                ],
                reset_target=ActivateModal()
            )
            await interaction.response.send_message(embed=error_view.embed, view=error_view, ephemeral=True)