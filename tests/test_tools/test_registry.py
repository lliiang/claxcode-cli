"""Tests for ToolRegistry."""

import pytest

from claxcode.tools.base import Tool
from claxcode.tools.registry import registry


class _DummyTool(Tool):
    name = "dummy_unregister_test"
    description = "A dummy tool for testing unregister."
    input_schema = {"type": "object", "properties": {}, "required": []}
    category = "test"
    required_permissions = []

    async def execute(self, **kwargs) -> str:
        return "ok"


@pytest.fixture(autouse=True)
def _clean_registry():
    """Remove test tool if present."""
    yield
    registry.unregister("dummy_unregister_test")


def test_unregister_removes_tool():
    registry.register(_DummyTool())
    assert registry.get("dummy_unregister_test") is not None
    assert registry.unregister("dummy_unregister_test") is True
    assert registry.get("dummy_unregister_test") is None


def test_unregister_unknown_returns_false():
    assert registry.unregister("nonexistent_tool_xyz") is False
