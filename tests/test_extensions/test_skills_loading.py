"""Tests for layered skill loading (builtin/user/project) and name dedupe."""

from pathlib import Path

import claxcode.extensions.skills as skills_mod
from claxcode.extensions.skills import BUILTIN_SKILLS_DIR, SkillManager


def _make_skill(parent: Path, dirname: str, title: str) -> None:
    skill_dir = parent / dirname
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"# {title}\n\n## Description\n{title} desc.\n",
        encoding="utf-8",
    )


def test_builtin_skills_dir_loads():
    mgr = SkillManager()
    mgr.load_skill_dir(BUILTIN_SKILLS_DIR, source="builtin")
    assert any(s.name == "Python Refactoring" and s.source == "builtin" for s in mgr.skills)


def test_builtin_methodology_skills_load():
    mgr = SkillManager()
    mgr.load_skill_dir(BUILTIN_SKILLS_DIR, source="builtin")
    names = {s.name for s in mgr.skills}
    assert {"Python Refactoring", "Task Workflow", "Bug Fix", "Code Review"} <= names


def test_builtin_skill_commands_available():
    mgr = SkillManager()
    mgr.load_skill_dir(BUILTIN_SKILLS_DIR, source="builtin")
    for cmd in ("task", "plan", "fix", "review"):
        assert mgr.find_command(cmd) is not None
    assert mgr.find_command("review")["skill"] == "Code Review"


def test_same_name_skill_is_overridden_by_later_source(tmp_path):
    low = tmp_path / "low"
    high = tmp_path / "high"
    _make_skill(low, "demo", "Demo")
    _make_skill(high, "demo", "Demo")

    mgr = SkillManager()
    mgr.load_skill_dir(low, source="builtin")
    mgr.load_skill_dir(high, source="project")

    demos = [s for s in mgr.skills if s.name == "Demo"]
    assert len(demos) == 1
    assert demos[0].source == "project"


def test_load_defaults_covers_all_sources(tmp_path, monkeypatch):
    builtin = tmp_path / "pkg_skills"
    _make_skill(builtin, "a", "Alpha")
    home = tmp_path / "home"
    _make_skill(home / ".claxcode" / "skills", "b", "Beta")
    _make_skill(home / ".agent" / "skills", "b2", "Beta2")
    project = tmp_path / "project"
    _make_skill(project / ".claxcode" / "skills", "c", "Gamma")
    _make_skill(project / ".agent" / "skills", "c2", "Gamma2")
    _make_skill(project / "skills", "d", "Delta")

    monkeypatch.setattr(skills_mod, "BUILTIN_SKILLS_DIR", builtin)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    mgr = SkillManager()
    mgr.load_defaults(project)

    sources = {s.name: s.source for s in mgr.skills}
    assert sources == {
        "Alpha": "builtin",
        "Beta": "user",
        "Beta2": "user",
        "Gamma": "project",
        "Gamma2": "project",
        "Delta": "project",
    }


def test_find_command():
    mgr = SkillManager()
    mgr.load_skill_dir(BUILTIN_SKILLS_DIR, source="builtin")
    cmd = mgr.find_command("refactor_file")
    assert cmd is not None
    assert cmd["skill"] == "Python Refactoring"
    assert mgr.find_command("nonexistent") is None
