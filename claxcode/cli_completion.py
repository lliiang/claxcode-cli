"""Input completion for the interactive CLI (@file mentions and /commands).

Built on prompt_toolkit. The file index is rebuilt lazily with a short TTL
so completion stays cheap even on large projects; dependency/cache dirs
(from tools.search.IGNORED_DIRS) are pruned.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from claxcode.tools.search import IGNORED_DIRS

MAX_FILES = 5000
MAX_SUGGESTIONS = 30
CACHE_TTL = 30.0

UNSUPPORTED_FILE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
COMMAND_ARGUMENTS = {
    "/mode": [
        ("ask", "写操作和执行命令前逐项确认"),
        ("auto_edit", "自动允许全部工具"),
        ("plan", "只读规划，阻止写操作和命令执行"),
        ("auto_safe", "允许读写，阻止命令执行"),
        ("yolo", "不做任何限制，谨慎使用"),
    ],
    "/skills": [
        ("list", "列出已加载技能"),
        ("reload", "重新加载技能"),
        ("create", "创建项目技能"),
    ],
    "/memory": [
        ("overview", "记忆总览"),
        ("history", "当前会话历史"),
        ("list", "长期记忆列表"),
        ("search", "搜索长期记忆"),
        ("export", "导出长期记忆"),
        ("import", "导入长期记忆"),
        ("delete", "删除长期记忆"),
        ("learn", "添加自动记忆"),
        ("forget", "删除自动记忆"),
        ("facts", "自动记忆列表"),
    ],
    "/rollback": [("list", "列出可回滚快照")],
    "/debug": [("on", "显示详细工具信息"), ("off", "只显示工具名称")],
}
_AT_COMPLETION_RE = re.compile(r'(?<![A-Za-z0-9_@])@(?:"([^"]*)|([^\s，。；：、！？]*))$')


class ProjectFileIndex:
    """Cached list of project-relative file paths for @ completion."""

    def __init__(self, root: Path):
        self._root = root
        self._files: list[str] = []
        self._built_at = 0.0

    def files(self) -> list[str]:
        if time.monotonic() - self._built_at > CACHE_TTL:
            self._rebuild()
        return self._files

    def _rebuild(self) -> None:
        files: list[str] = []
        stack = [self._root]
        while stack and len(files) < MAX_FILES:
            current = stack.pop()
            try:
                entries = sorted(current.iterdir())
            except OSError:
                continue
            for p in entries:
                if p.is_dir():
                    if p.name not in IGNORED_DIRS and not p.is_symlink():
                        stack.append(p)
                elif p.is_file() and p.suffix.lower() not in UNSUPPORTED_FILE_SUFFIXES:
                    files.append(str(p.relative_to(self._root)).replace("\\", "/"))
        self._files = files
        self._built_at = time.monotonic()


def _fuzzy_match(needle: str, candidate: str) -> bool:
    """Case-insensitive subsequence match (e.g. 'agt' matches 'agent.py')."""
    it = iter(candidate.lower())
    return all(ch in it for ch in needle.lower())


def _file_rank(needle: str, path: str) -> tuple[int, int, str]:
    needle_lower = needle.lower()
    path_lower = path.lower()
    basename = path_lower.rsplit("/", 1)[-1]
    if not needle_lower:
        rank = 0
    elif path_lower == needle_lower or basename == needle_lower:
        rank = 1
    elif basename.startswith(needle_lower):
        rank = 2
    elif path_lower.startswith(needle_lower):
        rank = 3
    elif needle_lower in basename:
        rank = 4
    elif needle_lower in path_lower:
        rank = 5
    else:
        rank = 6
    return rank, len(path), path_lower


class CliCompleter(Completer):
    """Complete @file mentions, /slash commands, and common command arguments."""

    def __init__(
        self,
        project_path: Path,
        commands_provider: Callable[[], list[tuple[str, str]]],
    ):
        self._index = ProjectFileIndex(project_path)
        self._commands_provider = commands_provider

    def get_completions(
        self, document: Document, _complete_event: Any
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        mention = _AT_COMPLETION_RE.search(text)
        if mention:
            quoted, unquoted = mention.groups()
            needle = quoted if quoted is not None else unquoted
            needs_quote = quoted is not None and not document.text_after_cursor.startswith('"')
            closing_quote = '"' if needs_quote else ""
            yield from self._file_completions(needle, closing_quote)
            return

        if "\n" in text or not text.startswith("/"):
            return
        argument = re.fullmatch(r"(/\S+)[ \t]+([^\s]*)", text)
        if argument:
            yield from self._argument_completions(argument.group(1), argument.group(2))
        elif re.fullmatch(r"/\S*", text):
            yield from self._command_completions(text)

    def _file_completions(self, needle: str, suffix: str = "") -> Iterable[Completion]:
        candidates = [p for p in self._index.files() if not needle or _fuzzy_match(needle, p)]
        candidates.sort(key=lambda p: _file_rank(needle, p))
        for path in candidates[:MAX_SUGGESTIONS]:
            yield Completion(path + suffix, start_position=-len(needle), display=path)

    def _command_completions(self, needle: str) -> Iterable[Completion]:
        needle_lower = needle.lower()
        for name, description in self._commands_provider():
            if name.lower().startswith(needle_lower):
                yield Completion(
                    name,
                    start_position=-len(needle),
                    display=name,
                    display_meta=description,
                )

    def _argument_completions(self, command: str, needle: str) -> Iterable[Completion]:
        needle_lower = needle.lower()
        for value, description in COMMAND_ARGUMENTS.get(command.lower(), []):
            if value.startswith(needle_lower):
                yield Completion(
                    value,
                    start_position=-len(needle),
                    display=value,
                    display_meta=description,
                )
