"""File operation tools."""

from pathlib import Path
from typing import Any

from claxcode.tools.base import Tool
from claxcode.tools.registry import tool


@tool
class ReadFile(Tool):
    name = "read_file"
    description = "Read the contents of a text file."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
        },
        "required": ["path"],
    }
    category = "file_operations"
    required_permissions = ["read"]

    async def execute(self, path: str, **kwargs: Any) -> str:
        target = Path(path)
        if not target.exists():
            return f"Error: File not found: {path}"
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"Error: File appears to be binary: {path}"


@tool
class WriteFile(Tool):
    name = "write_file"
    description = "Write content to a file (overwrite or create)."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }
    category = "file_operations"
    required_permissions = ["write"]

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"File written: {path}"


@tool
class StrReplaceFile(Tool):
    name = "str_replace_file"
    description = "Replace an exact string within a file."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old": {"type": "string"},
            "new": {"type": "string"},
            "replace_all": {"type": "boolean", "default": False},
        },
        "required": ["path", "old", "new"],
    }
    category = "file_operations"
    required_permissions = ["write"]

    async def execute(self, path: str, old: str, new: str, replace_all: bool = False, **kwargs: Any) -> str:
        target = Path(path)
        if not target.exists():
            return f"Error: File not found: {path}"
        text = target.read_text(encoding="utf-8")
        if old not in text:
            return f"Error: Old string not found in {path}"
        if replace_all:
            text = text.replace(old, new)
            count = text.count(new) - target.read_text(encoding="utf-8").count(new) + 1
        else:
            text = text.replace(old, new, 1)
            count = 1
        target.write_text(text, encoding="utf-8")
        return f"Replaced {count} occurrence(s) in {path}"


@tool
class CreateDirectory(Tool):
    name = "create_directory"
    description = "Create a directory and any necessary parent directories."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
        "required": ["path"],
    }
    category = "file_operations"
    required_permissions = ["write"]

    async def execute(self, path: str, **kwargs: Any) -> str:
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        return f"Directory created: {path}"


@tool
class RenameFile(Tool):
    name = "rename_file"
    description = "Rename or move a file or directory."
    input_schema = {
        "type": "object",
        "properties": {
            "old_path": {"type": "string"},
            "new_path": {"type": "string"},
        },
        "required": ["old_path", "new_path"],
    }
    category = "file_operations"
    required_permissions = ["write"]

    async def execute(self, old_path: str, new_path: str, **kwargs: Any) -> str:
        source = Path(old_path)
        dest = Path(new_path)
        if not source.exists():
            return f"Error: Source not found: {old_path}"
        source.rename(dest)
        return f"Renamed {old_path} -> {new_path}"
