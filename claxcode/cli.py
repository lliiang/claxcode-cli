"""Interactive CLI for ClaxCode — terminal-based agentic coding assistant."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

# Load .env BEFORE importing settings so that pydantic picks up the values
from dotenv import load_dotenv

# Try common .env locations
for _env_path in [Path(".env").resolve(), Path.home() / ".claxcode" / ".env"]:
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
        break

from claxcode.config import settings
from claxcode.core.agent import Agent
from claxcode.extensions.skills import SkillManager
from claxcode.memory.project_context import load_project_context
from claxcode.tools.registry import registry


class InteractiveCLI:
    """REPL-style interactive CLI."""

    def __init__(self, project_path: str = ".", permission_mode: str = "ask"):
        self.session_id = uuid4()
        self.project_path = Path(project_path).resolve()
        self.permission_mode = permission_mode
        self.agent: Agent | None = None
        self.skill_manager = SkillManager()
        self._load_skills()

    def _load_skills(self) -> None:
        """Load global and project-level skills."""
        global_skills = Path.home() / ".claxcode" / "skills"
        if global_skills.exists():
            self.skill_manager.load_skill_dir(global_skills)
        project_skills = self.project_path / ".claxcode" / "skills"
        if project_skills.exists():
            self.skill_manager.load_skill_dir(project_skills)
        project_skills2 = self.project_path / "skills"
        if project_skills2.exists():
            self.skill_manager.load_skill_dir(project_skills2)

    async def run(self) -> None:
        print("🚀 ClaxCode")
        print(f"📁 Project: {self.project_path}")
        print(f"🔧 Mode: {self.permission_mode}")
        print(f"🧠 Skills loaded: {len(self.skill_manager.skills)}")
        print(f"🤖 LLM Provider: {settings.llm_provider}")
        print(f"📝 LLM Model: {settings.llm_model}")
        print(f"🔑 API Key set: {'Yes' if settings.llm_api_key else 'No'}")
        print(f"🐛 Debug: {'On' if settings.debug else 'Off'}")
        print('Type "/help" for commands, "/exit" to quit.\n')

        self.agent = Agent(
            session_id=self.session_id,
            project_path=str(self.project_path),
            permission_mode=self.permission_mode,
        )
        skills_prompt = self.skill_manager.to_prompt_fragment()
        if skills_prompt:
            self.agent.context.add_message("system", f"\n\n{skills_prompt}")

        while True:
            try:
                user_input = await self._read_input()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Goodbye!")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                should_exit = await self._handle_command(user_input)
                if should_exit:
                    break
            else:
                await self._chat(user_input)

    async def _read_input(self) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: input("❯ "))

    async def _chat(self, message: str) -> None:
        if self.agent is None:
            return
        print()
        async for event in self.agent.run(message):
            etype = event.get("type")
            if etype == "thinking":
                print(f"💭 {event['content']}")
            elif etype == "message_delta":
                print(event["content"], end="", flush=True)
            elif etype == "tool_call":
                print(f"\n🔧 Calling tool: {event['name']}({json.dumps(event.get('arguments', {}))})")
            elif etype == "tool_result":
                print(f"📋 Result:\n{event['output'][:500]}{'...' if len(event['output']) > 500 else ''}")
            elif etype == "debug":
                self._print_debug(event)
            elif etype == "done":
                print("\n")

    async def _handle_command(self, command: str) -> bool:
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("/exit", "/quit"):
            print("👋 Goodbye!")
            return True

        if cmd == "/help":
            self._print_help()
        elif cmd == "/tools":
            self._print_tools()
        elif cmd == "/mode":
            self._set_mode(args)
        elif cmd == "/skills":
            self._print_skills()
        elif cmd == "/debug":
            self._toggle_debug()
        elif cmd == "/config":
            self._print_config()
        elif cmd == "/clear":
            if self.agent:
                self.agent.context.clear()
            print("🧹 Context cleared.\n")
        elif cmd == "/project":
            ctx = load_project_context(self.project_path)
            if ctx:
                print(f"📄 Project context:\n{ctx}\n")
            else:
                print("ℹ️ No project context file found (CLAUDE.md or .claxcode/context.md).\n")
        else:
            print(f"❓ Unknown command: {cmd}. Type /help for available commands.\n")

        return False

    def _print_help(self) -> None:
        print("""
