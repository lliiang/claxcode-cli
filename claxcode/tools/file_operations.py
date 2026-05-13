"""File operation tools."""

from pathlib import Path
from typing import Any

from claxcode.tools.base import Tool
from claxcode.tools.registry import tool


@tool
class ReadFile(Tool):
    name = "read_file"
    description = "读取文本文件的内容。"
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
            return f"错误：文件不存在: {path}"
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"错误：文件可能是二进制文件: {path}"


@tool
class WriteFile(Tool):
    name = "write_file"
    description = "将内容写入文件（覆盖或创建）。"
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
        return f"文件已写入: {path}"


@tool
class StrReplaceFile(Tool):
    name = "str_replace_file"
    description = "替换文件中的指定字符串。"
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
            return f"错误：文件不存在: {path}"
        text = target.read_text(encoding="utf-8")
        if old not in text:
            return f"错误：在 {path} 中未找到要替换的字符串"
        if replace_all:
            text = text.replace(old, new)
            count = text.count(new) - target.read_text(encoding="utf-8").count(new) + 1
        else:
            text = text.replace(old, new, 1)
            count = 1
        target.write_text(text, encoding="utf-8")
        return f"已在 {path} 中替换 {count} 处"


@tool
class CreateDirectory(Tool):
    name = "create_directory"
    description = "创建目录及必要的父目录。"
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
        return f"目录已创建: {path}"


@tool
class RenameFile(Tool):
    name = "rename_file"
    description = "重命名或移动文件/目录。"
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
            return f"错误：源文件不存在: {old_path}"
        source.rename(dest)
        return f"已重命名 {old_path} -> {new_path}"
