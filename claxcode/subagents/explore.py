"""Explore subagent — read-only codebase explorer."""

from uuid import UUID

from claxcode.subagents.base import Subagent

READONLY_TOOLS = [
    "glob_search",
    "grep_search",
    "explore_codebase",
    "read_file",
    "find_definition",
    "find_references",
]


class ExploreSubagent(Subagent):
    def __init__(self, session_id: UUID, instruction: str):
        super().__init__(
            session_id=session_id,
            agent_type="explore",
            instruction=instruction,
            allowed_tools=READONLY_TOOLS,
            max_iterations=8,
        )
