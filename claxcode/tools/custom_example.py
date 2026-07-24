"""Example: How to add a custom tool.

To make this tool available, import this module in claxcode/tools/__init__.py:
    from claxcode.tools import custom_example

Or register it at runtime:
    from claxcode.tools.registry import registry
    registry.register(MyTool())
"""

import ast
import math
import operator
from typing import Any

from claxcode.tools.base import Tool
from claxcode.tools.registry import tool

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_FUNC_NAMES = ("sqrt", "sin", "cos", "tan", "log", "log2", "log10", "exp", "floor", "ceil", "fabs")
_FUNCS = {name: getattr(math, name) for name in _FUNC_NAMES}
_CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _safe_eval(expression: str) -> float:
    """Evaluate a math expression by walking the AST (no eval() involved)."""
    return _eval_node(ast.parse(expression, mode="eval").body)


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        return _FUNCS[node.func.id](*[_eval_node(arg) for arg in node.args])
    raise ValueError("仅支持数字、四则运算和常用数学函数")


@tool
class Calculate(Tool):
    """一个简单的计算器工具，作为自定义扩展示例。"""

    name = "calculate"
    description = "安全地计算数学表达式（数字、四则运算、常用数学函数）。"
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
            return str(_safe_eval(expression))
        except Exception as exc:
            return f"计算表达式时出错: {exc}"
