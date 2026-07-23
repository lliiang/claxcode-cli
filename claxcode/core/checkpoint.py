"""Pre-edit snapshot and rollback system."""

import asyncio
import json
import shutil
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from claxcode.config import settings


class CheckpointManager:
    """Creates filesystem snapshots before edits and restores them on demand."""

    def __init__(self) -> None:
        self.base_dir = settings.snapshots_dir

    def _session_snapshot_dir(self, session_id: UUID) -> Path:
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        return self.base_dir / str(session_id) / ts

    async def snapshot(self, session_id: UUID, file_path: str) -> Path:
        """Copy file to snapshot directory before editing."""
        target = Path(file_path)
        if not target.exists():
            return Path()
        snap_dir = self._session_snapshot_dir(session_id)
        while snap_dir.exists():  # same-microsecond collision: wait for a fresh timestamp
            await asyncio.sleep(0.001)
            snap_dir = self._session_snapshot_dir(session_id)
        snap_dir.mkdir(parents=True, exist_ok=True)
        dest = snap_dir / target.name
        shutil.copy2(target, dest)
        self._write_manifest(snap_dir, target)
        return dest

    def _write_manifest(self, snap_dir: Path, target: Path) -> None:
        """Record the original path of each snapshotted file."""
        manifest = snap_dir / "manifest.json"
        data: dict[str, str] = {}
        if manifest.exists():
            with suppress(json.JSONDecodeError, OSError):
                data = json.loads(manifest.read_text(encoding="utf-8"))
        data[target.name] = str(target.resolve())
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_manifest(self, snap_dir: Path) -> dict[str, str]:
        manifest = snap_dir / "manifest.json"
        if not manifest.exists():
            return {}
        with suppress(json.JSONDecodeError, OSError):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        return {}

    def list_snapshots(self, session_id: UUID, limit: int = 10) -> list[dict[str, Any]]:
        """Most recent snapshot batches, newest first."""
        session_dir = self.base_dir / str(session_id)
        if not session_dir.exists():
            return []
        entries = []
        for snap_dir in sorted(session_dir.iterdir(), reverse=True):
            if not snap_dir.is_dir():
                continue
            files = list(self._read_manifest(snap_dir).values())
            if not files:  # legacy snapshots without a manifest
                files = [
                    f.name for f in snap_dir.iterdir() if f.is_file() and f.name != "manifest.json"
                ]
            entries.append({"timestamp": snap_dir.name, "files": files})
            if len(entries) >= limit:
                break
        return entries

    def restore(self, session_id: UUID, steps: int = 1) -> list[str]:
        """Restore files from the `steps` most recent snapshots.

        For each file the oldest copy wins, so the file returns to its state
        before all of the rolled-back actions. Returns restored paths.
        """
        batches = self.list_snapshots(session_id, limit=steps)
        restored: list[str] = []
        for batch in reversed(batches):  # oldest batch first
            snap_dir = self.base_dir / str(session_id) / batch["timestamp"]
            for name, original in self._read_manifest(snap_dir).items():
                if original in restored:
                    continue
                src = snap_dir / name
                if not src.exists():
                    continue
                Path(original).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, original)
                restored.append(original)
        return restored
