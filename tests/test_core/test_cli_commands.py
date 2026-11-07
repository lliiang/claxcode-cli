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


async def test_version_command(capsys):
    from claxcode.cli import _get_version

    cli = InteractiveCLI(".")
    await cli._handle_command("/version")
    assert f"ClaxCode {_get_version()}" in capsys.readouterr().out


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


def test_expand_mentions_ignores_images(tmp_path):
    cli = InteractiveCLI(str(tmp_path))
    (tmp_path / "shot.png").write_bytes(b"\x89PNG-fake")
    out = cli._expand_mentions("分析 @shot.png")
    assert "```" not in out
    assert "[文件 shot.png 的内容]" not in out


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


async def test_skills_list_subcommand(capsys):
    cli = InteractiveCLI(".")
    await cli._handle_command("/skills list")
    assert "Python Refactoring" in capsys.readouterr().out


async def test_skills_unknown_subcommand(capsys):
    cli = InteractiveCLI(".")
    await cli._handle_command("/skills bogus")
    assert "未知子命令" in capsys.readouterr().out


async def test_memory_overview(capsys):
    from claxcode.memory import init_db

    await init_db()
    cli = InteractiveCLI(".")
    await cli._handle_command("/memory")
    out = capsys.readouterr().out
    assert "记忆总览" in out
    assert "长期记忆" in out
    assert "自动记忆" in out


async def test_memory_history_shows_messages(capsys):
    from uuid import uuid4

    from claxcode.core.agent import Agent

    cli = InteractiveCLI(".")
    agent = Agent(session_id=uuid4(), project_path=".")
    agent.context.add_message("user", "帮我看看上下文压缩")
    agent.context.add_message("assistant", "好的，压缩已改为 LLM 摘要")
    cli.agent = agent
    await cli._handle_command("/memory history")
    out = capsys.readouterr().out
    assert "帮我看看上下文压缩" in out
    assert "LLM 摘要" in out


async def test_memory_history_without_agent(capsys):
    cli = InteractiveCLI(".")
    await cli._handle_command("/memory history")
    assert "代理未初始化" in capsys.readouterr().out


def test_expand_mentions_supports_quotes_chinese_and_deduplicates(tmp_path):
    cli = InteractiveCLI(str(tmp_path))
    (tmp_path / "设计 说明.md").write_text("项目约定", encoding="utf-8")
    out = cli._expand_mentions('参考@"设计 说明.md"，再参考@"设计 说明.md"。')
    assert "项目约定" in out
    assert out.count("[文件 设计 说明.md 的内容]") == 1


def test_expand_mentions_supports_chinese_punctuation(tmp_path):
    cli = InteractiveCLI(str(tmp_path))
    (tmp_path / "note.py").write_text("answer = 42", encoding="utf-8")
    out = cli._expand_mentions("分析@note.py，给出建议")
    assert "answer = 42" in out


def test_expand_mentions_stays_inside_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    cli = InteractiveCLI(str(project))
    out = cli._expand_mentions("读取 @../outside.txt")
    assert "secret" not in out


def test_expand_mentions_marks_truncation(tmp_path):
    cli = InteractiveCLI(str(tmp_path))
    (tmp_path / "long.txt").write_text("长" * 8001, encoding="utf-8")
    out = cli._expand_mentions("读取 @long.txt")
    assert "[内容已截断]" in out


