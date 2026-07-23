"""Tests for the CLI slash-command dispatch table and skill command routing."""

from claxcode.cli import InteractiveCLI


def test_command_table_contains_all_builtin_commands():
    cli = InteractiveCLI(".")
    expected = {
        "/help", "/tools", "/mode", "/skills", "/config", "/debug", "/clear",
        "/project", "/memory", "/init", "/compact", "/audit", "/exit", "/quit",
    }
    assert expected <= set(cli._command_table.keys())


async def test_unknown_command_prints_hint(capsys):
    cli = InteractiveCLI(".")
    assert await cli._handle_command("/nonexistent") is False
    assert "未知命令" in capsys.readouterr().out


async def test_exit_command_returns_true():
    cli = InteractiveCLI(".")
    assert await cli._handle_command("/exit") is True


async def test_help_lists_commands_and_skill_commands(capsys):
    cli = InteractiveCLI(".")
    await cli._handle_command("/help")
    out = capsys.readouterr().out
    assert "/audit" in out
    assert "refactor_file" in out  # built-in skill command


async def test_skill_command_routed_to_agent(monkeypatch):
    cli = InteractiveCLI(".")
    sent = []

    async def fake_chat(message: str) -> None:
        sent.append(message)

    monkeypatch.setattr(cli, "_chat", fake_chat)
    await cli._handle_command("/refactor_file foo.py")
    assert len(sent) == 1
    assert "refactor_file" in sent[0]
    assert "foo.py" in sent[0]


def test_rollback_in_command_table():
    assert "/rollback" in InteractiveCLI(".")._command_table


def test_expand_mentions_inlines_file(tmp_path):
    cli = InteractiveCLI(str(tmp_path))
    (tmp_path / "note.py").write_text("print('hi')", encoding="utf-8")
    out = cli._expand_mentions("看一下 @note.py 这个文件")
    assert "print('hi')" in out
    assert "note.py" in out


def test_expand_mentions_ignores_missing_files(tmp_path):
    cli = InteractiveCLI(str(tmp_path))
    out = cli._expand_mentions("看一下 @nope.py")
    assert "```" not in out


def test_quick_memory_records(tmp_path, monkeypatch, capsys):
    from claxcode.memory.auto_memory import AutoMemory

    mem = AutoMemory(store_path=tmp_path / "auto.json")
    monkeypatch.setattr("claxcode.cli.auto_memory", mem)
    cli = InteractiveCLI(".")
    cli._quick_memory("用户偏好简洁回答")
    assert "已记住" in capsys.readouterr().out
    assert "用户偏好简洁回答" in mem.items().values()


async def test_run_shell_inline_executes(capsys):
    cli = InteractiveCLI(".")
    await cli._run_shell_inline("echo hello-claxcode")
    assert "hello-claxcode" in capsys.readouterr().out
