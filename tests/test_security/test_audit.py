"""Tests for the durable audit logger."""

import json
from uuid import uuid4

from claxcode.security.audit import AuditLogger


def test_audit_log_written_to_jsonl(tmp_path):
    logger = AuditLogger(log_path=tmp_path / "audit.jsonl")
    logger.log_tool_call(uuid4(), "write_file", {"path": "a.py"}, "ok", allowed=True)

    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["tool_name"] == "write_file"
    assert entry["allowed"] is True


def test_read_recent_returns_newest_last(tmp_path):
    logger = AuditLogger(log_path=tmp_path / "audit.jsonl")
    for i in range(3):
        logger.log_tool_call(uuid4(), f"tool_{i}", {}, "", allowed=True)

    entries = logger.read_recent(limit=2)
    assert [e["tool_name"] for e in entries] == ["tool_1", "tool_2"]


def test_read_recent_empty_when_no_log(tmp_path):
    logger = AuditLogger(log_path=tmp_path / "audit.jsonl")
    assert logger.read_recent() == []


def test_audit_failure_does_not_raise(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    logger = AuditLogger(log_path=blocker / "audit.jsonl")
    logger.log_tool_call(uuid4(), "t", {}, "", allowed=True)  # should not raise
