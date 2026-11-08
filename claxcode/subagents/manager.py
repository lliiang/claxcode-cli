"""In-process registry for cancellable subagent tasks."""

import asyncio
from contextlib import suppress
from typing import Any
from uuid import UUID

_running_tasks: dict[UUID, asyncio.Task[Any]] = {}


def track_subagent(task_id: UUID, task: asyncio.Task[Any]) -> None:
    """Track a running task and remove it automatically when it finishes."""
    _running_tasks[task_id] = task
    task.add_done_callback(lambda _: _running_tasks.pop(task_id, None))


async def cancel_subagent_task(task_id: UUID) -> bool:
    """Cancel a task owned by this process and wait for its cleanup."""
    task = _running_tasks.get(task_id)
    if task is None or task.done():
        return False
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    return True


def running_subagent_ids() -> set[UUID]:
    return {task_id for task_id, task in _running_tasks.items() if not task.done()}
