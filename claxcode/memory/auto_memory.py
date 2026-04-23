"""Auto-memory for learned patterns and preferences (stub for Phase 5)."""

from typing import Any


class AutoMemory:
    """Stores and retrieves user preferences and project patterns."""

    def __init__(self):
        self._memories: dict[str, str] = {}

    def remember(self, key: str, value: str) -> None:
        self._memories[key] = value

    def recall(self, key: str) -> str | None:
        return self._memories.get(key)

    def to_prompt_fragment(self) -> str:
        if not self._memories:
            return ""
        lines = ["# Auto Memory"]
        for k, v in self._memories.items():
            lines.append(f"- {k}: {v}")
        return "\n".join(lines)
