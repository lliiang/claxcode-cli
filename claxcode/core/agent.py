"""Agentic Loop controller."""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

from claxcode.config import settings
from claxcode.core.checkpoint import CheckpointManager
from claxcode.core.context import ContextManager
from claxcode.core.models import get_provider
from claxcode.extensions.skills import SkillManager
from claxcode.memory.project_context import load_project_context
from claxcode.tools.registry import registry


DEFAULT_SYSTEM_PROMPT = """You are ClaxCode, an agentic coding assistant.
You help users write, edit, debug, and understand code.
When you need to interact with the project, use the provided tools.
Always think step by step and explain your reasoning."""


class Agent:
    """Main agent implementing Gather -> Think -> Act -> Verify loop."""

    def __init__(
        self,
        session_id: UUID,
        project_path: str = ".",
        permission_mode: str = "ask",
        skill_manager: SkillManager | None = None,
        debug: bool | None = None,
    ):
        self.session_id = session_id
        self.project_path = Path(project_path)
        self.permission_mode = permission_mode
        self.debug = settings.debug if debug is None else debug
        self.provider = get_provider()
        self.checkpoint = CheckpointManager()
        self.max_iterations = 10

        # Build system prompt with project context and skills
        project_ctx = load_project_context(self.project_path)
        system = DEFAULT_SYSTEM_PROMPT
        if project_ctx:
            system += f"\n\n# Project Context\n{project_ctx}"

        # Auto-load skills if not provided
        if skill_manager is None:
            skill_manager = SkillManager()
            global_skills = Path.home() / ".claxcode" / "skills"
            if global_skills.exists():
                skill_manager.load_skill_dir(global_skills)
            proj_skills = self.project_path / ".claxcode" / "skills"
            if proj_skills.exists():
                skill_manager.load_skill_dir(proj_skills)
            proj_skills2 = self.project_path / "skills"
            if proj_skills2.exists():
                skill_manager.load_skill_dir(proj_skills2)

        skills_fragment = skill_manager.to_prompt_fragment()
        if skills_fragment:
            system += f"\n\n{skills_fragment}"

        self.context = ContextManager(system_prompt=system)

    async def run(self, user_message: str) -> AsyncIterator[dict]:
        """Stream agent events."""
        yield {"type": "thinking", "content": "Gathering context..."}
        self.context.add_message("user", user_message)

        for iteration in range(self.max_iterations):
            # Prepare available tools
            available_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in registry.list_tools()
            ]

            yield {"type": "thinking", "content": f"Thinking... (step {iteration + 1})"}

            messages = self.context.get_messages()

            # Debug: emit raw context
            if self.debug:
                yield {
                    "type": "debug",
                    "label": "Raw context sent to LLM",
                    "payload": {
                        "messages": messages,
                        "tools_count": len(available_tools),
                        "tools": [t["function"]["name"] for t in available_tools],
                    },
                }

            content_buffer = ""
            pending_tool_calls: list[dict] = []

            async for chunk in self.provider.stream_chat(
                messages=messages,
                tools=available_tools if available_tools else None,
            ):
                if isinstance(chunk, str):
                    content_buffer += chunk
                    yield {"type": "message_delta", "content": chunk}
                elif isinstance(chunk, dict) and chunk.get("type") == "tool_call":
                    pending_tool_calls.append(chunk)
                    yield {
                        "type": "tool_call",
                        "name": chunk["name"],
                        "arguments": chunk["arguments"],
                    }

            if not pending_tool_calls:
                # Assistant finished without tools
                self.context.add_message("assistant", content_buffer)
                if self.debug:
                    yield {
                        "type": "debug",
                        "label": "Assistant response (no tools)",
                        "payload": {"content": content_buffer},
                    }
                yield {"type": "done"}
                return

            # ACT: execute tools
            assistant_tool_calls = []
            for tc in pending_tool_calls:
                assistant_tool_calls.append(
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                )
            self.context.add_assistant_tool_calls(assistant_tool_calls)

            if self.debug:
                yield {
                    "type": "debug",
                    "label": "Tool calls from LLM",
                    "payload": {"tool_calls": pending_tool_calls},
                }

            for tc in pending_tool_calls:
                name = tc["name"]
                args = tc["arguments"]
                yield {"type": "tool_result_start", "name": name}

                result = await self._execute_tool(name, args)
                yield {"type": "tool_result", "name": name, "output": result}
                self.context.add_tool_result(tc["id"], name, result)

                if self.debug:
                    yield {
                        "type": "debug",
                        "label": f"Tool result: {name}",
                        "payload": {"arguments": args, "result": result},
                    }

            # VERIFY: lightweight step (just a thinking marker)
            yield {"type": "thinking", "content": "Verifying results..."}

        yield {"type": "done", "warning": "Max iterations reached"}

    async def _execute_tool(self, name: str, args: dict) -> str:
        tool = registry.get(name)
        if tool is None:
            return f"Error: Tool '{name}' not found"

        # Permission check
        if self.permission_mode == "plan":
            if "write" in tool.required_permissions or "execute" in tool.required_permissions:
                return f"[Blocked in plan mode] Tool '{name}' requires write/execute permission."
        # YOLO mode: execute everything without confirmation
        # (snapshot is still created for rollback safety)

        # Snapshot before file edits
        if "write" in tool.required_permissions and "path" in args:
            await self.checkpoint.snapshot(self.session_id, args["path"])

        try:
            return await tool.execute(**args)
        except Exception as exc:
            return f"Error executing {name}: {exc}"
