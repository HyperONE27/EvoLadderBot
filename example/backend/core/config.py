"""Configuration for the orchestration example."""

from typing import Dict, Any


class OrchestrationConfig:
    """Configuration for the orchestration system."""

    # Valid state transitions - centralized control of allowed flows
    VALID_TRANSITIONS = {
        "created": ["validated", "failed"],
        "validated": ["processing", "failed"],
        "processing": ["completed", "failed"],
        "completed": [],  # Terminal state
        "failed": [],     # Terminal state
    }

    # Service operation timeouts (in seconds)
    SERVICE_TIMEOUTS = {
        "validate": 5,
        "process": 10,
        "persist": 3,
    }

    # Maximum retry attempts for failed operations
    MAX_RETRIES = 3

    @classmethod
    def is_valid_transition(cls, from_status: str, to_status: str) -> bool:
        """Check if a state transition is allowed."""
        return to_status in cls.VALID_TRANSITIONS.get(from_status, [])
