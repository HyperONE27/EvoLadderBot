"""Transition manager - defines and enforces allowed state transitions."""

from typing import Callable, Dict, Any, Optional
from ..core.types import Task, TaskStatus
from ..core.config import OrchestrationConfig


class TransitionManager:
    """Manages allowed state transitions and their associated actions.

    Centralizes the definition of valid state flows and coordinates
    the actions that should occur during transitions.
    """

    def __init__(self, state_manager):
        self.state_manager = state_manager
        # Map of (from_status, to_status) -> transition function
        self._transition_actions: Dict[tuple, Callable] = {}

    def register_transition(self, from_status: str, to_status: str,
                          action: Callable[[Task], None]) -> None:
        """Register an action to perform during a specific transition."""
        key = (from_status, to_status)
        if key in self._transition_actions:
            raise ValueError(f"Transition {from_status} -> {to_status} already registered")
        self._transition_actions[key] = action

    def attempt_transition(self, task_id: str, new_status: TaskStatus,
                          error_message: Optional[str] = None) -> bool:
        """Attempt to transition a task to a new status.

        Returns True if transition was successful, False otherwise.
        """
        task = self.state_manager.get_task(task_id)
        if not task:
            return False

        current_status = task.status.value

        # Check if transition is allowed
        if not OrchestrationConfig.is_valid_transition(current_status, new_status.value):
            return False

        # Execute transition action if registered
        transition_key = (current_status, new_status.value)
        if transition_key in self._transition_actions:
            try:
                self._transition_actions[transition_key](task)
            except Exception as e:
                # Transition action failed - don't update status
                print(f"Transition action failed for {task_id}: {e}")
                return False

        # Update the state
        return self.state_manager.update_task_status(task_id, new_status, error_message)

    def get_allowed_transitions(self, task_id: str) -> list:
        """Get list of allowed next statuses for a task."""
        task = self.state_manager.get_task(task_id)
        if not task:
            return []

        current_status = task.status.value
        return OrchestrationConfig.VALID_TRANSITIONS.get(current_status, [])