Commands:
  /help          Show this help message
  /tools         List available tools
  /mode <mode>   Set permission mode (ask|auto_edit|plan|auto_safe|yolo)
  /skills        List loaded skills
  /config        Show current LLM configuration
  /debug         Toggle debug mode (show raw LLM context)
  /clear         Clear conversation context
  /project       Show project context (CLAUDE.md)
  /exit, /quit   Exit ClaxCode

Any other input is sent to the agent.
""")

    def _print_tools(self) -> None:
        print("\nAvailable tools:")
        for tool in registry.list_tools():
            print(f"  • {tool.name} ({tool.category}) — {tool.description}")
        print()

    def _set_mode(self, args: list[str]) -> None:
        modes = ["ask", "auto_edit", "plan", "auto_safe", "yolo"]
        if not args:
            mode = self._interactive_select(modes, prompt="Select mode:")
            if mode is None:
                print("  Cancelled.\n")
                return
        else:
            mode = args[0].lower()
            if mode not in modes:
                print("❌ Invalid mode. Choose: ask, auto_edit, plan, auto_safe, yolo\n")
                return
        self.permission_mode = mode
        if self.agent:
            self.agent.permission_mode = mode
        print(f"✅ Mode set to: {mode}\n")

    def _interactive_select(self, options: list[str], prompt: str = "Select:") -> str | None:
        """Show an inline arrow-key selector. Returns the chosen option or None if cancelled."""
        import sys

        idx = options.index(self.permission_mode) if self.permission_mode in options else 0
        prefix = f"{prompt} "
        # Print initial line
        print(f"{prefix}{options[idx]}  [←↑↓→ to move, Enter to confirm, Esc to cancel]", end="", flush=True)

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
                print(f"\r{prefix}{options[idx]}  [←↑↓→ to move, Enter to confirm, Esc to cancel]", end="", flush=True)
        else:
            import tty
            import termios

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
                    print(f"\r{prefix}{options[idx]}  [←↑↓→ to move, Enter to confirm, Esc to cancel]", end="", flush=True)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return None

    def _print_config(self) -> None:
        print(f"""
Configuration:
  LLM_PROVIDER:     {settings.llm_provider}
  LLM_MODEL:        {settings.llm_model}
  LLM_BASE_URL:     {settings.llm_base_url or '(default)'}
  LLM_TEMPERATURE:  {settings.llm_temperature}
  LLM_MAX_TOKENS:   {settings.llm_max_tokens}
  API_KEY set:      {'Yes' if settings.llm_api_key else 'No'}
  Database:         {settings.database_url}
  Permission mode:  {self.permission_mode}
  Debug mode:       {'On' if self.agent and self.agent.debug else 'Off'}
""")

    def _toggle_debug(self) -> None:
        if self.agent is None:
            return
        self.agent.debug = not self.agent.debug
        state = "On" if self.agent.debug else "Off"
        print(f"🐛 Debug mode: {state}\n")

    def _print_debug(self, event: dict) -> None:
        label = event.get("label", "Debug")
        payload = event.get("payload", {})
        print(f"\n{'─' * 60}")
        print(f"🐛 DEBUG — {label}")
        print(f"{'─' * 60}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"{'─' * 60}\n")

    def _print_skills(self) -> None:
        if not self.skill_manager.skills:
            print("ℹ️ No skills loaded.\n")
            return
        print("\nLoaded skills:")
        for skill in self.skill_manager.skills:
            print(f"  • {skill.name} — {skill.description}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="ClaxCode Interactive CLI")
    parser.add_argument("--project", "-p", default=".", help="Project directory")
    parser.add_argument("--mode", "-m", default="ask", choices=["ask", "auto_edit", "plan", "auto_safe", "yolo"])
    parser.add_argument("--env", "-e", default=None, help="Path to .env file")
    args = parser.parse_args()

    project_path = Path(args.project).resolve()

    # Allow explicit .env override
    if args.env:
        env_file = Path(args.env)
        if env_file.exists():
            load_dotenv(env_file, override=True)
        else:
            print(f"⚠️ Env file not found: {env_file}")

    cli = InteractiveCLI(project_path=str(project_path), permission_mode=args.mode)
    asyncio.run(cli.run())


if __name__ == "__main__":
    main()
