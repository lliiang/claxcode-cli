"""Tests for checkpoint listing and rollback."""

from pathlib import Path
from uuid import uuid4

from claxcode.core.checkpoint import CheckpointManager


def _mgr(tmp_path):
    mgr = CheckpointManager()
    mgr.base_dir = tmp_path / "snapshots"
    return mgr


async def test_snapshot_writes_manifest(tmp_path):
    mgr = _mgr(tmp_path)
    target = tmp_path / "a.py"
    target.write_text("v1", encoding="utf-8")
    sid = uuid4()

    await mgr.snapshot(sid, str(target))

    batches = mgr.list_snapshots(sid)
    assert len(batches) == 1
    assert batches[0]["files"] == [str(target.resolve())]


async def test_restore_reverts_latest_change(tmp_path):
    mgr = _mgr(tmp_path)
    target = tmp_path / "a.py"
    target.write_text("v1", encoding="utf-8")
    sid = uuid4()
    await mgr.snapshot(sid, str(target))
    target.write_text("v2", encoding="utf-8")

    restored = mgr.restore(sid)

    assert restored == [str(target.resolve())]
    assert target.read_text(encoding="utf-8") == "v1"


async def test_restore_multiple_steps_uses_oldest_copy(tmp_path):
    mgr = _mgr(tmp_path)
    target = tmp_path / "a.py"
    sid = uuid4()
    target.write_text("v1", encoding="utf-8")
    await mgr.snapshot(sid, str(target))
    target.write_text("v2", encoding="utf-8")
    await mgr.snapshot(sid, str(target))
    target.write_text("v3", encoding="utf-8")

    mgr.restore(sid, steps=2)

    assert target.read_text(encoding="utf-8") == "v1"


async def test_snapshot_missing_file_is_noop(tmp_path):
    mgr = _mgr(tmp_path)
    sid = uuid4()
    dest = await mgr.snapshot(sid, str(tmp_path / "nope.py"))
    assert dest == Path()
    assert mgr.list_snapshots(sid) == []


async def test_nonpositive_snapshot_limit_returns_empty(tmp_path):
    mgr = _mgr(tmp_path)
    target = tmp_path / "a.py"
    target.write_text("v1", encoding="utf-8")
    sid = uuid4()
    await mgr.snapshot(sid, str(target))
    assert mgr.list_snapshots(sid, limit=0) == []
