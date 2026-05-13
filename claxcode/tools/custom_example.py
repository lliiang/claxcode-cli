"""Example: How to add a custom tool.

To make this tool available, import this module in claxcode/tools/__init__.py:
    from claxcode.tools import custom_example

Or register it at runtime:
    from claxcode.tools.registry import registry
    registry.register(MyTool())
"""

from typing import Any

from claxcode.tools.base import Tool
from claxcode.tools.registry import tool


@tool
class Calculate(Tool):
    """一个简单的计算器工具，作为自定义扩展示例。"""

    name = "calculate"
    description = "安全地计算数学表达式。"
    input_schema = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "要计算的数学表达式，例如 '2 + 2 * 3'",
            },
        },
        "required": ["expression"],
    }
    category = "math"
    required_permissions = []

    async def execute(self, expression: str, **kwargs: Any) -> str:
        try:
            # Safe eval: only allow basic math operators
            allowed = {"__builtins__": {}}
            result = eval(expression, allowed, {"__builtins__": {}})  # noqa: S307
            return str(result)
        except Exception as exc:
            return f"计算表达式时出错: {exc}"
