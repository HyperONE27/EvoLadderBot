import discord
from discord import app_commands


# API Call / Data Handling
def dummy_command_handler(interaction: discord.Interaction) -> str:
    """
    Handle dummy command logic.
    For now, just logs and returns a message.
    """
    print("[TERMINAL] /dummy command called by:", interaction.user)
    return "🧩 Dummy command with 4 multiselect dropdowns. All selections persist clearly in the UI!"


# Register Command
def register_dummy_command(tree: app_commands.CommandTree):
    """Register the dummy command."""

    @tree.command(
        name="dummy",
        description="Example command with 4 multiselect dropdowns demonstrating UI persistence."
    )
    async def dummy(interaction: discord.Interaction):
        message = dummy_command_handler(interaction)
        view = DummyMultiselectView()
        await interaction.response.send_message(message, view=view, ephemeral=True)


# UI Elements
class DummyMultiselectView(discord.ui.View):
    """Main view with 4 multiselect dropdowns demonstrating clear UI persistence."""

    def __init__(self, category_selections=None, color_selections=None, size_selections=None, priority_selections=None):
        super().__init__(timeout=300)
        
        # Initialize selection state
        self.category_selections = category_selections or []
        self.color_selections = color_selections or []
        self.size_selections = size_selections or []
        self.priority_selections = priority_selections or []
        
        # Add all dropdowns
        self.add_item(CategoryMultiselect(self.category_selections))
        self.add_item(ColorMultiselect(self.color_selections))
        self.add_item(SizeMultiselect(self.size_selections))
        self.add_item(PriorityMultiselect(self.priority_selections))

    async def update_view(self, interaction: discord.Interaction):
        """Update the view with current selections"""
        # Create a new view with current selections to maintain state
        new_view = DummyMultiselectView(
            category_selections=self.category_selections,
            color_selections=self.color_selections,
            size_selections=self.size_selections,
            priority_selections=self.priority_selections
        )
        
        await interaction.response.edit_message(
            content=new_view.get_status_message(),
            view=new_view
        )

    def get_status_message(self) -> str:
        """Get status message showing current selections"""
        message = "🧩 **Dummy Multiselect Demo**\n\n"
        
        # Category selections
        if self.category_selections:
            message += f"📂 **Categories:** `{', '.join(self.category_selections)}`\n"
        else:
            message += "📂 **Categories:** `None selected`\n"
        
        # Color selections
        if self.color_selections:
            message += f"🎨 **Colors:** `{', '.join(self.color_selections)}`\n"
        else:
            message += "🎨 **Colors:** `None selected`\n"
        
        # Size selections
        if self.size_selections:
            message += f"📏 **Sizes:** `{', '.join(self.size_selections)}`\n"
        else:
            message += "📏 **Sizes:** `None selected`\n"
        
        # Priority selections
        if self.priority_selections:
            message += f"⚡ **Priorities:** `{', '.join(self.priority_selections)}`\n"
        else:
            message += "⚡ **Priorities:** `None selected`\n"
        
        message += "\n💡 **Tip:** All selections persist clearly in the UI between refreshes!"
        
        return message


class CategoryMultiselect(discord.ui.Select):
    """Multiselect dropdown for categories"""
    
    def __init__(self, selected_values=None):
        self.selected_values = selected_values or []
        
        options = []
        # Create options with default=False, then set default=True for selected ones
        all_options = [
            ("Technology", "tech", "Tech-related items"),
            ("Gaming", "gaming", "Gaming content"),
            ("Music", "music", "Music and audio"),
            ("Sports", "sports", "Sports and fitness"),
            ("Art", "art", "Art and creativity"),
            ("Food", "food", "Food and cooking"),
            ("Travel", "travel", "Travel and adventure"),
            ("Books", "books", "Books and literature")
        ]
        
        for label, value, description in all_options:
            is_default = value in self.selected_values
            options.append(
                discord.SelectOption(
                    label=label,
                    value=value,
                    description=description,
                    default=is_default
                )
            )
        
        # Set placeholder based on current selections
        placeholder = "Select categories (multiselect)..."
        if self.selected_values:
            placeholder = f"Selected: {', '.join(self.selected_values)}"
        
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=8,
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.category_selections = self.values
        await self.view.update_view(interaction)


