"""Project-level context loading."""

from pathlib import Path

from claxcode.config import settings


def load_project_context(project_path: Path) -> str:
    """Load CLAUDE.md or .claxcode/context.md if present."""
    candidates = [
        project_path / settings.project_context_file,
        project_path / ".claxcode" / "context.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return candidate.read_text(encoding="utf-8")
            except Exception:
                continue
    return ""
