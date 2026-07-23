"""Memory tool — lets the agent record durable facts and preferences."""

from typing import Any

from claxcode.memory.auto_memory import auto_memory
from claxcode.tools.base import Tool
from claxcode.tools.registry import tool


@tool
class RememberFactTool(Tool):
    name = "remember_fact"
    description = (
        "记录一条用户偏好或重要事实到自动记忆（键值对），"
        "以后的会话会自动加载。例如用户偏好的语言、代码风格、常用命令等。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "事实名称，如 '回复语言'"},
            "value": {"type": "string", "description": "事实内容，如 '始终使用中文'"},
        },
        "required": ["key", "value"],
    }
    category = "memory"
    required_permissions = ["write"]

    async def execute(self, key: str, value: str, **kwargs: Any) -> str:
        return auto_memory.remember(key, value)
