"""Permission modes."""

from enum import Enum


class PermissionMode(str, Enum):
    ASK = "ask"
    AUTO_EDIT = "auto_edit"
    PLAN = "plan"
    AUTO_SAFE = "auto_safe"
    YOLO = "yolo"


def check_permission(mode: PermissionMode, tool_name: str, required_perms: list[str]) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    if mode == PermissionMode.PLAN:
        if "write" in required_perms or "execute" in required_perms:
            return False, "Plan mode is read-only"
    if mode == PermissionMode.ASK:
        # Always ask; caller should prompt user
        return False, "Approval required"
    if mode == PermissionMode.AUTO_SAFE:
        # Allow read and safe edits; block destructive execute
        if "execute" in required_perms:
            return False, "Execution requires approval in auto-safe mode"
    # AUTO_EDIT and YOLO allow everything
    return True, ""
