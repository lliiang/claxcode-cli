"""Skills system — load and inject skill packages into agent context.

Inspired by Claude Code's Skills. A skill is a directory containing a SKILL.md
file that describes capabilities, conventions, and commands. The SKILL.md content
is injected into the agent's system prompt.

Skill directory layout:
    my-skill/
        SKILL.md          # Required: name, description, instructions
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
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Skill:
    """A loaded skill package."""

    name: str
    description: str
    content: str          # Full SKILL.md text
    commands: list[dict]  # Optional custom commands
    path: Path            # Directory containing the skill


class SkillManager:
    """Load and manage skill packages."""

    def __init__(self):
        self.skills: list[Skill] = []

    def load_skill_dir(self, path: Path) -> None:
        """Scan a directory for skill packages and load them."""
        if not path.exists():
            return
        for entry in sorted(path.iterdir()):
            if entry.is_dir() and (entry / "SKILL.md").exists():
                self._load_skill(entry)

    def _load_skill(self, skill_dir: Path) -> None:
        """Parse a single skill directory."""
        skill_md = skill_dir / "SKILL.md"
        raw = skill_md.read_text(encoding="utf-8")

        name = skill_dir.name
        description = ""
        commands: list[dict] = []

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
                    l = lines[j].strip()
                    if l.startswith("##"):
                        break
                    if l.startswith("- "):
                        cmd_text = l[2:].strip()
                        if ":" in cmd_text:
                            cmd_name, cmd_desc = cmd_text.split(":", 1)
                            commands.append({"name": cmd_name.strip().strip("`"), "description": cmd_desc.strip()})

        if not description:
            # Fallback: first non-empty, non-header line
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    description = stripped
                    break

        skill = Skill(
            name=name,
            description=description,
            content=raw,
            commands=commands,
            path=skill_dir,
        )
        self.skills.append(skill)

    def to_prompt_fragment(self) -> str:
        """Convert all loaded skills into a system-prompt fragment."""
        if not self.skills:
            return ""
        lines = ["# Skills"]
        for skill in self.skills:
            lines.append(f"\n## {skill.name}")
            lines.append(skill.content)
        return "\n".join(lines)

    def get_skill_commands(self) -> list[dict]:
        """Return all custom commands defined across skills."""
        cmds = []
        for skill in self.skills:
            cmds.extend(skill.commands)
        return cmds
