"""Core types for the orchestration example."""

from typing import Dict, Any, Optional
from enum import Enum


class TaskStatus(Enum):
    """Valid task states in the system."""
    CREATED = "created"
    VALIDATED = "validated"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Task:
    """Represents a task in the system."""

    def __init__(self, task_id: str, data: Dict[str, Any]):
        self.task_id = task_id
        self.data = data
        self.status = TaskStatus.CREATED
        self.error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary representation."""
        return {
            "task_id": self.task_id,
            "data": self.data,
            "status": self.status.value,
            "error_message": self.error_message,
        }


class OrchestrationResult:
    """Result of an orchestration operation."""

    def __init__(self, success: bool, task: Optional[Task] = None, error: Optional[str] = None):
        self.success = success
        self.task = task
        self.error = error
