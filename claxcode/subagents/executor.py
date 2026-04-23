"""Executor subagent — full-capability multi-step task executor."""

from uuid import UUID

from claxcode.subagents.base import Subagent


class ExecutorSubagent(Subagent):
    def __init__(self, session_id: UUID, instruction: str):
        super().__init__(
            session_id=session_id,
            agent_type="executor",
            instruction=instruction,
            allowed_tools=None,  # all tools
            max_iterations=10,
        )
