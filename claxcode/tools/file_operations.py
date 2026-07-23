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
class ViewFile(Tool):
    name = "view_file"
    description = "查看文件内容，带行号，支持分页。"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "view_range": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 2,
                "maxItems": 2,
                "description": "查看范围 [起始行, 结束行]，1-based",
            },
            "max_lines": {"type": "integer", "default": 50, "description": "默认最大显示行数"},
        },
        "required": ["path"],
    }
    category = "file_operations"
    required_permissions = ["read"]

    async def execute(self, path: str, view_range: list[int] | None = None, max_lines: int = 50, **kwargs: Any) -> str:
        target = Path(path)
        if not target.exists():
            return f"错误：文件不存在: {path}"
        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"错误：文件可能是二进制文件: {path}"

        lines = text.splitlines()
        total = len(lines)

        start = 0
        end = total

        if view_range is not None:
            start = max(0, view_range[0] - 1)
            end = min(total, view_range[1])
        elif total > max_lines:
            end = max_lines

        width = len(str(total))
        output_lines = []
        for i in range(start, end):
            output_lines.append(f"{i + 1:>{width}} | {lines[i]}")

        result = "\n".join(output_lines)

        if end < total:
            result += f"\n\n... （共 {total} 行，显示 {start + 1}-{end} 行。使用 view_range 查看更多）"

        return result


@tool
class EditFile(Tool):
    name = "edit_file"
    description = "精确编辑文件：使用 old_string / new_string 块进行多行替换，自动验证匹配唯一性。"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "edits": {
                "type": "array",
                "description": "编辑块列表，每个块包含 old_string 和 new_string",
                "items": {
                    "type": "object",
                    "properties": {
                        "old_string": {"type": "string", "description": "要替换的精确内容（多行）"},
                        "new_string": {"type": "string", "description": "替换后的内容"},
                    },
                    "required": ["old_string", "new_string"],
                },
            },
        },
        "required": ["path", "edits"],
    }
    category = "file_operations"
    required_permissions = ["write"]

    async def execute(self, path: str, edits: list[dict], **kwargs: Any) -> str:
        target = Path(path)
        if not target.exists():
            return f"错误：文件不存在: {path}"
        text = target.read_text(encoding="utf-8")

        # 先验证所有编辑块，收集位置信息
        edit_infos = []
        for idx, edit in enumerate(edits):
            old = edit["old_string"]
            new = edit["new_string"]
            count = text.count(old)

            if count == 0:
                # 返回文件前 50 行上下文帮助定位
                lines = text.splitlines()
                context_lines = lines[:50]
                width = len(str(len(lines))) if lines else 1
                ctx = "\n".join(f"{i + 1:>{width}} | {line}" for i, line in enumerate(context_lines))
                return f"错误：第 {idx + 1} 个编辑块的 old_string 在文件中未找到。\n\n文件前 {len(context_lines)} 行上下文：\n{ctx}\n\n提示：请核对 old_string 是否完全匹配（包括缩进和换行）。"

            if count > 1:
                # 收集所有匹配位置
                matches = []
                start = 0
                while True:
                    pos = text.find(old, start)
                    if pos == -1:
                        break
                    # 计算行号
                    line_start = text[:pos].count("\n") + 1
                    line_end = line_start + old.count("\n")
                    matches.append((line_start, line_end))
                    start = pos + 1
                match_lines = "\n".join(f"   - 第 {s}-{e} 行" for s, e in matches)
                return f"错误：第 {idx + 1} 个编辑块的 old_string 在文件中匹配到 {count} 处：\n{match_lines}\n提示：请增加更多上下文使匹配唯一。"

            # 记录位置（用于从后往前排序）
            pos = text.find(old)
            edit_infos.append({"idx": idx, "old": old, "new": new, "pos": pos})

        # 从后往前执行替换（避免位置偏移）
        edit_infos.sort(key=lambda x: x["pos"], reverse=True)
        applied = []
        for info in edit_infos:
            old = info["old"]
            new = info["new"]
            pos = text.find(old)
            line_start = text[:pos].count("\n") + 1
            line_end = line_start + old.count("\n")
            new_line_end = line_start + new.count("\n")
            text = text[:pos] + new + text[pos + len(old):]
            applied.append((info["idx"] + 1, line_start, line_end, new_line_end))

        target.write_text(text, encoding="utf-8")

        # 按原始顺序输出结果
        applied.sort(key=lambda x: x[0])
        lines = [f"✅ 已编辑: {path}"]
        for block_num, s, e, ne in applied:
            if s == e and s == ne:
                lines.append(f"   块 {block_num}: 第 {s} 行")
            elif s == e:
                lines.append(f"   块 {block_num}: 第 {s} 行 → 第 {s}-{ne} 行")
            else:
                lines.append(f"   块 {block_num}: 第 {s}-{e} 行 → 第 {s}-{ne} 行")
        return "\n".join(lines)


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
