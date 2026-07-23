"""Tests for shell lifecycle hooks."""

import json
import sys

from claxcode.extensions.hooks import Hook, HookManager


def _write_config(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _manager(tmp_path, config):
    _write_config(tmp_path / ".claxcode" / "hooks.json", config)
    return HookManager(tmp_path)


def test_hook_matching():
    assert Hook("", "cmd", ".").matches("anything")
    assert Hook("*", "cmd", ".").matches("anything")
    assert Hook("run_shell", "cmd", ".").matches("run_shell")
    assert Hook("run_", "cmd", ".").matches("run_shell")
    assert not Hook("write", "cmd", ".").matches("run_shell")
    # invalid regex falls back to exact comparison
    assert Hook("run[", "cmd", ".").matches("run_shell") is False


async def test_pre_hook_blocks_on_nonzero_exit(tmp_path):
    cmd = f'"{sys.executable}" -c "import sys; sys.exit(1)"'
    mgr = _manager(tmp_path, {"PreToolUse": [{"match": "", "command": cmd}]})
    allowed, reason = await mgr.run_pre("any_tool", {})
    assert allowed is False
    assert "退出码" in reason


async def test_pre_hook_allows_on_zero_exit(tmp_path):
    cmd = f'"{sys.executable}" -c "pass"'
    mgr = _manager(tmp_path, {"PreToolUse": [{"match": "run_shell", "command": cmd}]})
    assert await mgr.run_pre("run_shell", {}) == (True, "")
    assert await mgr.run_pre("other_tool", {}) == (True, "")


async def test_hook_receives_json_payload(tmp_path):
    out_file = tmp_path / "payload.json"
    cmd = (
        f'"{sys.executable}" -c "import sys, pathlib; '
        f"pathlib.Path(r'{out_file}').write_text(sys.stdin.read())\""
    )
    mgr = _manager(tmp_path, {"PreToolUse": [{"match": "", "command": cmd}]})
    await mgr.run_pre("write_file", {"path": "a.py"})
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["tool"] == "write_file"
    assert payload["arguments"] == {"path": "a.py"}


async def test_post_hook_output_collected(tmp_path):
    cmd = f'"{sys.executable}" -c "print(\'lint ok\')"'
    mgr = _manager(tmp_path, {"PostToolUse": [{"match": "write", "command": cmd}]})
    output = await mgr.run_post("write_file", {}, "done")
    assert "lint ok" in output


async def test_missing_config_means_no_hooks(tmp_path):
    mgr = HookManager(tmp_path)
    assert await mgr.run_pre("x", {}) == (True, "")
    assert await mgr.run_post("x", {}, "") == ""
