"""Agentic Loop controller."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from claxcode.config import settings
from claxcode.core.checkpoint import CheckpointManager
from claxcode.core.context import ContextManager
from claxcode.core.models import get_provider
from claxcode.extensions.hooks import HookManager
from claxcode.extensions.skills import SkillManager
from claxcode.memory.auto_memory import auto_memory
from claxcode.memory.project_context import load_project_context
from claxcode.security.audit import audit_logger
from claxcode.security.permissions import PermissionMode, check_permission
from claxcode.tools.base import Tool
from claxcode.tools.execution import clear_tool_cancelled
from claxcode.tools.registry import registry

DEFAULT_SYSTEM_PROMPT = """你是 ClaxCode，一个智能编程助手。
你帮助用户编写、编辑、调试和理解代码。
当你需要与项目交互时，请使用提供的工具。
始终逐步思考并解释你的推理过程。

## 工作原则
1. 先理解后行动：改代码前先用工具读懂相关实现，不臆测路径、签名和行为。
2. 最小改动：只做任务要求的事，用最少代码、最简单实现，不顺手重构。
3. 小步验证：每完成一个改动就验证（跑测试或读回文件），再往下走。
4. 诚实汇报：没验证过的不要声称完成；遇到阻塞如实说明并给出下一步建议。"""


class Agent:
    """Main agent implementing Gather -> Think -> Act -> Verify loop."""

    def __init__(
        self,
        session_id: UUID,
        project_path: str = ".",
        permission_mode: str = "ask",
        skill_manager: SkillManager | None = None,
        debug: bool | None = None,
        approval_callback: Callable[[str, dict[str, Any]], Awaitable[bool]] | None = None,
    ):
        self.session_id = session_id
        self.project_path = Path(project_path).resolve()
        self.permission_mode = permission_mode
        self.approval_callback = approval_callback
        self.debug = settings.debug if debug is None else debug
        self.provider = get_provider()
        self.checkpoint = CheckpointManager()
        self.hooks = HookManager(self.project_path)
        self.max_iterations = 10

        # Build system prompt: system-level -> project-level -> skills
        system_prompt_path = Path.home() / ".claxcode" / "system_prompt.md"
        if system_prompt_path.exists():
            system = system_prompt_path.read_text(encoding="utf-8")
        else:
            system = DEFAULT_SYSTEM_PROMPT

        project_ctx = load_project_context(self.project_path)
        if project_ctx:
            system += f"\n\n# Project Context\n{project_ctx}"

        # Auto-load skills (built-in + user + project) if not provided
        if skill_manager is None:
            skill_manager = SkillManager()
            skill_manager.load_defaults(self.project_path)

        self._system_prompt_before_skills = system
        skills_fragment = skill_manager.to_prompt_fragment()
        if skills_fragment:
            system += f"\n\n{skills_fragment}"

        self._base_system_prompt = system
        self.context = ContextManager(system_prompt=system)

    def update_skills(self, skill_manager: SkillManager) -> None:
        """Replace the skill fragment while preserving dynamically loaded memories."""
        memory_suffix = self.context.system_prompt.removeprefix(self._base_system_prompt)
        system = self._system_prompt_before_skills
        skills_fragment = skill_manager.to_prompt_fragment()
        if skills_fragment:
            system += f"\n\n{skills_fragment}"
        self._base_system_prompt = system
        self.context.system_prompt = system + memory_suffix
        if self.context.messages and self.context.messages[0].get("role") == "system":
            self.context.messages[0]["content"] = self.context.system_prompt

    async def _load_memories(self, user_message: str) -> None:
        """Refresh scoped memories for each user message without duplicating them."""
        from claxcode.memory import long_term_memory, project_memory

        auto_fragment = auto_memory.to_prompt_fragment()
        auto_prompt = f"\n\n{auto_fragment}" if auto_fragment else ""
        fragments: list[str] = []
        project_summary = ""
        try:
            project = await project_memory.get_project(str(self.project_path))
            if project:
                project_summary = project.get("context_summary", "").strip()
            if project_summary:
                fragments.append(
                    f"\n# 项目滚动摘要（历史状态，需结合当前代码验证）\n{project_summary}"
                )

            memories = await long_term_memory.search(
                keywords=[user_message],
                project_path=str(self.project_path),
                include_global=True,
                limit=3,
            )
            if not memories:
                memories = await long_term_memory.search(
                    project_path=str(self.project_path), include_global=True, limit=2
                )
            lines = ["\n# 相关长期记忆（仅作历史参考，当前指令优先）"]
            for memory in memories:
                content = memory["compressed_content"].strip()
                if not content or content == project_summary:
                    continue
                scope = "全局" if not memory["project_path"] else "项目"
                lines.append(f"- [{scope}] {content[:400]}")
            if len(lines) > 1:
                fragments.append("\n".join(lines))
        except Exception:
            fragments = []  # 长期记忆加载失败不应阻塞主流程或全局偏好

        self.context.system_prompt = self._base_system_prompt + auto_prompt + "".join(fragments)
        if self.context.messages and self.context.messages[0].get("role") == "system":
            self.context.messages[0]["content"] = self.context.system_prompt

    async def run(self, user_message: str) -> AsyncIterator[dict]:
        """Stream agent events."""
        clear_tool_cancelled()
        await self._load_memories(user_message)

        yield {"type": "thinking", "content": "正在收集上下文..."}
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

            yield {"type": "thinking", "content": f"思考中... (步骤 {iteration + 1})"}

            if await self._compress_context_if_needed():
                yield {"type": "thinking", "content": "上下文过长，已压缩早期对话。"}

            messages = self.context.get_messages()

            # Debug: emit raw context
            if self.debug:
                yield {
                    "type": "debug",
                    "label": "发送给 LLM 的原始上下文",
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
                        "label": "助手响应（无工具调用）",
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
                    "label": "来自 LLM 的工具调用",
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
                        "label": f"工具结果: {name}",
                        "payload": {"arguments": args, "result": result},
                    }

            # VERIFY: lightweight step (just a thinking marker)
            yield {"type": "thinking", "content": "正在验证结果..."}

        yield {"type": "done", "warning": "已达到最大迭代次数"}

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        tool = registry.get(name)
        if tool is None:
            return f"错误：工具 '{name}' 不存在"

        allowed, reason = await self._check_tool_permission(tool, args)
        if not allowed:
            audit_logger.log_tool_call(
                self.session_id, name, args, f"已阻止: {reason}", allowed=False
            )
            return f"[权限阻止] 工具 '{name}': {reason}"

        hook_ok, hook_reason = await self.hooks.run_pre(name, args)
        if not hook_ok:
            audit_logger.log_tool_call(
                self.session_id, name, args, f"钩子阻止: {hook_reason}", allowed=False
            )
            return f"[钩子阻止] 工具 '{name}': {hook_reason}"

        # Snapshot before file edits (kept in every mode for rollback safety)
        if "write" in tool.required_permissions and "path" in args:
            await self.checkpoint.snapshot(self.session_id, args["path"])

        try:
            result = await tool.execute(**args)
        except Exception as exc:
            result = f"执行 {name} 时出错: {exc}"

        hook_output = await self.hooks.run_post(name, args, result)
        if hook_output:
            result += f"\n\n[Hook 输出]\n{hook_output}"

        audit_logger.log_tool_call(self.session_id, name, args, result, allowed=True)
        return result

    async def _check_tool_permission(self, tool: Tool, args: dict[str, Any]) -> tuple[bool, str]:
        """Check the permission mode; in ask mode consult the approval callback."""
        try:
            mode = PermissionMode(self.permission_mode)
        except ValueError:
            mode = PermissionMode.ASK

        allowed, reason = check_permission(mode, tool.name, tool.required_permissions)
        if allowed:
            return True, ""
        if mode == PermissionMode.ASK and self.approval_callback is not None:
            if await self.approval_callback(tool.name, args):
                return True, ""
            reason = "用户拒绝了执行"
        return False, reason

    async def _compress_context_if_needed(self) -> bool:
        """Replace the oldest half of the history with a summary when over threshold."""
        if not self.context.over_threshold():
            return False
        removed = self.context.pop_oldest(max(1, len(self.context.messages) // 2))
        summary = await self._summarize_messages(removed)
        self.context.insert_summary(summary)
        return True

    async def _summarize_messages(self, messages: list[dict[str, Any]]) -> str:
        """Summarize dropped messages with the LLM; fall back to a placeholder."""
        lines = [f"{m.get('role')}: {str(m.get('content', ''))[:500]}" for m in messages]
        prompt = (
            "请用中文简要总结以下早期对话的关键信息（用户目标、已完成的工作、"
            "重要文件路径和结论），200 字以内：\n\n" + "\n".join(lines)[:8000]
        )
        summary = ""
        try:
            async for chunk in self.provider.stream_chat(
                messages=[{"role": "user", "content": prompt}], tools=None
            ):
                if isinstance(chunk, str):
                    summary += chunk
        except Exception:
            summary = ""
        summary = summary.strip() or f"[已省略 {len(messages)} 条早期对话消息]"
        return f"[早期对话摘要]\n{summary}"
