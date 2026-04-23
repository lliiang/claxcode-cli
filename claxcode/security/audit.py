"""Audit logging (stub for Phase 6)."""

from datetime import datetime, timezone
from uuid import UUID


class AuditLogger:
    """Logs tool calls and permission decisions."""

    def __init__(self):
        self._logs: list[dict] = []

    def log_tool_call(
        self,
        session_id: UUID,
        tool_name: str,
        arguments: dict,
        result: str,
        allowed: bool,
    ) -> None:
        self._logs.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "session_id": str(session_id),
                "tool_name": tool_name,
                "arguments": arguments,
                "result_preview": result[:500],
                "allowed": allowed,
            }
        )


audit_logger = AuditLogger()
