"""Stateless task validation service."""

from typing import Dict, Any
from ..core.types import Task


class TaskValidator:
    """Stateless service for validating tasks.

    Contains no internal state - all operations are pure functions
    that operate on the provided task data.
    """

    async def validate(self, task: Task) -> Dict[str, Any]:
        """Validate a task's data.

        Returns dict with 'valid' boolean and optional 'error' message.
        """
        try:
            # Check required fields
            required_fields = ["name", "priority"]
            for field in required_fields:
                if field not in task.data:
                    return {
                        "valid": False,
                        "error": f"Missing required field: {field}"
                    }

            # Validate priority range
            priority = task.data.get("priority")
            if not isinstance(priority, int) or not (1 <= priority <= 10):
                return {
                    "valid": False,
                    "error": "Priority must be integer between 1-10"
                }

            # Validate name length
            name = task.data.get("name", "")
            if not isinstance(name, str) or len(name.strip()) < 3:
                return {
                    "valid": False,
                    "error": "Name must be string with at least 3 characters"
                }

            return {"valid": True}

        except Exception as e:
            return {
                "valid": False,
                "error": f"Validation error: {str(e)}"
            }
