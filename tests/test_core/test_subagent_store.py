"""Tests for subagent task persistence in session_store."""

from uuid import uuid4

from claxcode.memory import init_db
from claxcode.memory.session_store import (
    create_subagent_task,
    finish_subagent_task,
    get_subagent_task,
)
from claxcode.models.subagent import SubagentStatus, SubagentTask


async def test_subagent_task_roundtrip():
    await init_db()
    task = SubagentTask(
        session_id=uuid4(),
        instruction="do something",
        status=SubagentStatus.RUNNING,
    )
    await create_subagent_task(task)

    loaded = await get_subagent_task(task.id)
    assert loaded is not None
    assert loaded.status == SubagentStatus.RUNNING
    assert loaded.instruction == "do something"

    await finish_subagent_task(task.id, SubagentStatus.COMPLETED, "done result")
    loaded = await get_subagent_task(task.id)
    assert loaded.status == SubagentStatus.COMPLETED
    assert loaded.result == "done result"
    assert loaded.completed_at is not None


async def test_get_subagent_task_missing_returns_none():
    await init_db()
    assert await get_subagent_task(uuid4()) is None


async def test_finish_missing_task_is_noop():
    await init_db()
    await finish_subagent_task(uuid4(), SubagentStatus.FAILED, "x")  # should not raise
