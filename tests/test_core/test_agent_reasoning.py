"""Tests for preserving reasoning content across tool-call rounds."""

from uuid import uuid4

from claxcode.core.agent import Agent


async def test_reasoning_content_is_sent_back_after_tool_call(tmp_path, monkeypatch):
    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def stream_chat(self, messages, tools=None):
            self.calls.append(messages)
            if len(self.calls) == 1:
                yield {"type": "reasoning_delta", "content": "先检查当前目录"}
                yield {
                    "type": "tool_call",
                    "id": "call-1",
                    "name": "run_shell",
                    "arguments": {"command": "pwd"},
                }
            else:
                yield "检查完成"

    async def no_memories(message):
        return None

    async def fake_execute(name, args):
        return "ok"

    agent = Agent(session_id=uuid4(), project_path=str(tmp_path))
    provider = FakeProvider()
    agent.provider = provider
    monkeypatch.setattr(agent, "_load_memories", no_memories)
    monkeypatch.setattr(agent, "_execute_tool", fake_execute)

    events = [event async for event in agent.run("检查服务器")]

    assistant = next(
        message for message in agent.context.messages if message.get("tool_calls")
    )
    assert assistant["reasoning_content"] == "先检查当前目录"
    assert assistant["tool_calls"][0]["function"]["arguments"] == '{"command": "pwd"}'
    second_request = provider.calls[1]
    assert any(
        message.get("reasoning_content") == "先检查当前目录"
        for message in second_request
    )
    assert events[-1]["type"] == "done"
