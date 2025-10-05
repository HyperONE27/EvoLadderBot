from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import pytest

from src.backend.services import user_info_service


@dataclass(frozen=True)
class EmbedCase:
    name: str
    user_info: Dict[str, str]
    expected: Dict[str, str]


EMBED_CASES = [
    EmbedCase(
        name="basic_user",
        user_info={
            "display_name": "TestUser",
            "id": 123,
            "username": "TestUser",
            "discriminator": "1234",
            "mention": "@TestUser",
        },
        expected={
            "name": "User Information",
            "value": "**Username:** TestUser\n**Discord ID:** `123`\n**Tag:** TestUser#1234",
            "inline": False,
        },
    ),
    EmbedCase(
        name="no_discriminator",
        user_info={
            "display_name": "Player",
            "id": 456,
            "username": "Player",
            "discriminator": "0",
            "mention": "@Player",
        },
        expected={
            "name": "User Information",
            "value": "**Username:** Player\n**Discord ID:** `456`",
            "inline": False,
        },
    ),
]


@pytest.mark.parametrize("case", EMBED_CASES, ids=lambda case: case.name)
def test_create_user_embed_field(case: EmbedCase) -> None:
    embed_field = user_info_service.create_user_embed_field(case.user_info, title="User Information")
    assert embed_field == case.expected


LOG_CASES = [
    ("basic_log", {"display_name": "Player", "id": 1}, "did something", ""),
    ("with_details", {"display_name": "Player", "id": 1}, "updated profile", "New country: US"),
]


@pytest.mark.parametrize("case_name, user_info, action, details", LOG_CASES)
def test_log_user_action(case_name: str, user_info: Dict[str, str], action: str, details: str, capsys) -> None:
    user_info_service.log_user_action(user_info, action, details)
    captured = capsys.readouterr()
    expected = f"User {user_info['display_name']} (ID: {user_info['id']}) {action}"
    if details:
        expected += f" - {details}"
    expected += "\n"
    assert captured.out == expected
