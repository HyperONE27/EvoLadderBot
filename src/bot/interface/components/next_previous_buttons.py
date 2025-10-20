import discord
from typing import Optional, Callable


class NextPageButton(discord.ui.Button):
    """Button to go to the next page of results."""

    def __init__(
        self,
        callback: Callable,
        label: str = "Next Page",
        style: discord.ButtonStyle = discord.ButtonStyle.primary,
        row: int = 0,
        disabled: bool = False,
    ):
        super().__init__(
            label=label, style=style, emoji="➡️", row=row, disabled=disabled
        )
        self.callback_func = callback

    async def callback(self, interaction: discord.Interaction):
        await self.callback_func(interaction)


class PreviousPageButton(discord.ui.Button):
    """Button to go to the previous page of results."""

    def __init__(
        self,
        callback: Callable,
        label: str = "Previous Page",
        style: discord.ButtonStyle = discord.ButtonStyle.primary,
        row: int = 0,
        disabled: bool = False,
    ):
        super().__init__(
            label=label, style=style, emoji="⬅️", row=row, disabled=disabled
        )
        self.callback_func = callback

    async def callback(self, interaction: discord.Interaction):
        await self.callback_func(interaction)


class NextPreviousButtons:
    """Helper class to create sets of next/previous page buttons."""

    @staticmethod
    def create_buttons(
        next_callback: Optional[Callable] = None,
        previous_callback: Optional[Callable] = None,
        next_disabled: bool = False,
        previous_disabled: bool = False,
        next_label: str = "Next Page",
        previous_label: str = "Previous Page",
        row: int = 0,
    ) -> list[discord.ui.Button]:
        """Create a list of next/previous buttons based on provided parameters."""
        buttons = []

        if previous_callback is not None:
            buttons.append(
                PreviousPageButton(
                    previous_callback,
                    previous_label,
                    row=row,
                    disabled=previous_disabled,
                )
            )

        if next_callback is not None:
            buttons.append(
                NextPageButton(
                    next_callback, next_label, row=row, disabled=next_disabled
                )
            )

        return buttons
