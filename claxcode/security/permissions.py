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
            return False, "计划模式为只读模式"
    if mode == PermissionMode.ASK:
        # Always ask; caller should prompt user
        return False, "需要批准"
    if mode == PermissionMode.AUTO_SAFE:
        # Allow read and safe edits; block destructive execute
        if "execute" in required_perms:
            return False, "在自动安全模式下执行操作需要批准"
    # AUTO_EDIT and YOLO allow everything
    return True, ""
