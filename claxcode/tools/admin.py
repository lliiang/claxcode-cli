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
        "Register a new tool dynamically. "
        "Provide the tool name, description, JSON input schema, and the execute() method body as a string. "
        "The code runs in a restricted environment with only basic builtins."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Unique tool identifier"},
            "description": {"type": "string", "description": "What the tool does"},
            "category": {"type": "string", "default": "custom"},
            "required_permissions": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
            },
            "input_schema": {
                "type": "object",
                "description": "JSON Schema for the tool's arguments",
            },
            "code": {
                "type": "string",
                "description": (
                    "Python source code for the execute() method body. "
                    "Use 'self' and standard library only. Return a string."
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
            return f"Error: Tool '{name}' already exists."

        # Sanitize name
        if not name.replace("_", "").isalnum():
            return "Error: Tool name must be alphanumeric or underscores only."

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
            return f"Error in {repr(name)}: {{_exc}}"
"""

        # Restricted execution environment
        allowed_builtins = {
            "__build_class__": __build_class__,
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
            return f"Error compiling tool: {exc}\n\nGenerated source:\n{class_source}"

        tool_cls = namespace.get(class_name)
        if tool_cls is None or not isinstance(tool_cls, type) or not issubclass(tool_cls, Tool):
            return "Error: Compiled class is not a valid Tool subclass."

        instance = tool_cls()
        registry.register(instance)
        return f"✅ Tool '{name}' registered successfully in category '{category}'."
