"""Skills system — load and inject skill packages into agent context.

Inspired by Claude Code's Skills. A skill is a directory containing a SKILL.md
file that describes capabilities, conventions, and commands. The SKILL.md content
is injected into the agent's system prompt.

Skill directory layout:
    my-skill/
        SKILL.md          # Required: name, description, instructions
        tools.py          # Optional: skill-specific tools (auto-registered)
        (optional files)  # Templates, scripts, or reference docs

SKILL.md format:
    # Skill Name

    ## Description
    Brief explanation of what this skill does.

    ## Instructions
    Detailed instructions for the agent on how to use this skill.
    Can include examples, conventions, file patterns, etc.

    ## Commands (optional)
    - `cmd_name`: Description of what this command does

Skill sources (later overrides earlier on name conflict):
    builtin  — shipped inside the package at claxcode/skills/
    user     — ~/.claxcode/skills/ and ~/.agent/skills/
    project  — <project>/.claxcode/skills/, <project>/.agent/skills/ and <project>/skills/
"""

from dataclasses import dataclass, field
from pathlib import Path

from claxcode.tools.registry import registry

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


@dataclass
class Skill:
    """A loaded skill package."""

    name: str
    description: str
    content: str          # Full SKILL.md text
    commands: list[dict[str, str]]  # Optional custom commands
    path: Path            # Directory containing the skill
    source: str = "project"  # builtin | user | project
    registered_tools: list[str] = field(default_factory=list)


class SkillManager:
    """Load and manage skill packages."""

    def __init__(self) -> None:
        self.skills: list[Skill] = []
        self._skill_dirs: list[tuple[Path, str]] = []

    def load_defaults(self, project_path: Path) -> None:
        """Load built-in, user-global, then project skills.

        Later sources override earlier ones when skill names collide.
        """
        self.load_skill_dir(BUILTIN_SKILLS_DIR, source="builtin")
        self.load_skill_dir(Path.home() / ".claxcode" / "skills", source="user")
        self.load_skill_dir(Path.home() / ".agent" / "skills", source="user")
        self.load_skill_dir(project_path / ".claxcode" / "skills", source="project")
        self.load_skill_dir(project_path / ".agent" / "skills", source="project")
        self.load_skill_dir(project_path / "skills", source="project")

    def load_skill_dir(self, path: Path, source: str = "project") -> None:
        """Scan a directory for skill packages and load them."""
        if not path.exists():
            return
        if (path, source) not in self._skill_dirs:
            self._skill_dirs.append((path, source))
        for entry in sorted(path.iterdir()):
            if entry.is_dir() and (entry / "SKILL.md").exists():
                self._load_skill(entry, source)

    def _load_skill(self, skill_dir: Path, source: str) -> None:
        """Parse and register a single skill, replacing any same-name skill."""
        skill = self._parse_skill_md(skill_dir, source)
        self._remove_skill(skill.name)  # unregister tools of the overridden skill
        self._load_skill_tools(skill_dir, skill)
        self.skills.append(skill)

    def _parse_skill_md(self, skill_dir: Path, source: str) -> Skill:
        """Parse SKILL.md into a Skill (no side effects)."""
        raw = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

        name = skill_dir.name
        description = ""
        commands: list[dict[str, str]] = []

        # Simple parsing: extract first H1 as name, first paragraph as description
        lines = raw.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("# ") and name == skill_dir.name:
                name = line[2:].strip()
            if line.lower().startswith("## description"):
                # Collect following paragraph
                for j in range(i + 1, len(lines)):
                    if lines[j].strip() and not lines[j].startswith("##"):
                        description = lines[j].strip()
                        break
            if line.lower().startswith("## commands"):
                # Parse command list
                for j in range(i + 1, len(lines)):
                    cmd_line = lines[j].strip()
                    if cmd_line.startswith("##"):
                        break
                    if cmd_line.startswith("- "):
                        cmd_text = cmd_line[2:].strip()
                        if ":" in cmd_text:
                            cmd_name, cmd_desc = cmd_text.split(":", 1)
                            cmd_label = cmd_name.strip().strip("`")
                            commands.append({"name": cmd_label, "description": cmd_desc.strip()})

        if not description:
            # Fallback: first non-empty, non-header line
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    description = stripped
                    break

        return Skill(
            name=name,
            description=description,
            content=raw,
            commands=commands,
            path=skill_dir,
            source=source,
        )

    def _load_skill_tools(self, skill_dir: Path, skill: Skill) -> None:
        """Dynamically load tools.py from a skill directory."""
        tools_file = skill_dir / "tools.py"
        if not tools_file.exists():
            return

        before = set(registry._tools.keys())
        code = tools_file.read_text(encoding="utf-8")
        namespace = {
            "__name__": f"claxcode_skill_{skill.name}",
            "__file__": str(tools_file),
        }
        exec(compile(code, str(tools_file), "exec"), namespace)  # noqa: S102
        after = set(registry._tools.keys())
        skill.registered_tools = sorted(after - before)

    def _remove_skill(self, name: str) -> bool:
        """Remove a skill by name and unregister its tools."""
        for i, skill in enumerate(self.skills):
            if skill.name == name:
                for tool_name in skill.registered_tools:
                    registry.unregister(tool_name)
                self.skills.pop(i)
                return True
        return False

    def unload_skill(self, name: str) -> bool:
        """Unload a skill and unregister its tools."""
        return self._remove_skill(name)

    def reload_all(self) -> tuple[int, int]:
        """Unload all skills and reload from all known directories.

        Returns (skills_loaded, tools_registered).
        """
        for skill in self.skills:
            for tool_name in skill.registered_tools:
                registry.unregister(tool_name)
        self.skills.clear()

        for path, source in self._skill_dirs:
            self.load_skill_dir(path, source)
        return len(self.skills), sum(len(s.registered_tools) for s in self.skills)

    def to_prompt_fragment(self) -> str:
        """Convert all loaded skills into a system-prompt fragment."""
        if not self.skills:
            return ""
        lines = ["# Skills"]
        for skill in self.skills:
            lines.append(f"\n## {skill.name}")
            lines.append(skill.content)
        return "\n".join(lines)

    def get_skill_commands(self) -> list[dict[str, str]]:
        """Return all custom commands defined across skills (with source skill)."""
        cmds = []
        for skill in self.skills:
            for cmd in skill.commands:
                cmds.append({**cmd, "skill": skill.name})
        return cmds

    def find_command(self, name: str) -> dict[str, str] | None:
        """Find a skill command by name (without the leading slash)."""
        for cmd in self.get_skill_commands():
            if cmd["name"] == name:
                return cmd
        return None