class ColorMultiselect(discord.ui.Select):
    """Multiselect dropdown for colors"""
    
    def __init__(self, selected_values=None):
        self.selected_values = selected_values or []
        
        options = []
        # Create options with default=False, then set default=True for selected ones
        all_options = [
            ("Red", "red", "Bold and energetic"),
            ("Blue", "blue", "Calm and trustworthy"),
            ("Green", "green", "Natural and fresh"),
            ("Yellow", "yellow", "Bright and cheerful"),
            ("Purple", "purple", "Creative and mysterious"),
            ("Orange", "orange", "Warm and enthusiastic"),
            ("Pink", "pink", "Playful and romantic"),
            ("Black", "black", "Elegant and powerful")
        ]
        
        for label, value, description in all_options:
            is_default = value in self.selected_values
            options.append(
                discord.SelectOption(
                    label=label,
                    value=value,
                    description=description,
                    default=is_default
                )
            )
        
        # Set placeholder based on current selections
        placeholder = "Select colors (multiselect)..."
        if self.selected_values:
            placeholder = f"Selected: {', '.join(self.selected_values)}"
        
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=8,
            options=options,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.color_selections = self.values
        await self.view.update_view(interaction)


class SizeMultiselect(discord.ui.Select):
    """Multiselect dropdown for sizes"""
    
    def __init__(self, selected_values=None):
        self.selected_values = selected_values or []
        
        options = []
        # Create options with default=False, then set default=True for selected ones
        all_options = [
            ("XS", "xs", "Extra Small"),
            ("S", "s", "Small"),
            ("M", "m", "Medium"),
            ("L", "l", "Large"),
            ("XL", "xl", "Extra Large"),
            ("XXL", "xxl", "Double Extra Large"),
            ("Custom", "custom", "Custom size"),
            ("Variable", "variable", "Variable size")
        ]
        
        for label, value, description in all_options:
            is_default = value in self.selected_values
            options.append(
                discord.SelectOption(
                    label=label,
                    value=value,
                    description=description,
                    default=is_default
                )
            )
        
        # Set placeholder based on current selections
        placeholder = "Select sizes (multiselect)..."
        if self.selected_values:
            placeholder = f"Selected: {', '.join(self.selected_values)}"
        
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=8,
            options=options,
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.size_selections = self.values
        await self.view.update_view(interaction)


class PriorityMultiselect(discord.ui.Select):
    """Multiselect dropdown for priorities"""
    
    def __init__(self, selected_values=None):
        self.selected_values = selected_values or []
        
        options = []
        # Create options with default=False, then set default=True for selected ones
        all_options = [
            ("Critical", "critical", "Must be done immediately"),
            ("High", "high", "Important and urgent"),
            ("Medium", "medium", "Moderately important"),
            ("Low", "low", "Can be done later"),
            ("Optional", "optional", "Nice to have"),
            ("Future", "future", "For future consideration"),
            ("Backlog", "backlog", "Add to backlog"),
            ("Deprecated", "deprecated", "No longer needed")
        ]
        
        for label, value, description in all_options:
            is_default = value in self.selected_values
            options.append(
                discord.SelectOption(
                    label=label,
                    value=value,
                    description=description,
                    default=is_default
                )
            )
        
        # Set placeholder based on current selections
        placeholder = "Select priorities (multiselect)..."
        if self.selected_values:
            placeholder = f"Selected: {', '.join(self.selected_values)}"
        
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=8,
            options=options,
            row=3
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.priority_selections = self.values
        await self.view.update_view(interaction)