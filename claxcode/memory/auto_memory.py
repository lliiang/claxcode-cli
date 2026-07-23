"""Auto-memory for learned facts and preferences (durable JSON store)."""

import json
from pathlib import Path

DEFAULT_STORE_PATH = Path.home() / ".claxcode" / "auto_memory.json"


class AutoMemory:
    """Stores user preferences and project patterns in a JSON file."""

    def __init__(self, store_path: Path | None = None, limit: int = 50):
        self._store_path = store_path or DEFAULT_STORE_PATH
        self._limit = limit
        self._memories: dict[str, str] = self._load()

    def remember(self, key: str, value: str) -> str:
        """Record or update a fact. Returns a human-readable status."""
        if key not in self._memories and len(self._memories) >= self._limit:
            return f"记忆已满（{self._limit} 条上限），请先清理其他条目"
        self._memories[key] = value
        self._save()
        return f"已记住: {key}"

    def recall(self, key: str) -> str | None:
        return self._memories.get(key)

    def forget(self, key: str) -> bool:
        """Delete a fact. Returns True if it existed."""
        if key not in self._memories:
            return False
        del self._memories[key]
        self._save()
        return True

    def items(self) -> dict[str, str]:
        return dict(self._memories)

    def to_prompt_fragment(self) -> str:
        if not self._memories:
            return ""
        lines = ["# 用户偏好与事实（自动记忆）"]
        for k, v in self._memories.items():
            lines.append(f"- {k}: {v}")
        return "\n".join(lines)

    def _load(self) -> dict[str, str]:
        if not self._store_path.exists():
            return {}
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def _save(self) -> None:
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            self._store_path.write_text(
                json.dumps(self._memories, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass  # 记忆写入失败不应阻塞主流程


# Global singleton shared by the agent prompt, the remember_fact tool and the CLI.
auto_memory = AutoMemory()
