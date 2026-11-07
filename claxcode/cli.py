"""Interactive CLI for ClaxCode — terminal-based agentic coding assistant."""

# Load .env BEFORE importing settings so that pydantic picks up the values
import argparse
import asyncio
import json
import re
import shlex
import sys
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from dotenv import load_dotenv

# Parse --env before importing settings; all other arguments are validated in main().
_env_parser = argparse.ArgumentParser(add_help=False)
_env_parser.add_argument("--env", "-e")
_env_args, _ = _env_parser.parse_known_args()
_missing_env_file: Path | None = None
if _env_args.env:
    _env_path = Path(_env_args.env).resolve()
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
    else:
        _missing_env_file = _env_path
else:
    for _env_path in [Path(".env").resolve(), Path.home() / ".claxcode" / ".env"]:
        if _env_path.exists():
            load_dotenv(_env_path, override=True)
            break

# Ensure all built-in tools are registered
import claxcode.tools  # noqa: F401
from claxcode.config import settings
from claxcode.core.agent import Agent
from claxcode.core.checkpoint import CheckpointManager
from claxcode.core.models import PROVIDER_BASE_URLS
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

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.enums import DEFAULT_BUFFER
    from prompt_toolkit.filters import completion_is_selected, has_focus
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings

    from claxcode.cli_completion import CliCompleter
except ImportError:  # prompt_toolkit 未安装时退化为朴素 input()
    PromptSession = None  # type: ignore[assignment]
    CliCompleter = None  # type: ignore[assignment,misc]


_MENTION_RE = re.compile(r'(?<![A-Za-z0-9_@])@(?:"([^"]+)"|([^\s，。；：、！？]+))')


def _split_command(command: str) -> list[str]:
    """Split shell-like arguments without corrupting Windows backslashes."""
    parts = shlex.split(command, posix=False)
    return [
        part[1:-1]
        if len(part) >= 2 and part[0] == part[-1] and part[0] in {'"', "'"}
        else part
        for part in parts
    ]


