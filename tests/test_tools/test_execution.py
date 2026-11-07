"""Tests for shell process interruption cleanup."""

import pytest

from claxcode.tools.execution import RunShell


class SimulatedInterruptError(Exception):
    pass


class FakeProcess:
    def __init__(self):
        self.returncode = None
        self.killed = False
        self.waited = False

    async def communicate(self):
        raise SimulatedInterruptError()

    def kill(self):
        self.killed = True

    async def wait(self):
        self.waited = True
        self.returncode = -1


async def test_shell_interrupt_kills_process_and_reraises(monkeypatch):
    proc = FakeProcess()

    async def fake_create(*args, **kwargs):
        return proc

    monkeypatch.setattr("claxcode.tools.execution.asyncio.create_subprocess_shell", fake_create)
    monkeypatch.setattr(
        "claxcode.tools.execution.KeyboardInterrupt", SimulatedInterruptError, raising=False
    )
    with pytest.raises(SimulatedInterruptError):
        await RunShell().execute("test")
    assert proc.killed is True
    assert proc.waited is True
