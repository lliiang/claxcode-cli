"""Code intelligence tools (stubs for Phase 2)."""

import re
from typing import Any

from claxcode.tools.base import Tool
from claxcode.tools.registry import tool


@tool
class TypeCheck(Tool):
    name = "type_check"
    description = "Run a type checker (mypy) on the project or a file."
    input_schema = {
        "type": "object",
        "properties": {
            "target": {"type": "string", "default": "."},
        },
        "required": [],
    }
    category = "code_intelligence"
    required_permissions = ["execute"]

    async def execute(self, target: str = ".", **kwargs: Any) -> str:
        from claxcode.tools.execution import RunShell
        return await RunShell().execute(command=f"mypy {target}")


@tool
class FindDefinition(Tool):
    name = "find_definition"
    description = "Find the definition of a symbol in the codebase (basic text search)."
    input_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "directory": {"type": "string", "default": "."},
        },
        "required": ["symbol"],
    }
    category = "code_intelligence"
    required_permissions = ["read"]

    async def execute(self, symbol: str, directory: str = ".", **kwargs: Any) -> str:
        from claxcode.tools.search import GrepSearch
        pattern = rf"(class|def|async def)\s+{re.escape(symbol)}\b"
        return await GrepSearch().execute(pattern=pattern, directory=directory, output_mode="content")


@tool
class FindReferences(Tool):
    name = "find_references"
    description = "Find references to a symbol in the codebase."
    input_schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "directory": {"type": "string", "default": "."},
        },
        "required": ["symbol"],
    }
    category = "code_intelligence"
    required_permissions = ["read"]

    async def execute(self, symbol: str, directory: str = ".", **kwargs: Any) -> str:
        from claxcode.tools.search import GrepSearch
        pattern = rf"\b{re.escape(symbol)}\b"
        return await GrepSearch().execute(pattern=pattern, directory=directory, output_mode="content")