def _get_version() -> str:
    try:
        return package_version("claxcode")
    except PackageNotFoundError:
        return "未知"


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
        self._prompt_session = self._create_prompt_session()

    def _create_prompt_session(self) -> "PromptSession[Any] | None":
        """Build the enhanced prompt, or fall back to plain input()."""
        if PromptSession is None or CliCompleter is None:
            return None
        completer = CliCompleter(self.project_path, self._completable_commands)
        history_file = self.project_path / ".claxcode" / "cli_history"
        bindings = KeyBindings()

        @bindings.add("enter", filter=has_focus(DEFAULT_BUFFER) & ~completion_is_selected)
        def _accept_input(event: Any) -> None:
            event.current_buffer.validate_and_handle()

        @bindings.add("escape", "enter")
        def _insert_newline(event: Any) -> None:
            event.current_buffer.insert_text("\n")

        @bindings.add("c-c")
        def _clear_or_exit(event: Any) -> None:
            if event.current_buffer.text:
                event.current_buffer.reset()
            else:
                event.app.exit(exception=KeyboardInterrupt())

        with suppress(Exception):
            history_file.parent.mkdir(parents=True, exist_ok=True)
            return PromptSession(
                completer=completer,
                complete_while_typing=True,
                complete_in_thread=True,
                history=FileHistory(str(history_file)),
                auto_suggest=AutoSuggestFromHistory(),
                enable_history_search=True,
                key_bindings=bindings,
                multiline=True,
                bottom_toolbar=self._bottom_toolbar,
            )
        return None

    def _bottom_toolbar(self) -> str:
        return f" {self.permission_mode} | {self.project_path.name} | /help 帮助 | Alt+Enter 换行 "

    def _completable_commands(self) -> list[tuple[str, str]]:
        """Slash commands (builtin + skill-defined) for completion."""
        items = [(name, entry.description) for name, entry in self._command_table.items()]
        items += [
            ("/" + c["name"], c["description"])
            for c in self.skill_manager.get_skill_commands()
        ]
        return items

    def _load_skills(self) -> None:
        """Load built-in, user-global and project skills."""
        self.skill_manager.load_defaults(self.project_path)

    async def run(self) -> None:
        # 初始化数据库
        await init_db()

        print(f"\n🚀 ClaxCode · {settings.llm_provider}/{settings.llm_model}")
        print(f"📁 {self.project_path} · 模式 {self.permission_mode}")
        print("💡 @ 文件 · ! 命令 · # 记忆 · /help 帮助 · Alt+Enter 换行\n")

        self.agent = Agent(
            session_id=self.session_id,
            project_path=str(self.project_path),
            permission_mode=self.permission_mode,
            skill_manager=self.skill_manager,
            approval_callback=self._approve_tool,
        )

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
                text = self._expand_mentions(user_input)
                await self._chat(text)

    async def _read_input(self, prompt: str = "❯ ", is_password: bool = False) -> str:
        if self._prompt_session is not None:
            return await self._prompt_session.prompt_async(prompt, is_password=is_password)
        if is_password:
            from getpass import getpass

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: getpass(prompt))
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
        except Exception as exc:
            print(f"\n❌ 本轮执行失败: {exc}")
            print("请检查模型配置或稍后重试；您可以继续输入。\n")
        finally:
            await self._persist_session()

    async def _handle_command(self, command: str) -> bool:
        try:
            parts = _split_command(command)
        except ValueError:
            print("❌ 命令中的引号不完整。\n")
            return False
        if not parts:
            return False
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
            "/skills": SlashCommand("/skills [list|reload|create]", "技能管理", self._cmd_skills),
            "/config": SlashCommand("/config", "显示当前 LLM 配置", self._cmd_config),
            "/version": SlashCommand("/version", "查看 ClaxCode 版本号", self._cmd_version),
            "/debug": SlashCommand("/debug", "切换调试模式", self._cmd_debug),
            "/clear": SlashCommand("/clear", "清除对话上下文", self._cmd_clear),
            "/project": SlashCommand("/project [list|switch|info]", "项目管理", self._cmd_project),
            "/memory": SlashCommand(
                "/memory [history|list|learn|forget|facts|...]", "记忆管理", self._cmd_memory
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
        try:
            result = await tool.execute(command=command, cwd=str(self.project_path))
        except KeyboardInterrupt:
            from claxcode.tools.execution import set_tool_cancelled

            set_tool_cancelled()
            print("\n⏹️ 已中止命令。\n")
            return
        print(f"{result}\n")

    def _quick_memory(self, text: str) -> None:
        """Store a quick note into auto memory (input prefixed with '#')."""
        if not text:
            return
        key = f"note_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
        print(f"✅ {auto_memory.remember(key, text)}（可用 /memory forget {key} 删除）\n")

    def _expand_mentions(self, text: str) -> str:
        """Inline distinct project text files referenced by @path or @\"path with spaces\"."""
        blocks: list[str] = []
        warnings: list[str] = []
        seen: set[Path] = set()
        for match in _MENTION_RE.finditer(text):
            quoted, unquoted = match.groups()
            relative = quoted if quoted is not None else unquoted.rstrip(",.;!?")
            path = (self.project_path / relative).resolve()
            try:
                path.relative_to(self.project_path)
            except ValueError:
                warnings.append(f"{relative}（不在项目目录内）")
                continue
            if path in seen:
                continue
            if not path.is_file():
                warnings.append(f"{relative}（文件不存在或不是普通文件）")
                continue
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
                warnings.append(f"{relative}（当前不支持图片输入）")
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                warnings.append(f"{relative}（读取失败: {exc}）")
                continue
            seen.add(path)
            truncated = "\n...[内容已截断]" if len(content) > 8000 else ""
            blocks.append(f"\n\n[文件 {relative} 的内容]\n```\n{content[:8000]}{truncated}\n```")
        for warning in dict.fromkeys(warnings):
            print(f"⚠️ 已跳过文件引用: {warning}", file=sys.stderr)
        return text + "".join(blocks)

    async def one_shot(self, prompt: str) -> None:
        """Run a single prompt non-interactively (content to stdout)."""
        await init_db()
        self.agent = Agent(
            session_id=self.session_id,
            project_path=str(self.project_path),
            permission_mode=self.permission_mode,
            skill_manager=self.skill_manager,
        )
        text = self._expand_mentions(prompt)
        async for event in self.agent.run(text):
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
        subcmd = args[0] if args else "list"
        if subcmd == "list":
            self._print_skills()
        elif subcmd == "reload":
            await self._reload_skills()
        elif subcmd == "create":
            await self._create_skill(args[1:])
        else:
            print(f"❓ 未知子命令: {subcmd}。用法: /skills [list|reload|create]\n")
        return False

    async def _cmd_config(self, args: list[str]) -> bool:
        if args:
            print("❓ 未知子命令。用法: /config\n")
        else:
            self._print_config()
        return False

    async def _init_global_config(self) -> None:
        """Interactively create the user-global model configuration."""
        config_file = Path.home() / ".claxcode" / ".env"
        providers = {
            "openai", "anthropic", "generic_openai", "ollama", "custom_http",
            *PROVIDER_BASE_URLS,
        }
        try:
            if config_file.exists():
                answer = await self._read_input("⚠️ 全局配置已存在，覆盖? [y/N] ")
                if answer.strip().lower() not in ("y", "yes"):
                    print("已取消，保留现有全局配置。\n")
                    return
            provider = (
                await self._read_input(f"模型提供商 [{settings.llm_provider}]: ")
            ).strip() or settings.llm_provider
            model = (await self._read_input(f"模型名称 [{settings.llm_model}]: ")).strip()
            current_base_url = (
                settings.llm_base_url if provider == settings.llm_provider else ""
            )
            default_base_url = current_base_url or PROVIDER_BASE_URLS.get(provider, "")
            base_url = (
                await self._read_input(f"接口地址 [{default_base_url or '默认'}]: ")
            ).strip() or default_base_url
            api_key = await self._read_input("API 密钥（可留空）: ", is_password=True)
        except (EOFError, KeyboardInterrupt):
            print("\n已取消全局配置。\n")
            return

        model = model or settings.llm_model
        if provider not in providers:
            print(f"❌ 不支持的模型提供商: {provider}，可选: {', '.join(sorted(providers))}\n")
            return
        values = [provider, model, base_url, api_key]
        if any("\n" in value or "\r" in value for value in values):
            print("❌ 配置值不能包含换行。\n")
            return

        content = (
            f"LLM_PROVIDER={provider}\n"
            f"LLM_API_KEY={api_key.strip()}\n"
            f"LLM_BASE_URL={base_url}\n"
            f"LLM_MODEL={model}\n"
            f"LLM_TEMPERATURE={settings.llm_temperature}\n"
            f"LLM_MAX_TOKENS={settings.llm_max_tokens}\n"
        )
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(content, encoding="utf-8")
        print(f"✅ 全局配置已保存: {config_file}")
        print("重启 CLI 后生效，可使用 /config 查看。\n")

    async def _cmd_version(self, args: list[str]) -> bool:
        print(f"ClaxCode {_get_version()}\n")
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
        if args and (not args[0].isdigit() or int(args[0]) < 1):
            print("❌ 用法: /audit [正整数]\n")
            return False
        limit = int(args[0]) if args else 10
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

        if args and (not args[0].isdigit() or int(args[0]) < 1):
            print("❌ 用法: /rollback [正整数|list]\n")
            return False
        steps = int(args[0]) if args else 1
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
        print("\n输入技巧:")
        print("  @文件路径 / @\"带 空格的路径\"  引用项目文件（Tab 模糊补全）")
        print("  !命令 / #内容                执行 Shell / 保存自动记忆")
        print("  Alt+Enter / Ctrl+C           换行 / 清空输入（空输入时退出）")
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
            if not path_obj.is_dir():
                print(f"❌ 项目目录不存在: {new_path}\n")
                return
            await self._persist_session()
            debug = self.agent.debug if self.agent else None
            has_agent = self.agent is not None
            self.project_path = path_obj
            self._auto_approved.clear()
            self.skill_manager = SkillManager()
            self._load_skills()
            self._prompt_session = self._create_prompt_session()
            self.session_id = uuid4()
            restored = 0
            if has_agent:
                self.agent = Agent(
                    session_id=self.session_id,
                    project_path=str(self.project_path),
                    permission_mode=self.permission_mode,
                    skill_manager=self.skill_manager,
                    debug=debug,
                    approval_callback=self._approve_tool,
                )
                restored = await self._resume_session()
            else:
                self.agent = None
            print(f"✅ 已切换到项目: {self.project_path}")
            if restored:
                print(f"💾 已恢复项目会话（{restored} 条消息）。")
            print()

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
        subcmd = args[0] if args else "overview"

        if subcmd == "overview":
            await self._memory_overview()

        elif subcmd == "history":
            self._memory_history(args)

        elif subcmd == "list":
            memories = await long_term_memory.list_all(
                limit=20, project_path=str(self.project_path), include_global=True
            )
            if not memories:
                print("ℹ️ 当前项目和全局长期记忆为空。\n")
                return
            print("\n🧠 长期记忆（当前项目 + 全局）:")
            for m in memories:
                ts = m.get("timestamp", "")[:10]
                scope = "全局" if not m.get("project_path") else "项目"
                keywords = ", ".join(m.get("keywords", [])[:5])
                content = m.get("compressed_content", "")[:80]
                print(f"  [{ts}] [{scope}] [{m['id']}] {keywords}")
                print(f"      {content}")
            print("  使用 /memory delete <完整记忆ID> 删除。\n")

        elif subcmd == "search":
            if len(args) < 2:
                print("❌ 用法: /memory search <关键词>\n")
                return
            keywords = args[1:]
            memories = await long_term_memory.search(
                keywords=keywords,
                project_path=str(self.project_path),
                include_global=True,
                limit=10,
            )
            if not memories:
                print(f"ℹ️ 未找到包含关键词 '{', '.join(keywords)}' 的记忆。\n")
                return
            print(f"\n🔍 搜索结果 ({len(memories)} 条):")
            for m in memories:
                ts = m.get("timestamp", "")[:10]
                scope = "全局" if not m.get("project_path") else "项目"
                kw = ", ".join(m.get("keywords", []))
                print(f"  [{ts}] [{scope}] {kw}")
                print(f"      {m.get('compressed_content', '')[:100]}")
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
            print(f"❓ 未知子命令: {subcmd}。用法: /memory [history|list|learn|forget|...]\n")

    async def _memory_overview(self) -> None:
        """打印记忆总览：长期记忆、自动记忆、当前会话。"""
        memories = await long_term_memory.list_all(
            limit=100, project_path=str(self.project_path), include_global=True
        )
        facts = auto_memory.items()
        msg_count = len(self.agent.context.messages) - 1 if self.agent else 0

        print("\n🧠 记忆总览:")
        print(f"  • 长期记忆（当前项目 + 全局）: {len(memories)} 条（/memory list 查看）")
        for m in memories[:3]:
            print(f"      - {m.get('compressed_content', '')[:60]}")
        print(f"  • 全局自动记忆: {len(facts)} 条（/memory facts 查看）")
        print(f"  • 当前会话消息: {max(msg_count, 0)} 条（/memory history 查看）")
        print()

    def _memory_history(self, args: list[str]) -> None:
        """显示当前会话的最近消息（含恢复的会话）。"""
        if not self.agent:
            print("❌ 代理未初始化。\n")
            return
        limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 20
        messages = [m for m in self.agent.context.messages if m.get("role") != "system"]
        if not messages:
            print("ℹ️ 当前会话没有历史消息。\n")
            return
        shown = messages[-limit:]
        print(f"\n📜 会话历史（共 {len(messages)} 条，显示最近 {len(shown)} 条）:")
        for m in shown:
            role = m.get("role", "?")
            content = str(m.get("content") or "")
            if role == "assistant" and not content and m.get("tool_calls"):
                names = ", ".join(tc["function"]["name"] for tc in m["tool_calls"])
                content = f"[调用工具: {names}]"
            icon = {"user": "👤", "assistant": "🤖", "tool": "🔧"}.get(role, "•")
            print(f"  {icon} {content.replace(chr(10), ' ')[:80]}")
        print()

    async def _handle_init_command(self) -> None:
        """处理 /init 命令 - 初始化项目."""
        context_file = self.project_path / "CLAUDE.md"
        try:
            if context_file.exists():
                answer = await self._read_input(f"⚠️ {context_file.name} 已存在，覆盖? [y/N] ")
                if answer.strip().lower() not in ("y", "yes"):
                    print("已取消，保留现有项目上下文。\n")
                    return

            print("\n📝 初始化项目信息")
            print("-" * 40)
            name = await self._read_input(f"项目名称 [{self.project_path.name}]: ")
            description = await self._read_input("项目描述: ")
            tech_stack = await self._read_input("技术栈 (如: Python, FastAPI, React): ")
            build_command = await self._read_input("构建命令 (如: npm run build): ")
            test_command = await self._read_input("测试命令 (如: pytest): ")
            code_style = await self._read_input("代码风格偏好: ")
            notes = await self._read_input("其他说明: ")
        except (EOFError, KeyboardInterrupt):
            print("\n已取消项目初始化。\n")
            return

        config = {
            "name": name.strip() or self.project_path.name,
            "description": description.strip(),
            "tech_stack": tech_stack.strip(),
            "build_command": build_command.strip(),
            "test_command": test_command.strip(),
            "code_style": code_style.strip(),
            "notes": notes.strip(),
        }
        memory_id = await project_memory.init_project(str(self.project_path), config)
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

        try:
            project = await project_memory.get_project(str(self.project_path))
            previous_summary = project.get("context_summary", "") if project else ""
            summary_prompt = f"""请总结本次对话，并更新项目滚动摘要。

已有项目摘要（保留仍有效的信息，移除已被推翻的结论）：
{previous_summary[:2000] or "（无）"}

本次对话：
{full_content[:8000]}

要求：
1. 关键词覆盖本次讨论的主题。
2. 本次总结聚焦这轮完成的工作、重要文件和结论，150字以内。
3. 项目摘要融合旧摘要与本次对话，记录当前有效状态和未完成事项，250字以内。

严格使用以下格式：
关键词: keyword1, keyword2, keyword3
本次总结: ...
项目摘要: ..."""

            summary_response = ""
            async for chunk in self.agent.provider.stream_chat(
                messages=[{"role": "user", "content": summary_prompt}], tools=None
            ):
                if isinstance(chunk, str):
                    summary_response += chunk

            keyword_match = re.search(r"^关键词[:：]\s*(.+)$", summary_response, re.MULTILINE)
            summary_match = re.search(
                r"(?:本次总结|总结)[:：]\s*(.*?)(?=\n项目摘要[:：]|$)",
                summary_response,
                re.DOTALL,
            )
            project_match = re.search(r"项目摘要[:：]\s*(.*)", summary_response, re.DOTALL)
            summary = (summary_match.group(1) if summary_match else summary_response).strip()
            if not summary:
                raise ValueError("模型未返回有效摘要")
            project_summary = (project_match.group(1) if project_match else summary).strip()
            keywords = (
                [k.strip() for k in re.split(r"[,，]", keyword_match.group(1)) if k.strip()]
                if keyword_match
                else []
            )

            memory_id = await long_term_memory.save(
                session_id=str(self.session_id),
                compressed_content=summary,
                keywords=keywords,
                project_path=str(self.project_path),
            )
            await project_memory.update_summary(str(self.project_path), project_summary)

            self.agent.context.clear()
            await self._persist_session()

            print("✅ 会话已压缩，长期记忆与项目滚动摘要已更新!")
            print(f"   记忆ID: {memory_id}")
            print(f"   关键词: {', '.join(keywords[:5])}")
            print(f"   本次总结: {summary[:100]}\n")

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
        if self.agent:
            self.agent.update_skills(self.skill_manager)
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


def _setup_console_utf8() -> None:
    """Reconfigure stdout/stderr as UTF-8 so emoji output works on Windows cmd (GBK)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            with suppress(Exception):
                reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    _setup_console_utf8()
    if _missing_env_file is not None:
        print(f"⚠️ 未找到环境文件: {_missing_env_file}")
    parser = argparse.ArgumentParser(description="ClaxCode 交互式命令行")
    parser.add_argument("--project", "-p", default=".", help="项目目录")
    parser.add_argument(
        "--mode", "-m", default="ask",
        choices=["ask", "auto_edit", "plan", "auto_safe", "yolo"],
    )
    parser.add_argument(
        "--version", "-v", action="version", version=f"%(prog)s {_get_version()}", help="显示版本号"
    )
    parser.add_argument("--env", "-e", default=None, help=".env 文件路径")
    parser.add_argument(
        "--print", "-P", dest="one_shot", default=None, metavar="PROMPT",
        help="非交互模式：执行单条指令后退出（工具日志走 stderr）",
    )
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("init", help="交互式创建全局模型配置")
    args = parser.parse_args()

    project_path = Path(args.project).resolve()
    cli = InteractiveCLI(project_path=str(project_path), permission_mode=args.mode)
    if args.command == "init":
        asyncio.run(cli._init_global_config())
    elif args.one_shot:
        asyncio.run(cli.one_shot(args.one_shot))
    else:
        asyncio.run(cli.run())


if __name__ == "__main__":
    main()
