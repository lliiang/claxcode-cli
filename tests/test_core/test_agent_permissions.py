"""Tests for Agent permission enforcement and context compression."""

from uuid import uuid4

import pytest

from claxcode.core.agent import Agent
from claxcode.security.audit import AuditLogger
from claxcode.tools.base import Tool
from claxcode.tools.registry import registry


class DummyWriteTool(Tool):
    name = "_test_write_tool"
    description = "test-only write tool"
    input_schema = {"type": "object", "properties": {}}
    required_permissions = ["write"]

    async def execute(self, **kwargs) -> str:
        return "written"


class DummyReadTool(Tool):
    name = "_test_read_tool"
    description = "test-only read tool"
    input_schema = {"type": "object", "properties": {}}
    required_permissions = ["read"]

    async def execute(self, **kwargs) -> str:
        return "read"


class DummyExecTool(Tool):
    name = "_test_exec_tool"
    description = "test-only exec tool"
    input_schema = {"type": "object", "properties": {}}
    required_permissions = ["execute"]

    async def execute(self, **kwargs) -> str:
        return "executed"


@pytest.fixture(autouse=True)
def _register_tools():
    for cls in (DummyWriteTool, DummyReadTool, DummyExecTool):
        registry.register(cls())
    yield
    for name in ("_test_write_tool", "_test_read_tool", "_test_exec_tool"):
        registry.unregister(name)


def _make_agent(mode: str, **kwargs) -> Agent:
    return Agent(session_id=uuid4(), project_path=".", permission_mode=mode, **kwargs)


async def test_plan_mode_blocks_write_tool():
    agent = _make_agent("plan")
    result = await agent._execute_tool("_test_write_tool", {})
    assert "权限阻止" in result


async def test_plan_mode_allows_read_tool():
    agent = _make_agent("plan")
    assert await agent._execute_tool("_test_read_tool", {}) == "read"


async def test_auto_safe_blocks_execute_tool():
    agent = _make_agent("auto_safe")
    result = await agent._execute_tool("_test_exec_tool", {})
    assert "权限阻止" in result


async def test_auto_safe_allows_write_tool():
    agent = _make_agent("auto_safe")
    assert await agent._execute_tool("_test_write_tool", {}) == "written"


async def test_ask_mode_without_callback_blocks_write():
    agent = _make_agent("ask")
    result = await agent._execute_tool("_test_write_tool", {})
    assert "需要批准" in result


async def test_ask_mode_allows_read_without_callback():
    agent = _make_agent("ask")
    assert await agent._execute_tool("_test_read_tool", {}) == "read"


async def test_ask_mode_approval_callback_allows():
    async def approve(name, args):
        return True

    agent = _make_agent("ask", approval_callback=approve)
    assert await agent._execute_tool("_test_write_tool", {}) == "written"


async def test_ask_mode_approval_callback_denies():
    async def deny(name, args):
        return False

    agent = _make_agent("ask", approval_callback=deny)
    result = await agent._execute_tool("_test_write_tool", {})
    assert "用户拒绝了执行" in result


async def test_yolo_allows_everything():
    agent = _make_agent("yolo")
    assert await agent._execute_tool("_test_exec_tool", {}) == "executed"


async def test_unknown_permission_mode_falls_back_to_ask():
    agent = _make_agent("not_a_mode")
    result = await agent._execute_tool("_test_write_tool", {})
    assert "需要批准" in result


async def test_audit_trail_records_blocked_call(tmp_path, monkeypatch):
    logger = AuditLogger(log_path=tmp_path / "audit.jsonl")
    monkeypatch.setattr("claxcode.core.agent.audit_logger", logger)

    agent = _make_agent("plan")
    await agent._execute_tool("_test_write_tool", {})

    entries = logger.read_recent()
    assert len(entries) == 1
    assert entries[0]["allowed"] is False
    assert entries[0]["tool_name"] == "_test_write_tool"


async def test_audit_trail_records_allowed_call(tmp_path, monkeypatch):
    logger = AuditLogger(log_path=tmp_path / "audit.jsonl")
    monkeypatch.setattr("claxcode.core.agent.audit_logger", logger)

    agent = _make_agent("yolo")
    await agent._execute_tool("_test_read_tool", {})

    entries = logger.read_recent()
    assert len(entries) == 1
    assert entries[0]["allowed"] is True


class _StubProvider:
    async def stream_chat(self, messages, tools):
        yield "摘要内容"


async def test_compress_context_inserts_llm_summary(monkeypatch):
    agent = _make_agent("yolo")
    agent.provider = _StubProvider()
    for i in range(8):
        agent.context.add_message("user", f"message {i}")
    monkeypatch.setattr(agent.context, "over_threshold", lambda: True)

    assert await agent._compress_context_if_needed() is True
    assert "[早期对话摘要]" in agent.context.messages[1]["content"]
    assert "摘要内容" in agent.context.messages[1]["content"]


async def test_compress_context_skipped_under_threshold():
    agent = _make_agent("yolo")
    agent.context.add_message("user", "short")
    assert await agent._compress_context_if_needed() is False


def test_default_system_prompt_has_methodology():
    from claxcode.core.agent import DEFAULT_SYSTEM_PROMPT

    assert "工作原则" in DEFAULT_SYSTEM_PROMPT
    assert "最小改动" in DEFAULT_SYSTEM_PROMPT
    assert "诚实汇报" in DEFAULT_SYSTEM_PROMPT
