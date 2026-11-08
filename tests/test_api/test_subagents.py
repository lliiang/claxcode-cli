"""Tests for cooperative subagent cancellation."""

import asyncio
from uuid import uuid4

from claxcode.models.subagent import SubagentStatus


async def test_cancel_running_subagent(client, monkeypatch):
    class BlockingAgent:
        async def run(self):
            yield {"type": "status", "status": "running"}
            await asyncio.sleep(60)
            yield {"type": "result", "content": "不应到达"}

    monkeypatch.setattr(
        "claxcode.api.subagents._spawn_subagent", lambda *args: BlockingAgent()
    )
    session_id = uuid4()
    response = await client.post(
        f"/subagents?session_id={session_id}&instruction=test&agent_type=explore"
    )
    assert response.status_code == 200
    task_id = response.json()["id"]
    await asyncio.sleep(0)

    response = await client.post(f"/subagents/{task_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == SubagentStatus.CANCELLED.value
    assert "用户取消" in response.json()["result"]
