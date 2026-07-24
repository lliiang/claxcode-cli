"""Tests for the polling-based SSH command execution."""

import pytest

import claxcode.tools.ssh as ssh_mod
from claxcode.tools.execution import clear_tool_cancelled, set_tool_cancelled
from claxcode.tools.ssh import SSHExecute, _format_remote_result


class FakeChannel:
    """Minimal paramiko channel stand-in."""

    def __init__(self, stdout=b"", stderr=b"", polls_until_exit=1, exit_code=0):
        self._stdout = stdout
        self._stderr = stderr
        self._polls_until_exit = polls_until_exit
        self._exit_code = exit_code
        self.commands: list[str] = []
        self.closed = False

    def exec_command(self, command):
        self.commands.append(command)

    def exit_status_ready(self):
        if self._polls_until_exit <= 0:
            return True
        self._polls_until_exit -= 1
        return False

    def recv_ready(self):
        return bool(self._stdout)

    def recv_stderr_ready(self):
        return bool(self._stderr)

    def recv(self, n):
        data, self._stdout = self._stdout[:n], self._stdout[n:]
        return data

    def recv_stderr(self, n):
        data, self._stderr = self._stderr[:n], self._stderr[n:]
        return data

    def recv_exit_status(self):
        return self._exit_code

    def close(self):
        self.closed = True


class FakeTransport:
    def __init__(self, channel):
        self._channel = channel

    def open_session(self):
        return self._channel


class FakeClient:
    def __init__(self, channel):
        self._channel = channel

    def get_transport(self):
        return FakeTransport(self._channel)


@pytest.fixture(autouse=True)
def _clear_cancel_flag():
    clear_tool_cancelled()
    yield
    clear_tool_cancelled()


def _run(channel, monkeypatch, timeout=60):
    monkeypatch.setattr(ssh_mod, "_get_ssh_client", lambda **kwargs: FakeClient(channel))
    tool = SSHExecute()
    return tool.execute(host="h", username="u", command="echo hi", timeout=timeout)


async def test_execute_collects_output(monkeypatch):
    channel = FakeChannel(stdout=b"hello world\n", polls_until_exit=2)
    result = await _run(channel, monkeypatch)
    assert "hello world" in result
    assert "[exit code: 0]" in result
    assert channel.commands == ["echo hi"]
    assert channel.closed


async def test_execute_collects_stderr(monkeypatch):
    channel = FakeChannel(stdout=b"ok", stderr=b"warn!", exit_code=1)
    result = await _run(channel, monkeypatch)
    assert "warn!" in result
    assert "[exit code: 1]" in result


async def test_execute_timeout_returns_partial_output(monkeypatch):
    channel = FakeChannel(stdout=b"partial", polls_until_exit=10**9)
    result = await _run(channel, monkeypatch, timeout=-1)
    assert "partial" in result
    assert "超时" in result
    assert channel.closed


async def test_execute_cancelled_by_user(monkeypatch):
    channel = FakeChannel(polls_until_exit=10**9)
    set_tool_cancelled()
    result = await _run(channel, monkeypatch)
    assert "中止" in result
    assert channel.closed


async def test_dangerous_command_rejected():
    tool = SSHExecute()
    result = await tool.execute(host="h", username="u", command="rm -rf /")
    assert "被拒绝" in result


def test_format_result_empty():
    assert _format_remote_result([], [], None, "") == "(无输出)"
