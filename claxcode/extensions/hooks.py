"""Lifecycle hooks — run shell commands before/after tool execution.

Config is read from `~/.claxcode/hooks.json` (global) and
`<project>/.claxcode/hooks.json` (project). Format:

{
  "PreToolUse":  [{"match": "run_shell|write_file", "command": "python guard.py"}],
  "PostToolUse": [{"match": "", "command": "echo done"}]
}

`match` is a regex tested against the tool name (empty or "*" matches all).
The hook command receives a JSON payload on stdin
({"tool": ..., "arguments": {...}, "result": ...}) plus the env vars
CLAXCODE_TOOL_NAME / CLAXCODE_TOOL_ARGS, and runs with the config's
project directory as cwd. A PreToolUse hook blocks the tool call when it
exits non-zero; its stdout becomes the block reason. Hooks that fail to
spawn or time out never block the main flow.
"""

import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HOOK_TIMEOUT = 30
HOOK_EVENTS = ("PreToolUse", "PostToolUse")


@dataclass
class Hook:
    """A single shell hook from a hooks.json config."""

    match: str
    command: str
    cwd: Path

    def matches(self, tool_name: str) -> bool:
        if not self.match or self.match == "*":
            return True
        try:
            return re.search(self.match, tool_name) is not None
        except re.error:
            return self.match == tool_name


class HookManager:
    """Load and execute PreToolUse/PostToolUse shell hooks."""

    def __init__(self, project_path: Path | None = None):
        self._hooks: dict[str, list[Hook]] = {event: [] for event in HOOK_EVENTS}
        for config_path in self._config_paths(project_path):
            self._load_config(config_path)

    def _config_paths(self, project_path: Path | None) -> list[Path]:
        paths = [Path.home() / ".claxcode" / "hooks.json"]
        if project_path is not None:
            paths.append(project_path / ".claxcode" / "hooks.json")
        return paths

    def _load_config(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        cwd = path.parent.parent if path.parent.name == ".claxcode" else path.parent
        for event in HOOK_EVENTS:
            for entry in data.get(event, []):
                command = entry.get("command", "")
                if command:
                    self._hooks[event].append(Hook(entry.get("match", ""), command, cwd))

    async def run_pre(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        """Run PreToolUse hooks. Returns (allowed, reason)."""
        for hook in self._hooks["PreToolUse"]:
            if not hook.matches(tool_name):
                continue
            code, output = await self._run_command(hook, tool_name, arguments)
            if code != 0:
                return False, output or f"钩子命令退出码 {code}"
        return True, ""

    async def run_post(self, tool_name: str, arguments: dict[str, Any], result: str) -> str:
        """Run PostToolUse hooks. Returns combined hook output (may be empty)."""
        outputs = []
        for hook in self._hooks["PostToolUse"]:
            if not hook.matches(tool_name):
                continue
            _, output = await self._run_command(hook, tool_name, arguments, result)
            if output:
                outputs.append(output)
        return "\n".join(outputs)

    async def _run_command(
        self,
        hook: Hook,
        tool_name: str,
        arguments: dict[str, Any],
        result: str = "",
    ) -> tuple[int, str]:
        payload = {"tool": tool_name, "arguments": arguments, "result": result}
        env = {
            **os.environ,
            "CLAXCODE_TOOL_NAME": tool_name,
            "CLAXCODE_TOOL_ARGS": json.dumps(arguments, ensure_ascii=False),
        }
        try:
            proc = await asyncio.create_subprocess_shell(
                hook.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(hook.cwd),
                env=env,
            )
        except OSError:
            return 0, ""  # 钩子无法启动时不阻塞主流程

        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(json.dumps(payload, ensure_ascii=False).encode()),
                timeout=HOOK_TIMEOUT,
            )
        except TimeoutError:
            proc.kill()
            return 0, ""
        return proc.returncode or 0, stdout.decode("utf-8", errors="replace").strip()
