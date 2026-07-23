"""Durable audit logging — JSONL audit trail under .claxcode/."""

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import UUID


class AuditLogger:
    """Logs tool calls and permission decisions to a JSONL file."""

    def __init__(self, log_path: Path | None = None):
        self._log_path = log_path or Path(".claxcode") / "audit.jsonl"
        self._lock = Lock()

    def log_tool_call(
        self,
        session_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
        result: str,
        allowed: bool,
    ) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": str(session_id),
            "tool_name": tool_name,
            "arguments": arguments,
            "result_preview": result[:500],
            "allowed": allowed,
        }
        self._append(entry)

    def read_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the most recent entries (newest last)."""
        if not self._log_path.exists():
            return []
        lines = self._log_path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:] if line.strip()]

    def _append(self, entry: dict[str, Any]) -> None:
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass  # 审计写入失败不应阻塞主流程


audit_logger = AuditLogger()
