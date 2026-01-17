"""Stateless task persistence service."""

from typing import Dict, Any
from ..core.types import Task


class TaskPersistence:
    """Stateless service for persisting task results.

    In a real system, this would write to a database.
    Here it just simulates persistence operations.
    """

    async def persist(self, task: Task) -> Dict[str, Any]:
        """Persist task results.

        In a real implementation, this would write to a database
        or external storage system.
        """
        try:
            # Simulate database write time
            import asyncio
            await asyncio.sleep(0.1)

            # Validate that task has been processed
            if "processed_at" not in task.data:
                return {
                    "success": False,
                    "error": "Task has not been processed yet"
                }

            if "result" not in task.data:
                return {
                    "success": False,
                    "error": "Task has no processing result"
                }

            # In a real system, this would be a database INSERT/UPDATE
            # For this example, we just mark it as persisted
            task.data["persisted_at"] = "2024-01-01T00:00:00Z"
            task.data["persistence_status"] = "saved"

            return {"success": True}

        except Exception as e:
            return {
                "success": False,
                "error": f"Persistence failed: {str(e)}"
            }
