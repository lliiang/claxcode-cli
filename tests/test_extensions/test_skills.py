"""Tests for the Skills system."""

import tempfile
from pathlib import Path

import pytest

from claxcode.extensions.skills import SkillManager


@pytest.fixture
def sample_skill_dir():
    with tempfile.TemporaryDirectory() as tmp:
        skill_path = Path(tmp) / "python-refactor"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text(
            """# Python Refactoring

## Description
Expert Python refactoring assistant.

## Instructions
Use pathlib, dataclasses, and type hints.

## Commands
- `refactor_file`: Refactor a Python file
- `add_types`: Add type hints
""",
            encoding="utf-8",
        )
        yield Path(tmp)


def test_load_skill_dir(sample_skill_dir):
    mgr = SkillManager()
    mgr.load_skill_dir(sample_skill_dir)
    assert len(mgr.skills) == 1
    skill = mgr.skills[0]
    assert skill.name == "Python Refactoring"
    assert "Expert Python refactoring assistant." in skill.description
    assert len(skill.commands) == 2
    assert skill.commands[0]["name"] == "refactor_file"


def test_to_prompt_fragment(sample_skill_dir):
    mgr = SkillManager()
    mgr.load_skill_dir(sample_skill_dir)
    fragment = mgr.to_prompt_fragment()
    assert "# Skills" in fragment
    assert "Python Refactoring" in fragment
    assert "pathlib" in fragment


def test_get_skill_commands(sample_skill_dir):
    mgr = SkillManager()
    mgr.load_skill_dir(sample_skill_dir)
    cmds = mgr.get_skill_commands()
    assert len(cmds) == 2
    assert cmds[1]["name"] == "add_types"


def test_empty_manager():
    mgr = SkillManager()
    assert mgr.to_prompt_fragment() == ""
    assert mgr.get_skill_commands() == []
