"""Demo script to demonstrate orchestration architecture."""

import asyncio
import json
from typing import Dict, Any
from ..orchestrator import Orchestrator


async def demo():
    """Demo the orchestration without running a full server."""
    orchestrator = Orchestrator()

    print("=== Orchestration Architecture Demo ===\n")

    # Create a task
    print("1. Creating task...")
    result = orchestrator.create_task("demo-task", {
        "name": "Demo Task",
        "priority": 3,
        "description": "A demonstration task"
    })
    print(f"   Result: {result}\n")

    # Process the task
    print("2. Processing task through orchestration pipeline...")
    result = await orchestrator.process_task("demo-task")
    print(f"   Success: {result.success}")
    if result.task:
        print(f"   Final status: {result.task.status.value}")
        print(f"   Task data: {result.task.data}")
    if result.error:
        print(f"   Error: {result.error}")
    print()

    # Show all tasks
    print("3. All tasks in system:")
    tasks = orchestrator.get_all_tasks()
    for task_id, task_data in tasks.items():
        print(f"   {task_id}: {task_data['status']} - {task_data['data']}")


if __name__ == "__main__":
    asyncio.run(demo())
