"""Tests for CLI input completion (@file mentions and /commands)."""

import pytest

pytest.importorskip("prompt_toolkit")
from prompt_toolkit.document import Document

from claxcode.cli_completion import CliCompleter, ProjectFileIndex, _fuzzy_match


@pytest.fixture
def project(tmp_path):
    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "src" / "core" / "agent.py").write_text("x")
    (tmp_path / "src" / "main.py").write_text("x")
    (tmp_path / "README.md").write_text("x")
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "ignored.py").write_text("x")
    return tmp_path


def _completions(completer, text):
    doc = Document(text, len(text))
    return [c.text for c in completer.get_completions(doc, None)]


def test_file_index_skips_ignored_dirs(project):
    files = ProjectFileIndex(project).files()
    assert "src/core/agent.py" in files
    assert "src/main.py" in files
    assert not any(".venv" in f for f in files)


def test_fuzzy_match():
    assert _fuzzy_match("agt", "agent.py")
    assert _fuzzy_match("scmp", "src/main.py")
    assert not _fuzzy_match("xyz", "agent.py")


def test_at_completion_matches_files(project):
    completer = CliCompleter(project, list)
    results = _completions(completer, "重构 @agent")
    assert "src/core/agent.py" in results
    assert "README.md" not in results


def test_at_completion_empty_needle_lists_files(project):
    completer = CliCompleter(project, list)
    results = _completions(completer, "@")
    assert "src/core/agent.py" in results
    assert "README.md" in results


def test_completion_keeps_at_prefix(project):
    completer = CliCompleter(project, list)
    doc = Document("@ag", 3)
    completions = list(completer.get_completions(doc, None))
    assert completions
    # start_position 只覆盖 @ 之后的部分，保留 @ 本身
    assert all(c.start_position == -2 for c in completions)


def test_command_completion_prefix(project):
    commands = [("/memory", "记忆管理"), ("/mode", "权限模式"), ("/exit", "退出")]
    completer = CliCompleter(project, lambda: commands)
    results = _completions(completer, "/mem")
    assert results == ["/memory"]


def test_command_completion_only_at_line_start(project):
    commands = [("/memory", "记忆管理")]
    completer = CliCompleter(project, lambda: commands)
    assert _completions(completer, "运行 /mem") == []


def test_no_completion_for_plain_words(project):
    completer = CliCompleter(project, list)
    assert _completions(completer, "hello wor") == []


def test_skill_commands_included(project):
    cli_commands = [("/help", "帮助")]
    skill_commands = [("/refactor_file", "重构文件")]
    completer = CliCompleter(project, lambda: cli_commands + skill_commands)
    results = _completions(completer, "/ref")
    assert results == ["/refactor_file"]


def test_mode_argument_completion(project):
    completer = CliCompleter(project, list)
    assert _completions(completer, "/mode auto_e") == ["auto_edit"]
    assert _completions(completer, "/mode ask ") == []


def test_subcommand_completion(project):
    completer = CliCompleter(project, list)
    results = _completions(completer, "/memory ")
    assert "overview" in results
    assert "learn" in results
    assert "forget" in results
    assert _completions(completer, "/config ") == []
    assert _completions(completer, "/debug ") == ["on", "off"]


def test_quoted_file_completion_supports_spaces_and_chinese(project):
    (project / "docs").mkdir()
    (project / "docs" / "设计 说明.md").write_text("x")
    completer = CliCompleter(project, list)
    doc = Document('分析@"设计 说', len('分析@"设计 说'))
    completions = list(completer.get_completions(doc, None))
    assert [c.text for c in completions] == ['docs/设计 说明.md"']
    assert completions[0].start_position == -len("设计 说")


def test_completion_after_chinese_text_but_not_email(project):
    completer = CliCompleter(project, list)
    assert "src/core/agent.py" in _completions(completer, "分析@agent")
    assert _completions(completer, "user@agent") == []


def test_file_completion_skips_unsupported_images(project):
    (project / "shot.png").write_bytes(b"fake")
    completer = CliCompleter(project, list)
    assert "shot.png" not in _completions(completer, "@shot")


def test_basename_match_ranks_before_subsequence(project):
    (project / "src" / "agent_utils.py").write_text("x")
    completer = CliCompleter(project, list)
    results = _completions(completer, "@agent")
    assert results[0] == "src/core/agent.py"
