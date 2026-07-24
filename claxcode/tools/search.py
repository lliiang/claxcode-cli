"""Search tools."""

import fnmatch
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from claxcode.tools.base import Tool
from claxcode.tools.registry import tool

# 依赖/缓存目录：搜索时跳过，避免扫入海量无关文件
IGNORED_DIRS = {
    ".git", ".hg", ".svn",
    ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", ".tox", ".eggs",
    ".claxcode", ".idea", "dist", "build",
}


def _iter_files(root: Path) -> Iterator[Path]:
    """Recursively yield files under root, pruning dependency/cache dirs."""
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for p in entries:
            if p.is_dir():
                if p.name not in IGNORED_DIRS:
                    stack.append(p)
            elif p.is_file():
                yield p


@tool
class GlobSearch(Tool):
    name = "glob_search"
    description = "递归查找匹配 glob 模式的文件（自动跳过 .git/.venv/node_modules 等目录）。"
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern, e.g., src/**/*.py"},
            "directory": {"type": "string", "default": "."},
        },
        "required": ["pattern"],
    }
    category = "search"
    required_permissions = ["read"]

    async def execute(self, pattern: str, directory: str = ".", **kwargs: Any) -> str:
        root = Path(directory)
        matches = []
        for p in _iter_files(root):
            rel = str(p.relative_to(root))
            if fnmatch.fnmatch(rel, pattern):
                matches.append(rel)
        if not matches:
            return "未找到文件。"
        note = f"\n... [已截断，共 {len(matches)} 个]" if len(matches) > 200 else ""
        return "\n".join(matches[:200]) + note


@tool
class GrepSearch(Tool):
    name = "grep_search"
    description = "使用正则表达式搜索文件内容（自动跳过 .git/.venv/node_modules 等目录）。"
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "directory": {"type": "string", "default": "."},
            "glob": {"type": "string", "default": "*"},
            "output_mode": {
                "type": "string",
                "enum": ["content", "files_with_matches"],
                "default": "content",
            },
        },
        "required": ["pattern"],
    }
    category = "search"
    required_permissions = ["read"]

    async def execute(
        self,
        pattern: str,
        directory: str = ".",
        glob: str = "*",
        output_mode: str = "content",
        **kwargs: Any,
    ) -> str:
        root = Path(directory)
        regex = re.compile(pattern)
        results = []
        for p in _iter_files(root):
            if not fnmatch.fnmatch(p.name, glob):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            if not regex.search(text):
                continue
            if output_mode == "files_with_matches":
                results.append(str(p.relative_to(root)))
            else:
                for i, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        results.append(f"{p.relative_to(root)}:{i}:{line}")
        if not results:
            return "未找到匹配项。"
        note = f"\n... [已截断，共 {len(results)} 条]" if len(results) > 250 else ""
        return "\n".join(results[:250]) + note


@tool
class ExploreCodebase(Tool):
    name = "explore_codebase"
    description = "高级探索：列出顶层文件并总结结构。"
    input_schema = {
        "type": "object",
        "properties": {
            "directory": {"type": "string", "default": "."},
            "depth": {"type": "integer", "default": 2},
        },
        "required": [],
    }
    category = "search"
    required_permissions = ["read"]

    async def execute(self, directory: str = ".", depth: int = 2, **kwargs: Any) -> str:
        root = Path(directory)
        lines = []

        def walk(current: Path, current_depth: int):
            if current_depth > depth:
                return
            prefix = "  " * current_depth
            try:
                entries = sorted(current.iterdir())
            except OSError:
                return
            for p in entries:
                if p.name in IGNORED_DIRS:
                    continue
                if p.name.startswith(".") and p.name not in {".gitignore", ".env"}:
                    continue
                lines.append(f"{prefix}{p.name}{'/' if p.is_dir() else ''}")
                if p.is_dir():
                    walk(p, current_depth + 1)

        if root.exists():
            walk(root, 0)
        return "\n".join(lines) if lines else "空目录。"
