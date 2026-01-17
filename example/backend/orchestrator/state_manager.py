"""Centralized state manager - owns all state in the system."""

from typing import Dict, Optional
from threading import Lock

from ..core.types import Task, TaskStatus


class StateManager:
    """Centralized state owner for all tasks in the system.

    This class owns all state and provides thread-safe access.
    Only the orchestrator can modify state through defined methods.
    """

    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self._lock = Lock()

    def create_task(self, task_id: str, data: Dict[str, str]) -> Task:
        """Create a new task and add it to state."""
        with self._lock:
            if task_id in self._tasks:
                raise ValueError(f"Task {task_id} already exists")

            task = Task(task_id, data)
            self._tasks[task_id] = task
            return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def update_task_status(self, task_id: str, new_status: TaskStatus,
                          error_message: Optional[str] = None) -> bool:
        """Update task status - only allowed through orchestrator."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False

            task.status = new_status
            task.error_message = error_message
            return True

    def get_all_tasks(self) -> Dict[str, Task]:
        """Get all tasks (for debugging/admin purposes)."""
        with self._lock:
            return self._tasks.copy()

    def clear_completed_tasks(self) -> int:
        """Remove completed and failed tasks, return count removed."""
        with self._lock:
            to_remove = []
            for task_id, task in self._tasks.items():
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]

            return len(to_remove)
