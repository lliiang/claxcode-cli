"""Execution tools."""

import asyncio
from typing import Any

from claxcode.tools.base import Tool
from claxcode.tools.registry import tool

# Global flag for tool cancellation
_tool_cancelled = False


def set_tool_cancelled() -> None:
    """Set the tool cancellation flag."""
    global _tool_cancelled
    _tool_cancelled = True


def clear_tool_cancelled() -> None:
    """Reset the cancellation flag (called before each user message)."""
    global _tool_cancelled
    _tool_cancelled = False


def is_tool_cancelled() -> bool:
    """Return True if the user requested cancellation (Ctrl+C)."""
    return _tool_cancelled


@tool
class RunShell(Tool):
    name = "run_shell"
    description = "Run a shell command and return stdout/stderr."
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "cwd": {"type": "string", "description": "Working directory", "default": "."},
            "timeout": {"type": "integer", "default": 60},
        },
        "required": ["command"],
    }
    category = "execution"
    required_permissions = ["execute"]

    async def execute(self, command: str, cwd: str = ".", timeout: int = 60, **kwargs: Any) -> str:
        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n[stderr]\n" + stderr.decode("utf-8", errors="replace")
            if proc.returncode != 0:
                output += f"\n[exit code: {proc.returncode}]"
            return output
        except TimeoutError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            return f"Error: Command timed out after {timeout}s"
        except KeyboardInterrupt:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise
        except Exception as exc:
            return f"Error: {exc}"


@tool
class RunTests(Tool):
    name = "run_tests"
    description = "Run the project's test suite (pytest)."
    input_schema = {
        "type": "object",
        "properties": {
            "target": {"type": "string", "default": ".", "description": "Directory or file to test"},
            "verbose": {"type": "boolean", "default": True},
        },
        "required": [],
    }
    category = "execution"
    required_permissions = ["execute"]

    async def execute(self, target: str = ".", verbose: bool = True, **kwargs: Any) -> str:
        cmd = f"pytest {target}"
        if verbose:
            cmd += " -v"
        return await RunShell().execute(command=cmd, cwd=".")


@tool
class GitCommand(Tool):
    name = "git_command"
    description = "Run a git command."
    input_schema = {
        "type": "object",
        "properties": {
            "args": {"type": "string", "description": "Git arguments, e.g., 'status' or 'diff HEAD'"},
            "cwd": {"type": "string", "default": "."},
        },
        "required": ["args"],
    }
    category = "execution"
    required_permissions = ["execute"]

    async def execute(self, args: str, cwd: str = ".", **kwargs: Any) -> str:
        return await RunShell().execute(command=f"git {args}", cwd=cwd)
