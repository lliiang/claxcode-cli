"""Pre-edit snapshot and rollback system."""

import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from claxcode.config import settings


class CheckpointManager:
    """Creates filesystem snapshots before edits."""

    def __init__(self):
        self.base_dir = settings.snapshots_dir

    def _session_snapshot_dir(self, session_id: UUID) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        return self.base_dir / str(session_id) / ts

    async def snapshot(self, session_id: UUID, file_path: str) -> Path:
        """Copy file to snapshot directory before editing."""
        target = Path(file_path)
        if not target.exists():
            return Path()
        snap_dir = self._session_snapshot_dir(session_id)
        snap_dir.mkdir(parents=True, exist_ok=True)
        dest = snap_dir / target.name
        shutil.copy2(target, dest)
        return dest

    async def rollback(self, session_id: UUID, timestamp: str | None = None) -> list[str]:
        """Restore files from the latest (or specified) snapshot."""
        session_dir = self.base_dir / str(session_id)
        if not session_dir.exists():
            return []

        if timestamp:
            snap_dir = session_dir / timestamp
        else:
            # Latest snapshot
            snaps = sorted(session_dir.iterdir())
            if not snaps:
                return []
            snap_dir = snaps[-1]

        restored = []
        for src in snap_dir.iterdir():
            # Restore to original location (assume working dir)
            dest = Path(src.name)
            shutil.copy2(src, dest)
            restored.append(str(dest))
        return restored
