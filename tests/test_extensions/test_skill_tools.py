"""Tests for skill-level tool registration and unload."""

import tempfile
from pathlib import Path

import pytest

from claxcode.extensions.skills import SkillManager
from claxcode.tools.registry import registry


@pytest.fixture
def skill_with_tools():
    with tempfile.TemporaryDirectory() as tmp:
        skill_path = Path(tmp) / "math-helpers"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text(
            """# Math Helpers

## Description
Basic math utilities.

## Instructions
Use these tools for arithmetic.
""",
            encoding="utf-8",
        )
        (skill_path / "tools.py").write_text(
            '''from claxcode.tools.base import Tool
from claxcode.tools.registry import tool

@tool
class AddTool(Tool):
    name = "skill_add"
    description = "Add two numbers."
    input_schema = {
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"],
    }
    category = "math"
    required_permissions = []

    async def execute(self, a: float, b: float, **kwargs) -> str:
        return str(a + b)
''',
            encoding="utf-8",
        )
        yield Path(tmp)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Remove skill tools after each test."""
    yield
    registry.unregister("skill_add")


def test_skill_loads_tools(skill_with_tools):
    mgr = SkillManager()
    mgr.load_skill_dir(skill_with_tools)
    assert len(mgr.skills) == 1
    skill = mgr.skills[0]
    assert skill.name == "Math Helpers"
    assert "skill_add" in skill.registered_tools
    # Verify tool is usable
    tool = registry.get("skill_add")
    assert tool is not None
    assert tool.name == "skill_add"


@pytest.mark.asyncio
async def test_skill_tool_execution(skill_with_tools):
    mgr = SkillManager()
    mgr.load_skill_dir(skill_with_tools)
    tool = registry.get("skill_add")
    result = await tool.execute(a=2, b=3)
    assert result == "5"


def test_unload_skill_removes_tools(skill_with_tools):
    mgr = SkillManager()
    mgr.load_skill_dir(skill_with_tools)
    assert registry.get("skill_add") is not None
    mgr.unload_skill("Math Helpers")
    assert registry.get("skill_add") is None
    assert len(mgr.skills) == 0


def test_reload_all(skill_with_tools):
    mgr = SkillManager()
    mgr.load_skill_dir(skill_with_tools)
    assert len(mgr.skills) == 1
    # Unload manually
    mgr.unload_skill("Math Helpers")
    assert registry.get("skill_add") is None
    # Reload
    skill_count, tool_count = mgr.reload_all()
    assert skill_count == 1
    assert tool_count == 1
    assert registry.get("skill_add") is not None
