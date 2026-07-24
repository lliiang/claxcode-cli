"""Input completion for the interactive CLI (@file mentions and /commands).

Built on prompt_toolkit. The file index is rebuilt lazily with a short TTL
so completion stays cheap even on large projects; dependency/cache dirs
(from tools.search.IGNORED_DIRS) are pruned.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from claxcode.tools.search import IGNORED_DIRS

MAX_FILES = 5000
MAX_SUGGESTIONS = 50
CACHE_TTL = 30.0


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
                    if p.name not in IGNORED_DIRS:
                        stack.append(p)
                elif p.is_file():
                    files.append(str(p.relative_to(self._root)).replace("\\", "/"))
        self._files = files
        self._built_at = time.monotonic()


def _fuzzy_match(needle: str, candidate: str) -> bool:
    """Case-insensitive subsequence match (e.g. 'agt' matches 'agent.py')."""
    it = iter(candidate.lower())
    return all(ch in it for ch in needle.lower())


class CliCompleter(Completer):
    """Complete @file mentions (fuzzy) and /slash commands (prefix)."""

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
        word = document.get_word_before_cursor(WORD=True)
        if word.startswith("@"):
            yield from self._file_completions(word[1:])
        elif word.startswith("/") and document.text_before_cursor == word:
            yield from self._command_completions(word)

    def _file_completions(self, needle: str) -> Iterable[Completion]:
        candidates = [
            p for p in self._index.files() if not needle or _fuzzy_match(needle, p)
        ]
        needle_lower = needle.lower()
        candidates.sort(key=lambda p: (not p.lower().startswith(needle_lower), len(p), p))
        for path in candidates[:MAX_SUGGESTIONS]:
            yield Completion(path, start_position=-len(needle), display=path)

    def _command_completions(self, needle: str) -> Iterable[Completion]:
        for name, description in self._commands_provider():
            if name.startswith(needle):
                yield Completion(
                    name,
                    start_position=-len(needle),
                    display=name,
                    display_meta=description,
                )
