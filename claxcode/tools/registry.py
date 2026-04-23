"""Tool registry with decorator-based registration."""

from typing import Any

from claxcode.tools.base import Tool


class ToolRegistry:
    """Central registry for tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def list_by_category(self, category: str) -> list[Tool]:
        return [t for t in self._tools.values() if t.category == category]


registry = ToolRegistry()


def tool(cls: type[Tool]) -> type[Tool]:
    """Decorator to auto-register a Tool subclass."""
    instance = cls()
    registry.register(instance)
    return cls