async def test_project_switch_recreates_prompt_session(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    cli = InteractiveCLI(str(tmp_path))
    marker = object()
    monkeypatch.setattr(cli, "_create_prompt_session", lambda: marker)
    await cli._handle_command(f"/project switch {target}")
    assert cli._prompt_session is marker


async def test_prompt_supports_multiline_and_ctrl_c_clear(tmp_path, monkeypatch):
    import asyncio

    from prompt_toolkit import PromptSession
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    with create_pipe_input() as pipe_input:
        monkeypatch.setattr(
            "claxcode.cli.PromptSession",
            lambda **kwargs: PromptSession(
                **kwargs, input=pipe_input, output=DummyOutput()
            ),
        )
        cli = InteractiveCLI(str(tmp_path))
        assert cli._prompt_session is not None
        task = asyncio.create_task(cli._prompt_session.prompt_async())
        pipe_input.send_text("会被清空\x03第一行\x1b\r第二行\r")
        assert await asyncio.wait_for(task, timeout=2) == "第一行\n第二行"


def test_quick_memory_does_not_overwrite_immediate_notes(tmp_path, monkeypatch):
    from claxcode.memory.auto_memory import AutoMemory

    mem = AutoMemory(store_path=tmp_path / "auto.json")
    monkeypatch.setattr("claxcode.cli.auto_memory", mem)
    cli = InteractiveCLI(str(tmp_path))
    cli._quick_memory("第一条")
    cli._quick_memory("第二条")
    notes = {key: value for key, value in mem.items().items() if key.startswith("note_")}
    assert len(notes) == 2
    assert set(notes.values()) == {"第一条", "第二条"}


async def test_compact_updates_rolling_summary_and_persists(tmp_path, monkeypatch):
    from claxcode.core.agent import Agent

    class FakeProvider:
        prompt = ""

        async def stream_chat(self, messages, tools):
            self.prompt = messages[0]["content"]
            yield (
                "关键词: 记忆, 压缩\n本次总结: 本轮完成记忆优化\n"
                "项目摘要: 旧架构结论；新增滚动记忆"
            )

    cli = InteractiveCLI(str(tmp_path))
    agent = Agent(session_id=cli.session_id, project_path=str(tmp_path))
    provider = FakeProvider()
    agent.provider = provider
    cli.agent = agent
    agent.context.add_message("user", "讨论记忆设计" * 30)
    agent.context.add_message("assistant", "需要区分项目摘要与长期事件" * 20)
    saved = {}
    updated = {}
    persisted = []

    async def fake_save(**kwargs):
        saved.update(kwargs)
        return "memory-id"

    async def fake_get_project(project_path):
        return {"context_summary": "旧架构结论"}

    async def fake_update_summary(project_path, summary):
        updated.update(path=project_path, summary=summary)
        return True

    async def fake_persist():
        persisted.append(True)

    monkeypatch.setattr("claxcode.cli.long_term_memory.save", fake_save)
    monkeypatch.setattr("claxcode.cli.project_memory.get_project", fake_get_project)
    monkeypatch.setattr("claxcode.cli.project_memory.update_summary", fake_update_summary)
    monkeypatch.setattr(cli, "_persist_session", fake_persist)

    await cli._handle_compact_command()

    assert "旧架构结论" in provider.prompt
    assert saved["compressed_content"] == "本轮完成记忆优化"
    assert saved["keywords"] == ["记忆", "压缩"]
    assert updated["summary"] == "旧架构结论；新增滚动记忆"
    assert len(agent.context.messages) == 1
    assert persisted == [True]


def test_split_command_preserves_quoted_and_windows_paths():
    from claxcode.cli import _split_command

    assert _split_command('/project switch "folder with spaces"') == [
        "/project", "switch", "folder with spaces"
    ]
    assert _split_command(r"/project switch C:\Project\ClaxCode") == [
        "/project", "switch", r"C:\Project\ClaxCode"
    ]


async def test_unclosed_command_quote_shows_error(capsys):
    cli = InteractiveCLI(".")
    assert await cli._handle_command('/project switch "unclosed') is False
    assert "引号不完整" in capsys.readouterr().out


async def test_project_switch_rebuilds_agent_and_restores_target(tmp_path):
    from claxcode.core.agent import Agent
    from claxcode.memory import init_db

    await init_db()
    source = tmp_path / "source"
    target = tmp_path / "target with spaces"
    source.mkdir()
    target.mkdir()
    (source / "CLAUDE.md").write_text("SOURCE_CONTEXT", encoding="utf-8")
    (target / "CLAUDE.md").write_text("TARGET_CONTEXT", encoding="utf-8")
    cli = InteractiveCLI(str(source))
    old_agent = Agent(session_id=cli.session_id, project_path=str(source))
    cli.agent = old_agent

    await cli._handle_command(f'/project switch "{target}"')

    assert cli.agent is not old_agent
    assert cli.agent is not None
    assert "TARGET_CONTEXT" in cli.agent._base_system_prompt
    assert "SOURCE_CONTEXT" not in cli.agent._base_system_prompt
    assert cli.agent.session_id == cli.session_id
    state_file = target / ".claxcode" / "cli_session"
    assert state_file.read_text(encoding="utf-8") == str(cli.session_id)


async def test_skills_reload_replaces_prompt_fragment(tmp_path):
    from claxcode.core.agent import Agent

    cli = InteractiveCLI(str(tmp_path))
    cli.agent = Agent(
        session_id=cli.session_id,
        project_path=str(tmp_path),
        skill_manager=cli.skill_manager,
    )
    before = sum(str(m.get("content", "")).count("# Skills") for m in cli.agent.context.messages)
    await cli._handle_command("/skills reload")
    after = sum(str(m.get("content", "")).count("# Skills") for m in cli.agent.context.messages)
    assert before == 1
    assert after == 1


async def test_init_cancel_preserves_existing_context(tmp_path, monkeypatch, capsys):
    context = tmp_path / "CLAUDE.md"
    context.write_text("KEEP_EXISTING_CONTEXT", encoding="utf-8")
    cli = InteractiveCLI(str(tmp_path))

    async def reject(prompt):
        return "n"

    async def fail_init(*args):
        raise AssertionError("取消时不应写入项目记忆")

    monkeypatch.setattr(cli, "_read_input", reject)
    monkeypatch.setattr("claxcode.cli.project_memory.init_project", fail_init)
    await cli._handle_command("/init")
    assert context.read_text(encoding="utf-8") == "KEEP_EXISTING_CONTEXT"
    assert "已取消" in capsys.readouterr().out


async def test_inline_shell_interrupt_returns_to_prompt(tmp_path, monkeypatch, capsys):
    class InterruptedTool:
        async def execute(self, **kwargs):
            raise KeyboardInterrupt()

    monkeypatch.setattr("claxcode.cli.registry.get", lambda name: InterruptedTool())
    cli = InteractiveCLI(str(tmp_path))
    await cli._run_shell_inline("test")
    assert "已中止命令" in capsys.readouterr().out


async def test_zero_numeric_arguments_are_rejected(capsys):
    cli = InteractiveCLI(".")
    await cli._handle_command("/rollback 0")
    await cli._handle_command("/audit 0")
    out = capsys.readouterr().out
    assert "/rollback [正整数|list]" in out
    assert "/audit [正整数]" in out


async def test_memory_list_shows_full_delete_id(tmp_path, monkeypatch, capsys):
    memory_id = "12345678-1234-5678-1234-567812345678"

    async def fake_list_all(**kwargs):
        return [{
            "id": memory_id,
            "timestamp": "2026-01-01T00:00:00",
            "project_path": "",
            "keywords": ["测试"],
            "compressed_content": "内容",
        }]

    monkeypatch.setattr("claxcode.cli.long_term_memory.list_all", fake_list_all)
    cli = InteractiveCLI(str(tmp_path))
    await cli._handle_command("/memory list")
    assert memory_id in capsys.readouterr().out


def test_expand_mentions_reports_skipped_files(tmp_path, capsys):
    project = tmp_path / "project"
    project.mkdir()
    (project / "shot.png").write_bytes(b"fake")
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    cli = InteractiveCLI(str(project))
    cli._expand_mentions("读取 @missing.py @shot.png @../outside.txt")
    err = capsys.readouterr().err
    assert "missing.py（文件不存在或不是普通文件）" in err
    assert "shot.png（当前不支持图片输入）" in err
    assert "../outside.txt（不在项目目录内）" in err


async def test_config_init_creates_global_env(tmp_path, monkeypatch, capsys):
    cli = InteractiveCLI(str(tmp_path))
    monkeypatch.setattr("claxcode.cli.Path.home", classmethod(lambda cls: tmp_path))
    answers = iter(["generic_openai", "test-model", "https://example.invalid/v1", "dummy-key"])
    password_flags = []

    async def fake_input(prompt, is_password=False):
        password_flags.append(is_password)
        return next(answers)

    monkeypatch.setattr(cli, "_read_input", fake_input)
    await cli._init_global_config()

    content = (tmp_path / ".claxcode" / ".env").read_text(encoding="utf-8")
    assert "LLM_PROVIDER=generic_openai" in content
    assert "LLM_MODEL=test-model" in content
    assert "LLM_BASE_URL=https://example.invalid/v1" in content
    assert "LLM_API_KEY=dummy-key" in content
    assert password_flags == [False, False, False, True]
    assert "dummy-key" not in capsys.readouterr().out


async def test_config_init_cancel_preserves_existing_env(tmp_path, monkeypatch):
    config_file = tmp_path / ".claxcode" / ".env"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("KEEP_EXISTING_CONFIG", encoding="utf-8")
    cli = InteractiveCLI(str(tmp_path))
    monkeypatch.setattr("claxcode.cli.Path.home", classmethod(lambda cls: tmp_path))

    async def reject(prompt, is_password=False):
        return "n"

    monkeypatch.setattr(cli, "_read_input", reject)
    await cli._init_global_config()
    assert config_file.read_text(encoding="utf-8") == "KEEP_EXISTING_CONFIG"


def test_root_init_subcommand_starts_global_config(monkeypatch):
    from claxcode.cli import main

    called = []

    async def fake_init(self):
        called.append(True)

    monkeypatch.setattr("claxcode.cli.InteractiveCLI._init_global_config", fake_init)
    monkeypatch.setattr("sys.argv", ["claxcode-cli", "init"])
    main()
    assert called == [True]
