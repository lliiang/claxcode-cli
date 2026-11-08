"""Tests for shell process interruption cleanup."""

import pytest

from claxcode.tools.execution import RunShell


class SimulatedInterruptError(Exception):
    pass


class SimulatedCancelError(Exception):
    pass


class FakeProcess:
    def __init__(self, exception=SimulatedInterruptError):
        self.exception = exception
        self.returncode = None
        self.killed = False
        self.waited = False

    async def communicate(self):
        raise self.exception()

    def kill(self):
        self.killed = True

    async def wait(self):
        self.waited = True
        self.returncode = -1


async def _test_interrupt_cleanup(monkeypatch, exception, target):
    proc = FakeProcess(exception)

    async def fake_create(*args, **kwargs):
        return proc

    monkeypatch.setattr("claxcode.tools.execution.asyncio.create_subprocess_shell", fake_create)
    monkeypatch.setattr(f"claxcode.tools.execution.{target}", exception, raising=False)
    with pytest.raises(exception):
        await RunShell().execute("test")
    assert proc.killed is True
    assert proc.waited is True


async def test_shell_interrupt_kills_process_and_reraises(monkeypatch):
    await _test_interrupt_cleanup(monkeypatch, SimulatedInterruptError, "KeyboardInterrupt")


async def test_shell_task_cancellation_kills_process(monkeypatch):
    await _test_interrupt_cleanup(monkeypatch, SimulatedCancelError, "asyncio.CancelledError")
