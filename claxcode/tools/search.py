"""Search tools."""

import fnmatch
import re
from pathlib import Path
from typing import Any

from claxcode.tools.base import Tool
from claxcode.tools.registry import tool


@tool
class GlobSearch(Tool):
    name = "glob_search"
    description = "Find files matching a glob pattern recursively."
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
        for p in root.rglob("*"):
            if p.is_file() and fnmatch.fnmatch(str(p.relative_to(root)), pattern):
                matches.append(str(p.relative_to(root)))
        if not matches:
            return "No files found."
        return "\n".join(matches)


@tool
class GrepSearch(Tool):
    name = "grep_search"
    description = "Search file contents using a regex pattern."
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
        for p in root.rglob(glob):
            if not p.is_file():
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            if regex.search(text):
                if output_mode == "files_with_matches":
                    results.append(str(p.relative_to(root)))
                else:
                    for i, line in enumerate(text.splitlines(), 1):
                        if regex.search(line):
                            results.append(f"{p.relative_to(root)}:{i}:{line}")
        if not results:
            return "No matches found."
        return "\n".join(results[:250])


@tool
class ExploreCodebase(Tool):
    name = "explore_codebase"
    description = "High-level exploration: list top-level files and summarize structure."
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
            for p in sorted(current.iterdir()):
                if p.name.startswith(".") and p.name not in {".gitignore", ".env"}:
                    continue
                lines.append(f"{prefix}{p.name}{'/' if p.is_dir() else ''}")
                if p.is_dir():
                    walk(p, current_depth + 1)

        if root.exists():
            walk(root, 0)
        return "\n".join(lines) if lines else "Empty directory."
