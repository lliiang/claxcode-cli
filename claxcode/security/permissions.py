"""Permission modes."""

from enum import Enum


class PermissionMode(str, Enum):
    ASK = "ask"
    AUTO_EDIT = "auto_edit"
    PLAN = "plan"
    AUTO_SAFE = "auto_safe"
    YOLO = "yolo"


def check_permission(
    mode: PermissionMode, tool_name: str, required_perms: list[str]
) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    needs_write = "write" in required_perms or "execute" in required_perms
    if mode == PermissionMode.PLAN and needs_write:
        return False, "计划模式为只读模式"
    if mode == PermissionMode.ASK:
        # Read-only tools run freely; anything else requires user approval
        if set(required_perms) <= {"read"}:
            return True, ""
        return False, "需要批准"
    if mode == PermissionMode.AUTO_SAFE and "execute" in required_perms:
        return False, "在自动安全模式下执行操作需要批准"
    # AUTO_EDIT and YOLO allow everything
    return True, ""
