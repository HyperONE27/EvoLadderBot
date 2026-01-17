"""Service orchestrator - coordinates calls to stateless services."""

import asyncio
from typing import Dict, Any, Optional
from ..core.types import Task, TaskStatus, OrchestrationResult
from ..core.config import OrchestrationConfig
from .state_manager import StateManager
from .transition_manager import TransitionManager


class ServiceOrchestrator:
    """Main orchestrator that coordinates stateless service calls.

    This class owns the orchestration logic and controls how and when
    stateless services are called. It uses the transition manager to
    ensure only valid state changes occur.
    """

    def __init__(self, state_manager: StateManager, transition_manager: TransitionManager,
                 task_validator, task_processor, task_persistence):
        self.state_manager = state_manager
        self.transition_manager = transition_manager

        # Stateless service dependencies (injected)
        self.task_validator = task_validator
        self.task_processor = task_processor
        self.task_persistence = task_persistence

    async def process_task(self, task_id: str) -> OrchestrationResult:
        """Main orchestration method - process a task through its lifecycle."""
        try:
            # Step 1: Validate the task
            task = self.state_manager.get_task(task_id)
            if not task:
                return OrchestrationResult(False, error=f"Task {task_id} not found")

            validation_result = await self._call_service_with_timeout(
                self.task_validator.validate, task, "validate"
            )

            if not validation_result["valid"]:
                self.transition_manager.attempt_transition(
                    task_id, TaskStatus.FAILED, validation_result["error"]
                )
                return OrchestrationResult(False, task, validation_result["error"])

            # Transition to validated
            if not self.transition_manager.attempt_transition(task_id, TaskStatus.VALIDATED):
                return OrchestrationResult(False, task, "Failed to transition to validated")

            # Step 2: Process the task
            processing_result = await self._call_service_with_timeout(
                self.task_processor.process, task, "process"
            )

            if not processing_result["success"]:
                self.transition_manager.attempt_transition(
                    task_id, TaskStatus.FAILED, processing_result["error"]
                )
                return OrchestrationResult(False, task, processing_result["error"])

            # Transition to processing (in progress)
            if not self.transition_manager.attempt_transition(task_id, TaskStatus.PROCESSING):
                return OrchestrationResult(False, task, "Failed to transition to processing")

            # Step 3: Persist the results
            persist_result = await self._call_service_with_timeout(
                self.task_persistence.persist, task, "persist"
            )

            if not persist_result["success"]:
                self.transition_manager.attempt_transition(
                    task_id, TaskStatus.FAILED, persist_result["error"]
                )
                return OrchestrationResult(False, task, persist_result["error"])

            # Final transition to completed
            if not self.transition_manager.attempt_transition(task_id, TaskStatus.COMPLETED):
                return OrchestrationResult(False, task, "Failed to transition to completed")

            return OrchestrationResult(True, task)

        except Exception as e:
            # Handle unexpected errors
            self.transition_manager.attempt_transition(
                task_id, TaskStatus.FAILED, str(e)
            )
            return OrchestrationResult(False, error=str(e))

    async def _call_service_with_timeout(self, service_method, task: Task,
                                       operation: str) -> Dict[str, Any]:
        """Call a stateless service method with timeout protection."""
        timeout = OrchestrationConfig.SERVICE_TIMEOUTS.get(operation, 5)

        try:
            result = await asyncio.wait_for(
                service_method(task),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            return {"success": False, "error": f"{operation} timed out after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": f"{operation} failed: {str(e)}"}

    def get_task_status(self, task_id: str) -> Optional[Task]:
        """Get current task status."""
        return self.state_manager.get_task(task_id)
