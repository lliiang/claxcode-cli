"""Subagent management API."""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from claxcode.memory.session_store import (
    create_subagent_task,
    finish_subagent_task,
    get_subagent_task,
)
from claxcode.models.subagent import SubagentStatus, SubagentTask
from claxcode.subagents.executor import ExecutorSubagent
from claxcode.subagents.explore import ExploreSubagent
from claxcode.subagents.manager import cancel_subagent_task, track_subagent
from claxcode.subagents.planner import PlannerSubagent

router = APIRouter()


def _spawn_subagent(session_id: UUID, agent_type: str, instruction: str):
    if agent_type == "explore":
        return ExploreSubagent(session_id, instruction)
    if agent_type == "planner":
        return PlannerSubagent(session_id, instruction)
    if agent_type == "executor":
        return ExecutorSubagent(session_id, instruction)
    raise ValueError(f"未知的代理类型: {agent_type}")


@router.post("", response_model=SubagentTask)
async def spawn_subagent(
    session_id: UUID,
    instruction: str,
    agent_type: str = "explore",
):
    task = SubagentTask(
        session_id=session_id,
        agent_type=agent_type,
        instruction=instruction,
        status=SubagentStatus.RUNNING,
    )
    await create_subagent_task(task)

    async def run_task():
        results = []
        try:
            agent = _spawn_subagent(session_id, agent_type, instruction)
            async for event in agent.run():
                if event.get("type") == "result":
                    results.append(event.get("content", ""))
            await finish_subagent_task(task.id, SubagentStatus.COMPLETED, "\n".join(results))
        except asyncio.CancelledError:
            results.append("任务已由用户取消")
            await finish_subagent_task(task.id, SubagentStatus.CANCELLED, "\n".join(results))
        except Exception as exc:
            await finish_subagent_task(task.id, SubagentStatus.FAILED, str(exc))

    track_subagent(task.id, asyncio.create_task(run_task()))
    return task


@router.get("/{task_id}", response_model=SubagentTask)
async def get_subagent(task_id: UUID):
    task = await get_subagent_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="子代理任务不存在")
    return task


@router.post("/{task_id}/cancel", response_model=SubagentTask)
async def cancel_subagent(task_id: UUID):
    task = await get_subagent_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="子代理任务不存在")
    if task.status == SubagentStatus.RUNNING:
        cancelled = await cancel_subagent_task(task_id)
        if not cancelled:
            await finish_subagent_task(task_id, SubagentStatus.CANCELLED, "任务已取消")
    return await get_subagent_task(task_id) or task


@router.post("/{task_id}/stream")
async def stream_subagent(task_id: UUID):
    task = await get_subagent_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="子代理任务不存在")

    async def event_stream():
        agent = _spawn_subagent(task.session_id, task.agent_type, task.instruction)
        async for event in agent.run():
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
