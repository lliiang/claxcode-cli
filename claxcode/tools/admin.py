"""Admin tools for runtime extension."""

import textwrap
from typing import Any

from claxcode.tools.base import Tool
from claxcode.tools.registry import registry, tool


@tool
class AdminAddTool(Tool):
    """Dynamically add a new tool at runtime by providing its Python source."""

    name = "admin_add_tool"
    description = (
        "动态注册新工具。"
        "提供工具名称、描述、JSON 输入模式和 execute() 方法体作为字符串。"
        "代码在受限环境中运行，仅包含基本内置函数。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "唯一的工具标识符"},
            "description": {"type": "string", "description": "工具的功能描述"},
            "category": {"type": "string", "default": "custom"},
            "required_permissions": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
            },
            "input_schema": {
                "type": "object",
                "description": "工具参数的 JSON Schema",
            },
            "code": {
                "type": "string",
                "description": (
                    "execute() 方法体的 Python 源代码。"
                    "仅使用 'self' 和标准库。返回一个字符串。"
                ),
            },
        },
        "required": ["name", "description", "code"],
    }
    category = "admin"
    required_permissions = ["write"]

    async def execute(
        self,
        name: str,
        description: str,
        code: str,
        category: str = "custom",
        required_permissions: list[str] | None = None,
        input_schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        if registry.get(name):
            return f"错误：工具 '{name}' 已存在。"

        # Sanitize name
        if not name.replace("_", "").isalnum():
            return "错误：工具名称只能包含字母数字或下划线。"

        safe_name = "".join(ch if ch.isalnum() else "_" for ch in name)
        class_name = f"Dyn{safe_name.title()}"

        # Build the full class source
        schema = input_schema or {"type": "object", "properties": {}, "required": []}
        perms = required_permissions or []
        perms_repr = repr(perms)
        schema_repr = repr(schema)

        body = textwrap.dedent(code).strip()
        # Indent to 12 spaces so it sits inside the try block (try is at 8 spaces)
        wrapped_code = textwrap.indent(body, "            ")

        class_source = f"""
class {class_name}(Tool):
    name = {repr(name)}
    description = {repr(description)}
    input_schema = {schema_repr}
    category = {repr(category)}
    required_permissions = {perms_repr}

    async def execute(self, **kwargs) -> str:
        try:
{wrapped_code}
        except Exception as _exc:
            return f"{repr(name)} 中出错: {{_exc}}"
"""

        # Restricted execution environment
        allowed_builtins = {
            "__build_class__": __build_class__,
            "Exception": Exception,
            "BaseException": BaseException,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "AttributeError": AttributeError,
            "RuntimeError": RuntimeError,
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sum": sum,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
            "print": print,
            "repr": repr,
            "format": format,
            "isinstance": isinstance,
            "hasattr": hasattr,
            "getattr": getattr,
            "setattr": setattr,
            "open": open,
            "Path": __import__("pathlib").Path,
            "json": __import__("json"),
            "re": __import__("re"),
            "textwrap": __import__("textwrap"),
            "datetime": __import__("datetime"),
            "typing": __import__("typing"),
            "httpx": __import__("httpx"),
            "math": __import__("math"),
            "random": __import__("random"),
            "hashlib": __import__("hashlib"),
            "base64": __import__("base64"),
            "urllib": __import__("urllib"),
        }

        namespace = {
            "__builtins__": allowed_builtins,
            "__name__": "__claxcode_dynamic__",
            "__doc__": None,
            "Tool": Tool,
            "Any": Any,
        }

        try:
            exec(class_source, namespace)  # noqa: S102
        except Exception as exc:
            return f"编译工具时出错: {exc}\n\n生成的源代码:\n{class_source}"

        tool_cls = namespace.get(class_name)
        if tool_cls is None or not isinstance(tool_cls, type) or not issubclass(tool_cls, Tool):
            return "错误：编译的类不是有效的 Tool 子类。"

        instance = tool_cls()
        registry.register(instance)
        return f"✅ 工具 '{name}' 已成功注册到类别 '{category}'。"
