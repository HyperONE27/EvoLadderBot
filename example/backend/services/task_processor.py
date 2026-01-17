"""Stateless task processing service."""

import asyncio
from typing import Dict, Any
from ..core.types import Task


class TaskProcessor:
    """Stateless service for processing tasks.

    Contains no internal state - all operations are pure functions
    that operate on the provided task data.
    """

    async def process(self, task: Task) -> Dict[str, Any]:
        """Process a task based on its priority.

        Higher priority tasks take longer to "process" to simulate
        more complex work.
        """
        try:
            priority = task.data.get("priority", 1)

            # Simulate processing time based on priority
            # Higher priority = more complex processing
            processing_time = priority * 0.5  # 0.5-5 seconds

            await asyncio.sleep(processing_time)

            # Add processing result to task data
            task.data["processed_at"] = "2024-01-01T00:00:00Z"
            task.data["processing_duration"] = processing_time
            task.data["result"] = f"Processed task {task.task_id} with priority {priority}"

            return {"success": True}

        except Exception as e:
            return {
                "success": False,
                "error": f"Processing failed: {str(e)}"
            }
