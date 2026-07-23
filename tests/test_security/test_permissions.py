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
        "计划模式为只读模式",
    )
    assert check_permission(PermissionMode.PLAN, "run_shell", ["execute"]) == (
        False,
        "计划模式为只读模式",
    )
    assert check_permission(PermissionMode.PLAN, "read_file", ["read"]) == (True, "")


def test_ask_mode_allows_read_only_tools():
    assert check_permission(PermissionMode.ASK, "read_file", ["read"]) == (True, "")


def test_ask_mode_requires_approval_for_write_and_execute():
    assert check_permission(PermissionMode.ASK, "write_file", ["write"]) == (
        False,
        "需要批准",
    )
    assert check_permission(PermissionMode.ASK, "run_shell", ["execute"]) == (
        False,
        "需要批准",
    )


def test_auto_safe_blocks_execute():
    assert check_permission(PermissionMode.AUTO_SAFE, "run_shell", ["execute"]) == (
        False,
        "在自动安全模式下执行操作需要批准",
    )
    assert check_permission(PermissionMode.AUTO_SAFE, "write_file", ["write"]) == (True, "")
