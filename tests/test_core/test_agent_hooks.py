"""Tests for hook enforcement in the agent loop."""

import json
import sys
from uuid import uuid4

import pytest

from claxcode.core.agent import Agent
from claxcode.tools.base import Tool
from claxcode.tools.registry import registry


class HookedWriteTool(Tool):
    name = "_hook_test_write"
    description = "test-only write tool"
    input_schema = {"type": "object", "properties": {}}
    required_permissions = ["write"]

    async def execute(self, **kwargs) -> str:
        return "written"


@pytest.fixture(autouse=True)
def _register_tool():
    registry.register(HookedWriteTool())
    yield
    registry.unregister("_hook_test_write")


def _agent_with_hooks(tmp_path, config):
    hook_dir = tmp_path / ".claxcode"
    hook_dir.mkdir(parents=True, exist_ok=True)
    (hook_dir / "hooks.json").write_text(json.dumps(config), encoding="utf-8")
    return Agent(session_id=uuid4(), project_path=str(tmp_path), permission_mode="yolo")


async def test_pre_hook_blocks_tool(tmp_path):
    cmd = f'"{sys.executable}" -c "import sys; sys.exit(1)"'
    agent = _agent_with_hooks(tmp_path, {"PreToolUse": [{"match": "_hook_test", "command": cmd}]})

    result = await agent._execute_tool("_hook_test_write", {})

    assert "钩子阻止" in result


async def test_post_hook_appends_output(tmp_path):
    cmd = f'"{sys.executable}" -c "print(\'post-ok\')"'
    agent = _agent_with_hooks(tmp_path, {"PostToolUse": [{"match": "", "command": cmd}]})

    result = await agent._execute_tool("_hook_test_write", {})

    assert "written" in result
    assert "post-ok" in result


async def test_no_hooks_config_runs_normally(tmp_path):
    agent = Agent(session_id=uuid4(), project_path=str(tmp_path), permission_mode="yolo")
    assert await agent._execute_tool("_hook_test_write", {}) == "written"
