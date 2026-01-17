"""Orchestrator package - centralized orchestration logic."""

from .state_manager import StateManager
from .transition_manager import TransitionManager
from .service_orchestrator import ServiceOrchestrator
from ..services.task_validator import TaskValidator
from ..services.task_processor import TaskProcessor
from ..services.task_persistence import TaskPersistence


class Orchestrator:
    """Main orchestrator that brings all components together."""

    def __init__(self):
        # Create centralized state manager
        self.state_manager = StateManager()

        # Create stateless services
        self.task_validator = TaskValidator()
        self.task_processor = TaskProcessor()
        self.task_persistence = TaskPersistence()

        # Create transition manager
        self.transition_manager = TransitionManager(self.state_manager)

        # Create service orchestrator
        self.service_orchestrator = ServiceOrchestrator(
            self.state_manager,
            self.transition_manager,
            self.task_validator,
            self.task_processor,
            self.task_persistence
        )

        # Register transition actions (optional - for side effects)
        self._setup_transitions()

    def _setup_transitions(self):
        """Set up any transition-specific actions."""
        # In this example, transitions are pure state changes
        # but you could add logging, notifications, etc. here
        pass

    def create_task(self, task_id: str, data: dict) -> dict:
        """Create a new task."""
        try:
            task = self.state_manager.create_task(task_id, data)
            return {"success": True, "task": task.to_dict()}
        except ValueError as e:
            return {"success": False, "error": str(e)}

    async def process_task(self, task_id: str):
        """Process a task through the orchestration pipeline."""
        return await self.service_orchestrator.process_task(task_id)

    def get_task_status(self, task_id: str):
        """Get current status of a task."""
        task = self.service_orchestrator.get_task_status(task_id)
        return task.to_dict() if task else None

    def get_all_tasks(self):
        """Get all tasks (for debugging)."""
        tasks = self.state_manager.get_all_tasks()
        return {tid: task.to_dict() for tid, task in tasks.items()}

    def cleanup_completed(self):
        """Clean up completed and failed tasks."""
        return self.state_manager.clear_completed_tasks()
