"""Interactive CLI for ClaxCode — terminal-based agentic coding assistant."""

# Load .env BEFORE importing settings so that pydantic picks up the values
import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from dotenv import load_dotenv

# Try common .env locations
for _env_path in [Path(".env").resolve(), Path.home() / ".claxcode" / ".env"]:
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
        break

# Ensure all built-in tools are registered
import claxcode.tools  # noqa: F401
from claxcode.config import settings
from claxcode.core.agent import Agent
from claxcode.core.checkpoint import CheckpointManager
from claxcode.core.models import get_provider
from claxcode.extensions.skills import SkillManager
from claxcode.memory import (
    init_db,
    long_term_memory,
    project_memory,
)
from claxcode.memory.auto_memory import auto_memory
from claxcode.memory.project_context import load_project_context
from claxcode.memory.session_store import get_session_messages, save_session_messages
from claxcode.security.audit import audit_logger
from claxcode.tools.registry import registry


@dataclass
class SlashCommand:
    """A built-in CLI command."""

    usage: str
    description: str
    handler: Callable[[list[str]], Awaitable[bool]]  # returns True to exit the REPL


class InteractiveCLI:
    """REPL-style interactive CLI."""

    def __init__(self, project_path: str = ".", permission_mode: str = "ask"):
        self.session_id = uuid4()
        self.project_path = Path(project_path).resolve()
        self.permission_mode = permission_mode
        self._auto_approved: set[str] = set()
        self.agent: Agent | None = None
        self.skill_manager = SkillManager()
        self._load_skills()
        self._command_table = self._build_commands()

    def _load_skills(self) -> None:
        """Load built-in, user-global and project skills."""
        self.skill_manager.load_defaults(self.project_path)

    async def run(self) -> None:
        # 初始化数据库
        await init_db()

        print("🚀 ClaxCode")
        print(f"📁 项目路径: {self.project_path}")
        print(f"🔧 权限模式: {self.permission_mode}")
        print(f"🧠 已加载技能: {len(self.skill_manager.skills)}")
        print(f"🤖 LLM 提供商: {settings.llm_provider}")
        print(f"📝 LLM 模型: {settings.llm_model}")
        print(f"🔑 API 密钥: {'已设置' if settings.llm_api_key else '未设置'}")
        print(f"🐛 调试模式: {'开启' if settings.debug else '关闭'}")
        print(f"⏱️  工具超时: {settings.tool_timeout}秒")
        print('输入 "/help" 查看命令，"/exit" 退出。\n')

        self.agent = Agent(
            session_id=self.session_id,
            project_path=str(self.project_path),
            permission_mode=self.permission_mode,
            approval_callback=self._approve_tool,
        )
        skills_prompt = self.skill_manager.to_prompt_fragment()
        if skills_prompt:
            self.agent.context.add_message("system", f"\n\n{skills_prompt}")

        restored = await self._resume_session()
        if restored:
            print(f"💾 已恢复上次会话（{restored} 条消息），输入 /clear 可重新开始。\n")

        while True:
            try:
                user_input = await self._read_input()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 再见！")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                should_exit = await self._handle_command(user_input)
                if should_exit:
                    break
            elif user_input.startswith("!"):
                await self._run_shell_inline(user_input[1:].strip())
            elif user_input.startswith("#"):
                self._quick_memory(user_input[1:].strip())
            else:
                await self._chat(self._expand_mentions(user_input))

    async def _read_input(self, prompt: str = "❯ ") -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: input(prompt))

    async def _approve_tool(self, tool_name: str, args: dict[str, Any]) -> bool:
        """Prompt the user to approve a tool call in ask mode."""
        if tool_name in self._auto_approved:
            return True
        args_preview = json.dumps(args, ensure_ascii=False)[:200]
        print(f"\n🔐 权限请求: {tool_name}({args_preview})")
        try:
            answer = (await self._read_input("   允许? [y]es / [a]lways / [N]o: ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if answer == "a":
            self._auto_approved.add(tool_name)
            return True
        return answer in ("y", "yes")

    async def _resume_session(self) -> int:
        """Resume the previous CLI session for this project. Returns messages restored."""
        state_file = self.project_path / ".claxcode" / "cli_session"
        if state_file.exists():
            with suppress(ValueError):  # 损坏的状态文件：沿用新会话 ID
                self.session_id = UUID(state_file.read_text(encoding="utf-8").strip())
        else:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(str(self.session_id), encoding="utf-8")

        if self.agent is None:
            return 0
        self.agent.session_id = self.session_id
        saved = await get_session_messages(self.session_id)
        if saved:
            self.agent.context.restore(saved)
        return len(saved)

    async def _persist_session(self) -> None:
        """Persist the conversation (minus the system prompt) for later resume."""
        if self.agent is None:
            return
        with suppress(Exception):  # 持久化失败不应影响交互
            await save_session_messages(self.session_id, self.agent.context.messages[1:])

    async def _chat(self, message: str) -> None:
        if self.agent is None:
            return
        print()

        # 导入工具取消控制
        from claxcode.tools.execution import set_tool_cancelled

        try:
            async for event in self.agent.run(message):
                etype = event.get("type")
                if etype == "thinking":
                    print(f"💭 {event['content']}")
                elif etype == "message_delta":
                    print(event["content"], end="", flush=True)
                elif etype == "tool_call":
                    print(f"\n🔧 调用工具: {event['name']}({json.dumps(event.get('arguments', {}))})")
                    print("   (按 Ctrl+C 中止工具执行)")
                elif etype == "tool_result":
                    print(f"📋 结果:\n{event['output'][:500]}{'...' if len(event['output']) > 500 else ''}")
                elif etype == "debug":
                    self._print_debug(event)
                elif etype == "done":
                    print("\n")
        except KeyboardInterrupt:
            # 用户按 Ctrl+C，尝试取消工具执行
            set_tool_cancelled()
            print("\n\n⏹️  已请求中止工具执行...")
            # 给工具一些时间来响应取消
            await asyncio.sleep(0.5)
            print("📝 当前操作已中止。您可以继续输入新的指令。\n")
        finally:
            await self._persist_session()

    async def _handle_command(self, command: str) -> bool:
        parts = command.split()
        cmd, args = parts[0].lower(), parts[1:]

        entry = self._command_table.get(cmd)
        if entry is not None:
            return await entry.handler(args)

        skill_cmd = self.skill_manager.find_command(cmd.lstrip("/"))
        if skill_cmd is not None:
            await self._run_skill_command(skill_cmd, args)
            return False

        print(f"❓ 未知命令: {cmd}。输入 /help 查看可用命令。\n")
        return False

    def _build_commands(self) -> dict[str, SlashCommand]:
        """Build the slash-command dispatch table (also the source of /help)."""
        return {
            "/help": SlashCommand("/help", "显示帮助信息", self._cmd_help),
            "/tools": SlashCommand("/tools", "列出可用工具", self._cmd_tools),
            "/mode": SlashCommand(
                "/mode <mode>", "设置权限模式 (ask|auto_edit|plan|auto_safe|yolo)", self._cmd_mode
            ),
            "/skills": SlashCommand("/skills [reload|create]", "技能管理", self._cmd_skills),
            "/config": SlashCommand("/config", "显示当前 LLM 配置", self._cmd_config),
            "/debug": SlashCommand("/debug", "切换调试模式", self._cmd_debug),
            "/clear": SlashCommand("/clear", "清除对话上下文", self._cmd_clear),
            "/project": SlashCommand("/project [list|switch|info]", "项目管理", self._cmd_project),
            "/memory": SlashCommand(
                "/memory [list|search|learn|forget|facts|...]", "记忆管理", self._cmd_memory
            ),
            "/init": SlashCommand("/init", "初始化项目信息", self._cmd_init),
            "/compact": SlashCommand("/compact", "压缩会话到长期记忆", self._cmd_compact),
            "/audit": SlashCommand("/audit [n]", "查看最近 n 条审计日志", self._cmd_audit),
            "/rollback": SlashCommand("/rollback [n|list]", "回滚文件编辑快照", self._cmd_rollback),
            "/exit": SlashCommand("/exit, /quit", "退出 ClaxCode", self._cmd_exit),
            "/quit": SlashCommand("/exit, /quit", "退出 ClaxCode", self._cmd_exit),
        }

    async def _run_skill_command(self, skill_cmd: dict[str, str], args: list[str]) -> None:
        """Route a skill-defined command to the agent as an instruction."""
        request = " ".join(args) if args else skill_cmd["description"]
        prompt = f"使用 {skill_cmd['skill']} 技能的 {skill_cmd['name']} 命令：{request}"
        await self._chat(prompt)

    async def _run_shell_inline(self, command: str) -> None:
        """Run a shell command directly (input prefixed with '!')."""
        if not command:
            return
        tool = registry.get("run_shell")
        if tool is None:
            print("❌ run_shell 工具不可用。\n")
            return
        print(f"$ {command}")
        result = await tool.execute(command=command, cwd=str(self.project_path))
        print(f"{result}\n")

    def _quick_memory(self, text: str) -> None:
        """Store a quick note into auto memory (input prefixed with '#')."""
        if not text:
            return
        key = f"note_{datetime.now():%Y%m%d_%H%M%S}"
        print(f"✅ {auto_memory.remember(key, text)}（可用 /memory forget {key} 删除）\n")

    def _expand_mentions(self, text: str) -> str:
        """Inline @path file contents into the message (up to 8000 chars each)."""
        blocks = []
        for token in text.split():
            if not token.startswith("@") or len(token) < 2:
                continue
            path = (self.project_path / token[1:]).resolve()
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            blocks.append(f"\n\n[文件 {token[1:]} 的内容]\n```\n{content[:8000]}\n```")
        return text + "".join(blocks)

    async def one_shot(self, prompt: str) -> None:
        """Run a single prompt non-interactively (content to stdout)."""
        await init_db()
        self.agent = Agent(
            session_id=self.session_id,
            project_path=str(self.project_path),
            permission_mode=self.permission_mode,
        )
        async for event in self.agent.run(self._expand_mentions(prompt)):
            etype = event.get("type")
            if etype == "message_delta":
                print(event["content"], end="", flush=True)
            elif etype in ("tool_call", "tool_result"):
                print(f"[{etype}] {event.get('name')}", file=sys.stderr)
        print()
        await self._persist_session()

    async def _cmd_help(self, args: list[str]) -> bool:
        self._print_help()
        return False

    async def _cmd_tools(self, args: list[str]) -> bool:
        self._print_tools()
        return False

    async def _cmd_mode(self, args: list[str]) -> bool:
        self._set_mode(args)
        return False

    async def _cmd_skills(self, args: list[str]) -> bool:
        if args and args[0] == "reload":
            await self._reload_skills()
        elif args and args[0] == "create":
            await self._create_skill(args[1:])
        else:
            self._print_skills()
        return False

    async def _cmd_config(self, args: list[str]) -> bool:
        self._print_config()
        return False

    async def _cmd_debug(self, args: list[str]) -> bool:
        self._toggle_debug()
        return False

    async def _cmd_clear(self, args: list[str]) -> bool:
        if self.agent:
            self.agent.context.clear()
        await self._persist_session()
        print("🧹 上下文已清除。\n")
        return False

    async def _cmd_project(self, args: list[str]) -> bool:
        await self._handle_project_command(args)
        return False

    async def _cmd_memory(self, args: list[str]) -> bool:
        await self._handle_memory_command(args)
        return False

    async def _cmd_init(self, args: list[str]) -> bool:
        await self._handle_init_command()
        return False

    async def _cmd_compact(self, args: list[str]) -> bool:
        await self._handle_compact_command()
        return False

    async def _cmd_audit(self, args: list[str]) -> bool:
        limit = int(args[0]) if args and args[0].isdigit() else 10
        entries = audit_logger.read_recent(limit)
        if not entries:
            print("ℹ️ 暂无审计日志。\n")
            return False
        print(f"\n📜 最近 {len(entries)} 条审计日志:")
        for e in entries:
            mark = "✅" if e["allowed"] else "⛔"
            print(f"  {mark} [{e['timestamp'][:19]}] {e['tool_name']} — {e['result_preview'][:60]}")
        print()
        return False

    async def _cmd_rollback(self, args: list[str]) -> bool:
        mgr = self.agent.checkpoint if self.agent else CheckpointManager()
        if args and args[0] == "list":
            return self._print_snapshots(mgr.list_snapshots(self.session_id))

        steps = int(args[0]) if args and args[0].isdigit() else 1
        batches = mgr.list_snapshots(self.session_id, limit=steps)
        if not batches:
            print("ℹ️ 没有可回滚的快照。\n")
            return False
        prompt = f"⚠️ 将回滚最近 {len(batches)} 个快照，确认? [y/N] "
        try:
            answer = (await self._read_input(prompt)).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if answer not in ("y", "yes"):
            print("已取消。\n")
            return False
        restored = mgr.restore(self.session_id, steps=steps)
        print(f"✅ 已恢复 {len(restored)} 个文件:")
        for p in restored:
            print(f"  • {p}")
        print()
        return False

    def _print_snapshots(self, batches: list[dict]) -> bool:
        if not batches:
            print("ℹ️ 没有可用的快照。\n")
            return False
        print(f"\n📸 最近 {len(batches)} 个快照:")
        for i, b in enumerate(batches, 1):
            files = ", ".join(b["files"][:3])
            print(f"  {i}. [{b['timestamp']}] {files}")
        print()
        return False

    async def _cmd_exit(self, args: list[str]) -> bool:
        print("👋 再见！")
        return True

    async def _create_skill(self, args: list[str]) -> None:
        """创建规范格式的 Skill 目录。"""
        if not args:
            print("❌ 用法: /skills create <skill-name>\n")
            return
        name = args[0]
        skill_dir = self.project_path / ".claxcode" / "skills" / name
        if skill_dir.exists():
            print(f"❌ Skill '{name}' 已存在。\n")
            return
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            f"""# {name}

## Description
简要描述此 Skill 的功能和用途。

## Instructions
详细说明 Agent 应如何使用此 Skill。
可以包含示例、约定、文件模式等。

## Commands (可选)
- `example_cmd`: 命令描述

## Notes
其他补充说明。
""",
            encoding="utf-8",
        )

        tools_py = skill_dir / "tools.py"
        tools_py.write_text(
            f'''"""Tools for {name} skill.

在此文件中定义 Skill 专属的工具，使用 @tool 装饰器自动注册。
"""

from claxcode.tools.base import Tool
from claxcode.tools.registry import tool


# @tool
# class ExampleTool(Tool):
#     name = "example_tool"
#     description = "An example tool."
#     input_schema = {{
#         "type": "object",
#         "properties": {{"arg": {{"type": "string"}}}},
#         "required": ["arg"],
#     }}
#     category = "{name}"
#     required_permissions = []
#
#     async def execute(self, arg: str, **kwargs) -> str:
#         return f"Result: {{arg}}"
''',
            encoding="utf-8",
        )

        print(f"✅ Skill '{name}' 已创建!")
        print(f"   路径: {skill_dir}")
        print("   文件: SKILL.md, tools.py")
        print("   编辑后运行 '/skills reload' 生效。\n")

    def _print_help(self) -> None:
        print("\n命令列表:")
        seen: set[str] = set()
        for entry in self._command_table.values():
            if entry.usage in seen:
                continue
            seen.add(entry.usage)
            print(f"  {entry.usage:<38} {entry.description}")

        skill_cmds = self.skill_manager.get_skill_commands()
        if skill_cmds:
            print("\n技能命令:")
            for c in skill_cmds:
                print(f"  /{c['name']:<37} {c['description']}  (技能: {c['skill']})")
        print("\n其他输入将发送给智能助手。\n")

    def _print_tools(self) -> None:
        print("\n可用工具:")
        for tool in registry.list_tools():
            print(f"  • {tool.name} ({tool.category}) — {tool.description}")
        print()

    def _set_mode(self, args: list[str]) -> None:
        modes = ["ask", "auto_edit", "plan", "auto_safe", "yolo"]
        if not args:
            mode = self._interactive_select(modes, prompt="选择模式:")
            if mode is None:
                print("  已取消。\n")
                return
        else:
            mode = args[0].lower()
            if mode not in modes:
                print("❌ 无效模式。可选: ask, auto_edit, plan, auto_safe, yolo\n")
                return
        self.permission_mode = mode
        self._auto_approved.clear()
        if self.agent:
            self.agent.permission_mode = mode
        print(f"✅ 模式已设置为: {mode}\n")

    def _interactive_select(self, options: list[str], prompt: str = "选择:") -> str | None:
        """Show an inline arrow-key selector. Returns the chosen option or None if cancelled."""
        import sys  # noqa: F811

        idx = options.index(self.permission_mode) if self.permission_mode in options else 0
        prefix = f"{prompt} "
        # Print initial line
        print(f"{prefix}{options[idx]}  [←↑↓→ 移动, Enter 确认, Esc 取消]", end="", flush=True)

        if sys.platform == "win32":
            import msvcrt

            while True:
                key = msvcrt.getch()
                if key == b"\r":  # Enter
                    print()
                    return options[idx]
                if key == b"\x1b":  # Esc
                    print()
                    return None
                if key == b"\xe0":  # Arrow-key prefix on Windows
                    key2 = msvcrt.getch()
                    if key2 == b"H":  # Up
                        idx = (idx - 1) % len(options)
                    elif key2 == b"P":  # Down
                        idx = (idx + 1) % len(options)
                    elif key2 == b"K":  # Left
                        idx = (idx - 1) % len(options)
                    elif key2 == b"M":  # Right
                        idx = (idx + 1) % len(options)
                # Clear to end of line and reprint
                print(f"\r{prefix}{options[idx]}  [←↑↓→ 移动, Enter 确认, Esc 取消]", end="", flush=True)
        else:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                while True:
                    ch = sys.stdin.read(1)
                    if ch == "\r":
                        print()
                        return options[idx]
                    if ch == "\x1b":
                        seq = sys.stdin.read(2)
                        if seq == "[A":  # Up
                            idx = (idx - 1) % len(options)
                        elif seq == "[B":  # Down
                            idx = (idx + 1) % len(options)
                        elif seq == "[D":  # Left
                            idx = (idx - 1) % len(options)
                        elif seq == "[C":  # Right
                            idx = (idx + 1) % len(options)
                    print(f"\r{prefix}{options[idx]}  [←↑↓→ 移动, Enter 确认, Esc 取消]", end="", flush=True)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def _print_config(self) -> None:
        print(f"""
配置信息:
  LLM_PROVIDER:     {settings.llm_provider}
  LLM_MODEL:        {settings.llm_model}
  LLM_BASE_URL:     {settings.llm_base_url or '(默认)'}
  LLM_TEMPERATURE:  {settings.llm_temperature}
  LLM_MAX_TOKENS:   {settings.llm_max_tokens}
  API_KEY 状态:     {'已设置' if settings.llm_api_key else '未设置'}
  数据库:           {settings.database_url}
  权限模式:         {self.permission_mode}
  调试模式:         {'开启' if self.agent and self.agent.debug else '关闭'}
  工具超时:         {settings.tool_timeout}秒
""")

    async def _handle_project_command(self, args: list[str]) -> None:
        """处理 /project 命令."""
        subcmd = args[0] if args else "info"

        if subcmd == "list":
            projects = await project_memory.list_all_projects()
            if not projects:
                print("ℹ️ 没有找到已初始化的项目。\n")
                return
            print("\n📁 已初始化的项目:")
            for p in projects:
                name = p.get("name", "未知")
                path = p.get("project_path", "")
                updated = p.get("updated_at", "")[:10]
                has_summary = "✓" if p.get("has_summary") else " "
                print(f"  [{has_summary}] {name}")
                print(f"      路径: {path}")
                print(f"      更新: {updated}")
            print()

        elif subcmd == "switch":
            if len(args) < 2:
                print("❌ 用法: /project switch <项目路径>\n")
                return
            new_path = args[1]
            path_obj = Path(new_path).resolve()
            if not path_obj.exists():
                print(f"❌ 路径不存在: {new_path}\n")
                return
            self.project_path = path_obj
            # 重新加载技能和上下文
            self._load_skills()
            if self.agent:
                self.agent.project_path = str(self.project_path)
            print(f"✅ 已切换到项目: {self.project_path}\n")

        elif subcmd == "info":
            # 显示当前项目信息
            project = await project_memory.get_project(str(self.project_path))
            if project:
                config = project.get("config", {})
                print("\n📁 项目信息:")
                print(f"  名称: {config.get('name', '未命名')}")
                print(f"  路径: {project.get('project_path', '')}")
                print(f"  描述: {config.get('description', '无')}")
                print(f"  技术栈: {config.get('tech_stack', '未指定')}")
                print(f"  初始化时间: {project.get('initialized_at', '')[:10]}")
                if project.get("context_summary"):
                    print(f"  摘要: {project['context_summary'][:100]}...")
                print()
            else:
                # 显示 CLAUDE.md 或提示未初始化
                ctx = load_project_context(self.project_path)
                if ctx:
                    print(f"📄 项目上下文:\n{ctx}\n")
                else:
                    print("ℹ️ 项目未初始化。使用 /init 初始化项目。\n")

        else:
            print(f"❓ 未知子命令: {subcmd}。用法: /project [list|switch|info]\n")

    async def _handle_memory_command(self, args: list[str]) -> None:
        """处理 /memory 命令."""
        subcmd = args[0] if args else "list"

        if subcmd == "list":
            memories = await long_term_memory.list_all(limit=20)
            if not memories:
                print("ℹ️ 长期记忆为空。\n")
                return
            print("\n🧠 长期记忆:")
            for m in memories:
                ts = m.get("timestamp", "")[:10]
                keywords = ", ".join(m.get("keywords", [])[:5])
                content = m.get("compressed_content", "")[:80]
                print(f"  [{ts}] {keywords}")
                print(f"      {content}...")
            print()

        elif subcmd == "search":
            if len(args) < 2:
                print("❌ 用法: /memory search <关键词>\n")
                return
            keywords = args[1:]
            memories = await long_term_memory.search(
                keywords=keywords,
                project_path=str(self.project_path),
                limit=10
            )
            if not memories:
                print(f"ℹ️ 未找到包含关键词 '{', '.join(keywords)}' 的记忆。\n")
                return
            print(f"\n🔍 搜索结果 ({len(memories)} 条):")
            for m in memories:
                ts = m.get("timestamp", "")[:10]
                kw = ", ".join(m.get("keywords", []))
                print(f"  [{ts}] {kw}")
                print(f"      {m.get('compressed_content', '')[:100]}...")
            print()

        elif subcmd == "export":
            filepath = args[1] if len(args) > 1 else "memories_export.json"
            count = await long_term_memory.export_to_file(
                filepath,
                project_path=str(self.project_path)
            )
            print(f"✅ 已导出 {count} 条记忆到: {filepath}\n")

        elif subcmd == "import":
            if len(args) < 2:
                print("❌ 用法: /memory import <文件路径>\n")
                return
            filepath = args[1]
            try:
                count = await long_term_memory.import_from_file(filepath)
                print(f"✅ 已导入 {count} 条记忆。\n")
            except Exception as e:
                print(f"❌ 导入失败: {e}\n")

        elif subcmd == "delete":
            if len(args) < 2:
                print("❌ 用法: /memory delete <记忆ID>\n")
                return
            memory_id = args[1]
            success = await long_term_memory.delete(memory_id)
            if success:
                print(f"✅ 已删除记忆: {memory_id}\n")
            else:
                print(f"❌ 未找到记忆: {memory_id}\n")

        elif subcmd == "learn":
            if len(args) < 3:
                print("❌ 用法: /memory learn <键> <值>\n")
                return
            print(f"✅ {auto_memory.remember(args[1], ' '.join(args[2:]))}\n")

        elif subcmd == "forget":
            if len(args) < 2:
                print("❌ 用法: /memory forget <键>\n")
                return
            if auto_memory.forget(args[1]):
                print(f"✅ 已遗忘: {args[1]}\n")
            else:
                print(f"❌ 未找到: {args[1]}\n")

        elif subcmd == "facts":
            facts = auto_memory.items()
            if not facts:
                print("ℹ️ 自动记忆为空。可用 /memory learn <键> <值> 添加。\n")
                return
            print(f"\n🧠 自动记忆 ({len(facts)} 条):")
            for k, v in facts.items():
                print(f"  • {k}: {v}")
            print()

        else:
            print(f"❓ 未知子命令: {subcmd}。用法: /memory [list|search|learn|forget|facts|...]\n")

    async def _handle_init_command(self) -> None:
        """处理 /init 命令 - 初始化项目."""
        print("\n📝 初始化项目信息")
        print("-" * 40)

        # 交互式收集信息
        loop = asyncio.get_event_loop()

        name = await loop.run_in_executor(
            None,
            lambda: input(f"项目名称 [{self.project_path.name}]: ")
        ) or self.project_path.name

        description = await loop.run_in_executor(
            None,
            lambda: input("项目描述: ")
        )

        tech_stack = await loop.run_in_executor(
            None,
            lambda: input("技术栈 (如: Python, FastAPI, React): ")
        )

        build_command = await loop.run_in_executor(
            None,
            lambda: input("构建命令 (如: npm run build): ")
        )

        test_command = await loop.run_in_executor(
            None,
            lambda: input("测试命令 (如: pytest): ")
        )

        code_style = await loop.run_in_executor(
            None,
            lambda: input("代码风格偏好: ")
        )

        notes = await loop.run_in_executor(
            None,
            lambda: input("其他说明: ")
        )

        config = {
            "name": name,
            "description": description,
            "tech_stack": tech_stack,
            "build_command": build_command,
            "test_command": test_command,
            "code_style": code_style,
            "notes": notes,
        }

        # 保存到数据库
        memory_id = await project_memory.init_project(
            str(self.project_path),
            config
        )

        # 生成 CLAUDE.md 文件
        context_file = self.project_path / "CLAUDE.md"
        content = project_memory.generate_context_md(config)
        context_file.write_text(content, encoding="utf-8")

        print("\n✅ 项目已初始化!")
        print(f"   ID: {memory_id}")
        print(f"   CLAUDE.md 已创建: {context_file}\n")

    async def _handle_compact_command(self) -> None:
        """处理 /compact 命令 - 压缩会话."""
        if not self.agent:
            print("❌ 代理未初始化。\n")
            return

        print("\n🗜️  正在压缩会话...")

        # 获取当前会话的消息
        messages = self.agent.context.get_messages()
        if len(messages) <= 2:  # 只有系统提示和少量消息
            print("ℹ️ 会话内容太少，无需压缩。\n")
            return

        # 构建需要总结的内容
        content_parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                content_parts.append(f"{role}: {content}")

        full_content = "\n\n".join(content_parts)

        if len(full_content) < 200:
            print("ℹ️ 会话内容太少，无需压缩。\n")
            return

        # 使用 LLM 进行总结
        try:
            provider = get_provider()
            summary_prompt = f"""请总结以下对话内容，提取关键信息：

{full_content[:8000]}

请提供：
1. 主要讨论的主题（关键词列表）
2. 核心内容的简洁总结（200字以内）

格式：
关键词: keyword1, keyword2, keyword3
总结: ..."""

            summary_response = ""
            async for chunk in provider.stream_chat(
                messages=[{"role": "user", "content": summary_prompt}],
                tools=None
            ):
                if isinstance(chunk, str):
                    summary_response += chunk

            # 解析总结结果
            keywords = []
            summary = summary_response

            if "关键词:" in summary_response:
                parts = summary_response.split("总结:", 1)
                kw_part = parts[0].replace("关键词:", "").strip()
                keywords = [k.strip() for k in kw_part.split(",") if k.strip()]
                if len(parts) > 1:
                    summary = parts[1].strip()

            # 保存到长期记忆
            memory_id = await long_term_memory.save(
                session_id=str(self.session_id),
                compressed_content=summary,
                keywords=keywords,
                project_path=str(self.project_path),
            )

            # 清空当前会话上下文（保留系统提示）
            self.agent.context.clear()

            # 添加压缩后的记忆作为上下文
            memory_summary = f"[历史会话总结] {summary[:200]}..."
            self.agent.context.add_message("system", memory_summary)

            print("✅ 会话已压缩并保存!")
            print(f"   记忆ID: {memory_id}")
            print(f"   关键词: {', '.join(keywords[:5])}")
            print(f"   总结: {summary[:100]}...\n")

        except Exception as e:
            print(f"❌ 压缩失败: {e}\n")

    def _toggle_debug(self) -> None:
        if self.agent is None:
            return
        self.agent.debug = not self.agent.debug
        state = "开启" if self.agent.debug else "关闭"
        print(f"🐛 调试模式: {state}\n")

    def _print_debug(self, event: dict) -> None:
        label = event.get("label", "调试")
        payload = event.get("payload", {})
        print(f"\n{'─' * 60}")
        print(f"🐛 调试 — {label}")
        print(f"{'─' * 60}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"{'─' * 60}\n")

    async def _reload_skills(self) -> None:
        """热重载所有技能。"""
        count, tools_count = self.skill_manager.reload_all()
        # 重新注入到 agent 上下文
        if self.agent:
            skills_prompt = self.skill_manager.to_prompt_fragment()
            if skills_prompt:
                self.agent.context.add_message("system", f"\n\n{skills_prompt}")
        print(f"✅ 已重载 {count} 个技能，注册 {tools_count} 个工具。\n")

    def _print_skills(self) -> None:
        if not self.skill_manager.skills:
            print("ℹ️ 未加载任何技能。\n")
            return
        print("\n已加载的技能:")
        for skill in self.skill_manager.skills:
            tools_info = f" (+{len(skill.registered_tools)} 工具)" if skill.registered_tools else ""
            print(f"  • {skill.name} [{skill.source}]{tools_info} — {skill.description}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="ClaxCode 交互式命令行")
    parser.add_argument("--project", "-p", default=".", help="项目目录")
    parser.add_argument(
        "--mode", "-m", default="ask",
        choices=["ask", "auto_edit", "plan", "auto_safe", "yolo"],
    )
    parser.add_argument("--env", "-e", default=None, help=".env 文件路径")
    parser.add_argument(
        "--print", "-P", dest="one_shot", default=None, metavar="PROMPT",
        help="非交互模式：执行单条指令后退出（工具日志走 stderr）",
    )
    args = parser.parse_args()

    project_path = Path(args.project).resolve()

    # Allow explicit .env override
    if args.env:
        env_file = Path(args.env)
        if env_file.exists():
            load_dotenv(env_file, override=True)
        else:
            print(f"⚠️ 未找到环境文件: {env_file}")

    cli = InteractiveCLI(project_path=str(project_path), permission_mode=args.mode)
    if args.one_shot:
        asyncio.run(cli.one_shot(args.one_shot))
    else:
        asyncio.run(cli.run())


if __name__ == "__main__":
    main()
