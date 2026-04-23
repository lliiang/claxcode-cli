"""Tests for permission modes."""

import pytest

from claxcode.security.permissions import PermissionMode, check_permission


@pytest.mark.parametrize("mode", [PermissionMode.AUTO_EDIT, PermissionMode.YOLO])
def test_auto_edit_and_yolo_allow_all(mode):
    assert check_permission(mode, "write_file", ["write"]) == (True, "")
    assert check_permission(mode, "run_shell", ["execute"]) == (True, "")
    assert check_permission(mode, "read_file", ["read"]) == (True, "")


def test_plan_mode_blocks_write_and_execute():
    assert check_permission(PermissionMode.PLAN, "write_file", ["write"]) == (
        False,
        "Plan mode is read-only",
    )
    assert check_permission(PermissionMode.PLAN, "run_shell", ["execute"]) == (
        False,
        "Plan mode is read-only",
    )
    assert check_permission(PermissionMode.PLAN, "read_file", ["read"]) == (True, "")


def test_ask_mode_always_asks():
    assert check_permission(PermissionMode.ASK, "read_file", ["read"]) == (
        False,
        "Approval required",
    )


def test_auto_safe_blocks_execute():
    assert check_permission(PermissionMode.AUTO_SAFE, "run_shell", ["execute"]) == (
        False,
        "Execution requires approval in auto-safe mode",
    )
    assert check_permission(PermissionMode.AUTO_SAFE, "write_file", ["write"]) == (True, "")
