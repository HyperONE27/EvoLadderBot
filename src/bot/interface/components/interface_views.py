import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

class CheckboxButton(discord.ui.Button):
    def __init__(self, label: str):
        super().__init__(label=f"[ ] {label}", style=discord.ButtonStyle.secondary)
        self.checked = False
        self.base_label = label

    async def callback(self, interaction: discord.Interaction):
        self.checked = not self.checked
        self.label = f"[{'X' if self.checked else ' '}] {self.base_label}"
        await interaction.response.edit_message(view=self.view)


class LadderSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.selections = {}
        self.checkboxes = [
            CheckboxButton("Observer"),
            CheckboxButton("Caster"),
            CheckboxButton("Player"),
        ]
        for cb in self.checkboxes:
            self.add_item(cb)

    @discord.ui.select(
        placeholder="Select your region...",
        options=[
            discord.SelectOption(label="NA", description="North America"),
            discord.SelectOption(label="EU", description="Europe"),
            discord.SelectOption(label="KR", description="Korea"),
            discord.SelectOption(label="Other", description="Anywhere else"),
        ]
    )
    async def region_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selections["region"] = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="Select your race...",
        options=[
            discord.SelectOption(label="Terran"),
            discord.SelectOption(label="Protoss"),
            discord.SelectOption(label="Zerg"),
            discord.SelectOption(label="Random"),
        ]
    )
    async def race_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selections["race"] = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="Select game mode...",
        options=[
            discord.SelectOption(label="1v1"),
            discord.SelectOption(label="2v2"),
            discord.SelectOption(label="Custom"),
        ]
    )
    async def mode_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selections["mode"] = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="Pick multiple roles...",
        min_values=0,
        max_values=3,
        options=[
            discord.SelectOption(label="Leader"),
            discord.SelectOption(label="Strategist"),
            discord.SelectOption(label="Support"),
        ]
    )
    async def multi_roles(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selections["multi_roles"] = select.values
        await interaction.response.defer()

    @discord.ui.button(label="OK", style=discord.ButtonStyle.success)
    async def ok_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        checked_boxes = [cb.base_label for cb in self.checkboxes if cb.checked]
        if checked_boxes:
            self.selections["checkbox_roles"] = checked_boxes

        summary = []
        for k, v in self.selections.items():
            if isinstance(v, list):
                summary.append(f"**{k.capitalize()}**: {', '.join(v)}")
            else:
                summary.append(f"**{k.capitalize()}**: {v}")
        if not summary:
            summary = ["_No selections made_"]

        await interaction.response.send_message(
            "✅ Setup complete:\n" + "\n".join(summary),
            ephemeral=True
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Setup cancelled.", ephemeral=True)


class SetupNotesModal(discord.ui.Modal, title="Extra Setup Notes"):
    nickname = discord.ui.TextInput(label="Preferred nickname", required=False, max_length=32)
    comments = discord.ui.TextInput(
        label="Any additional comments?",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Got it! Nickname: {self.nickname.value or 'None'}\n"
            f"Comments: {self.comments.value or 'None'}",
            ephemeral=True
        )


class SetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)

    @discord.ui.select(
        placeholder="Select game modes (multi-select allowed)",
        min_values=1,
        max_values=3,
        options=[
            discord.SelectOption(label="1v1"),
            discord.SelectOption(label="2v2"),
            discord.SelectOption(label="FFA"),
            discord.SelectOption(label="Arcade"),
        ]
    )
    async def modes_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.send_message(
            f"You picked: {', '.join(select.values)}", ephemeral=True
        )

    @discord.ui.select(
        placeholder="Pick your main faction",
        options=[
            discord.SelectOption(label="Terran"),
            discord.SelectOption(label="Protoss"),
            discord.SelectOption(label="Zerg"),
            discord.SelectOption(label="Random"),
        ]
    )
    async def faction_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.send_message(
            f"Main faction set to: {select.values[0]}", ephemeral=True
        )

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("✅ Setup confirmed!", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Setup cancelled.", ephemeral=True)

    @discord.ui.button(label="Add Notes", style=discord.ButtonStyle.secondary)
    async def notes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetupNotesModal())


# -------------------------------
# Page 1
# -------------------------------
class PageOneView(discord.ui.View):
    def __init__(self, selections=None):
        super().__init__(timeout=600)
        self.selections = selections or {}

        # add nav button
        self.add_item(NextPageButton())

    @discord.ui.select(
        placeholder="Select your region...",
        options=[
            discord.SelectOption(label="NA"),
            discord.SelectOption(label="EU"),
            discord.SelectOption(label="KR"),
        ],
        row=0
    )
    async def region_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selections["region"] = select.values[0]
        await interaction.response.defer()


# -------------------------------
# Page 2
# -------------------------------
class PageTwoView(discord.ui.View):
    def __init__(self, selections=None):
        super().__init__(timeout=600)
        self.selections = selections or {}

        self.add_item(PrevPageButton())
        self.add_item(FinishButton())
        self.add_item(CancelButton())

    @discord.ui.select(
        placeholder="Pick your main race...",
        options=[
            discord.SelectOption(label="Terran"),
            discord.SelectOption(label="Protoss"),
            discord.SelectOption(label="Zerg"),
            discord.SelectOption(label="Random"),
        ],
        row=0
    )
    async def race_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selections["race"] = select.values[0]
        await interaction.response.defer()



class NextPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="➡️ Next", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        # Switch to Page 2, carrying over state
        new_view = PageTwoView(self.view.selections)
        await interaction.response.edit_message(
            content="Setup (Page 2)",
            view=new_view
        )


class PrevPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="⬅️ Prev", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        # Switch back to Page 1, carrying over state
        new_view = PageOneView(self.view.selections)
        await interaction.response.edit_message(
            content="Setup (Page 1)",
            view=new_view
        )



class FinishButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="✅ Finish", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        summary = "\n".join(f"**{k}**: {v}" for k, v in self.view.selections.items()) or "_No selections made_"
        await interaction.response.edit_message(content="✅ Setup complete:\n" + summary, view=None)


class CancelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="❌ Cancel", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="❌ Setup cancelled.", view=None)

