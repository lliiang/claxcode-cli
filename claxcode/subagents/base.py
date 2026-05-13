"""Base subagent with isolated context and restricted tools."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from claxcode.core.agent import DEFAULT_SYSTEM_PROMPT
from claxcode.core.context import ContextManager
from claxcode.core.models import get_provider
from claxcode.tools.registry import registry


class Subagent:
    """Isolated subagent for delegated tasks."""

    def __init__(
        self,
        session_id: UUID,
        agent_type: str,
        instruction: str,
        allowed_tools: list[str] | None = None,
        max_iterations: int = 5,
    ):
        self.id = uuid4()
        self.session_id = session_id
        self.agent_type = agent_type
        self.instruction = instruction
        self.allowed_tools = allowed_tools
        self.max_iterations = max_iterations
        self.provider = get_provider()
        self.context = ContextManager(
            system_prompt=f"{DEFAULT_SYSTEM_PROMPT}\n\n你是一个 {agent_type} 子代理。"
            f"专注于你的专业领域并简洁地报告发现。"
        )

    async def run(self) -> AsyncIterator[dict[str, Any]]:
        """Run the subagent and stream progress events."""
        yield {"type": "status", "status": "running"}
        self.context.add_message("user", self.instruction)

        for i in range(self.max_iterations):
            tools = self._build_tools()
            content_buffer = ""
            pending_tool_calls = []

            async for chunk in self.provider.stream_chat(
                messages=self.context.get_messages(),
                tools=tools if tools else None,
            ):
                if isinstance(chunk, str):
                    content_buffer += chunk
                elif isinstance(chunk, dict) and chunk.get("type") == "tool_call":
                    pending_tool_calls.append(chunk)

            if not pending_tool_calls:
                self.context.add_message("assistant", content_buffer)
                yield {"type": "result", "content": content_buffer}
                yield {"type": "status", "status": "completed"}
                return

            import json
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

            for tc in pending_tool_calls:
                result = await self._execute_tool(tc["name"], tc["arguments"])
                self.context.add_tool_result(tc["id"], tc["name"], result)

        final_messages = self.context.get_messages()
        final_content = "\n".join(m.get("content", "") for m in final_messages if m["role"] == "assistant")
        yield {"type": "result", "content": final_content}
        yield {"type": "status", "status": "completed"}

    def _build_tools(self) -> list[dict[str, Any]]:
        all_tools = registry.list_tools()
        if self.allowed_tools:
            all_tools = [t for t in all_tools if t.name in self.allowed_tools]
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in all_tools
        ]

    async def _execute_tool(self, name: str, args: dict) -> str:
        t = registry.get(name)
        if t is None:
            return f"错误：工具 {name} 不存在"
        try:
            return await t.execute(**args)
        except Exception as exc:
            return f"错误：{exc}"
