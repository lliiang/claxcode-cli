# AGENTS.md — ClaxCode

Guidance for AI coding agents working in this repository. Assumes no prior knowledge of the project.

## Project Overview

ClaxCode is an **agentic coding assistant** (inspired by Claude Code) written in Python. It has two front-ends sharing the same core:

- **Interactive CLI** (`claxcode-cli`) — a REPL-style terminal assistant. Slash commands are declared in a dispatch table in `cli.py` (and `/help` is generated from it); skill-defined commands (`## Commands` in SKILL.md) are routed to the agent as instructions. Input prefixes: `!cmd` runs a shell command directly, `#text` saves a quick auto-memory note, `@path` inlines a file's content. `--print/-P PROMPT` runs one prompt non-interactively (headless). The conversation is persisted per turn and resumed on next launch (`.claxcode/cli_session`).
- **HTTP API server** (`claxcode`) — a FastAPI app that streams chat events over SSE.

The core is an **Agentic Loop** (`claxcode/core/agent.py`): gather context -> think (LLM streaming) -> act (tool calls) -> verify, capped at `max_iterations = 10` per user message. The agent talks to an abstracted LLM provider, calls tools from a central registry, snapshots files before editing them, and injects project context (`CLAUDE.md`), skills, and long-term/project memories into the system prompt.

## Technology Stack

- **Python >= 3.11**, packaging via `pyproject.toml` with the **hatchling** build backend; installed with pip.
- **FastAPI + Uvicorn** for the API server; SSE via `StreamingResponse`.
- **Pydantic v2 + pydantic-settings** for settings, API models, and tool input schemas.
- **SQLAlchemy 2.0 (async) + aiosqlite** for persistence; SQLite by default.
- **httpx** for all outbound HTTP, including the OpenAI-compatible provider (the `openai` package is *not* used).
- **paramiko** for SSH tools; **playwright** for browser tools (optional, lazily imported; install the `browser` extra).
- **pytest + pytest-asyncio + pytest-httpx** for tests; **ruff** and **mypy** are configured (see "Code Style" for their current state).

## Code Organization

```
claxcode/
├── main.py            # FastAPI app factory, /health, router wiring, uvicorn launcher
├── cli.py             # InteractiveCLI REPL (entry point `claxcode-cli`), slash commands
├── config.py          # `settings` — pydantic-settings, reads .env
├── api/               # FastAPI routers: session, chat (SSE), tools, subagents
├── core/
│   ├── agent.py       # Agent: the agentic loop, permission check, pre-edit snapshots
│   ├── models.py      # LLMProvider ABC + OpenAI/Anthropic/GenericOpenAI/Ollama/CustomHTTP/Dummy providers
│   ├── context.py     # ContextManager: message history, rough token estimate, summary compression
│   └── checkpoint.py  # CheckpointManager: snapshots files into .claxcode/snapshots/ before edits; manifest-based list/restore (rollback)
├── tools/             # Tool base class, registry, and built-in tools (auto-discovered)
├── subagents/         # Subagent base + explore/planner (read-only) and executor (all tools)
├── memory/            # session_store (SQLAlchemy ORM + init_db), long/short-term & project memory
├── extensions/        # skills.py and hooks.py (working); mcp.py, plugins.py are STUBS
├── security/          # permissions.py (modes, enforced in the agent loop); audit.py (durable JSONL logger)
├── skills/            # Built-in skill packages shipped with the app (SKILL.md + optional tools.py)
└── models/            # Pydantic request/response models for the API

tests/                 # pytest suite, mirrors the package layout
```

### Tool system

- All tools subclass `Tool` (`claxcode/tools/base.py`): class attrs `name`, `description`, `input_schema` (JSON Schema), `category`, `required_permissions` (subset of `"read"`, `"write"`, `"execute"`, `"web"`); implement `async execute(**kwargs) -> str`.
- The `@tool` decorator (`claxcode/tools/registry.py`) registers an instance in the global `registry`.
- `claxcode/tools/__init__.py` **auto-imports every module in the package** via `pkgutil` — dropping a new module into `claxcode/tools/` is enough to register its tools. Both entry points import `claxcode.tools` for this side effect.
- Built-in tools (35 total): file ops (`read_file`, `write_file`, `str_replace_file`, `view_file`, `edit_file`, `create_directory`, `rename_file`), search (`glob_search`, `grep_search`, `explore_codebase`), execution (`run_shell`, `run_tests`, `git_command`), web (`fetch_url`, `web_search` — DuckDuckGo HTML scraping), browser (9 Playwright tools), SSH (5 paramiko tools), code intelligence (`type_check`, `find_definition`, `find_references`), admin (`admin_add_tool`), memory (`remember_fact`), example (`calculate`).

### LLM providers

`claxcode/core/models.py` defines the `LLMProvider` ABC (`stream_chat(messages, tools)` yielding `str` chunks or tool-call dicts) and `get_provider()`, which dispatches on `LLM_PROVIDER`: `openai`, `anthropic` (requires the optional `anthropic` package), `generic_openai` (vLLM/LM Studio/DashScope), `ollama`, `custom_http` (template-driven via `LLM_CUSTOM_CONFIG`), or anything registered at runtime with `register_custom_provider()`. Unknown or broken configuration falls back to `DummyProvider` so the app always starts.

### Persistence

`claxcode/memory/session_store.py` holds all ORM tables (`sessions`, `subagent_tasks`, `long_term_memories`, `short_term_memories`, `project_memories`). Tables are created with `Base.metadata.create_all` in `init_db()` — **there are no migrations** (Alembic is a noted future option). Runtime data lives under `./.claxcode/` (`claxcode.db`, `snapshots/`). Conversation messages are persisted per chat turn (`save_session_messages`/`get_session_messages` on the `sessions.messages` column): the API restores them per request, and the CLI resumes the last session via `.claxcode/cli_session`. `memory/auto_memory.py` is a durable JSON key-value store at `~/.claxcode/auto_memory.json` — injected into the system prompt, writable via the `remember_fact` tool or `/memory learn` in the CLI. (`short_term_memory` exists but is currently unused.)

### Language convention

Module docstrings, `README.md`, and this file are in **English**; inline comments, CLI output, error messages, and LLM-facing prompts are largely in **Chinese** (e.g. the default system prompt in `core/agent.py`). Match the surrounding style when editing: English for docstrings, Chinese for user-facing strings.

## Build and Run

```bash
# Setup (Windows)
python -m venv .venv
.\.venv\Scripts\activate
pip install -e "."            # core
pip install -e ".[dev]"       # + pytest, ruff, mypy
pip install -e ".[openai]" / ".[anthropic]"  # optional provider SDKs

# API server (http://127.0.0.1:8000, GET /health -> "ok")
claxcode                      # or: python -m claxcode.main

# Interactive CLI
claxcode-cli --project . --mode ask          # modes: ask|auto_edit|plan|auto_safe|yolo
```

Console scripts (`pyproject.toml [project.scripts]`): `claxcode` -> `claxcode.main:run`, `claxcode-cli` -> `claxcode.cli:main`.

API surface: `POST/GET/GET{id}/DELETE /sessions`, `POST /sessions/{id}/chat` (SSE stream of `thinking`/`message_delta`/`tool_call`/`tool_result`/`done` events), `GET /tools`, `POST /tools/invoke`, `POST /subagents`, `GET /subagents/{id}`, `POST /subagents/{id}/stream`.

## Testing

```bash
pytest            # 110 tests, all passing at time of writing
```

- Config in `pyproject.toml`: `asyncio_mode = "auto"`, `testpaths = ["tests"]` — async tests need no decorator.
- `tests/conftest.py` provides a `client` fixture: an httpx `AsyncClient` over `ASGITransport(app)` with `init_db()` called first. Use it for API tests.
- Tests mirror the source layout (`test_api/`, `test_core/`, `test_tools/`, `test_security/`, `test_extensions/`). Add tests for new tools/providers following the existing style.
- `pytest-httpx` is available for mocking outbound LLM/HTTP calls; tests must not require a real LLM or network.

## Code Style

- Configured in `pyproject.toml`: **ruff** (`line-length = 100`, `target-version = "py311"`, rules `E,F,I,N,W,UP,B,C4,SIM`) and **mypy** (`strict = true`, py3.11).
- Current state: `ruff check claxcode tests` reports ~44 errors and `mypy claxcode` ~131 errors — **neither is clean**, so do not treat them as gates, but do not add new violations either.
- Idioms: async/await throughout, type hints, `pathlib.Path`, Google-style docstrings, absolute imports (`from claxcode.x import y`).
- Keep tool results as plain strings (the `Tool.execute()` contract); never raise from `execute()` — return an error string, as callers stringify exceptions anyway.

## Configuration

Copy `.env.example` to `.env`. All settings are env-driven (`claxcode/config.py`, `extra="ignore"`):

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai` / `anthropic` / `generic_openai` / `ollama` / `custom_http` / custom-registered name |
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | — / — / `gpt-4o` | |
| `LLM_TEMPERATURE`, `LLM_MAX_TOKENS` | `0.2` / `4096` | |
| `LLM_CUSTOM_CONFIG` | `""` | JSON string: `ollama_options`, or `request_template`/`response_parser` for `custom_http` |
| `DATABASE_URL` | `sqlite+aiosqlite:///./.claxcode/claxcode.db` | |
| `PERMISSION_MODE` | `ask` | `ask` / `auto_edit` / `plan` / `auto_safe` / `yolo` |
| `MAX_CONTEXT_TOKENS`, `CONTEXT_COMPRESSION_THRESHOLD` | `128000` / `0.85` | |
| `HOST`, `PORT`, `CLAXCODE_DEBUG`, `TOOL_TIMEOUT` | `127.0.0.1` / `8000` / `false` / `60` | |

Note: `python-dotenv` is declared in `pyproject.toml`; `playwright` is an optional extra (`pip install -e ".[browser]"`).

## Security Considerations

- A `.gitignore` now excludes `.env`, `.claxcode/`, caches, and `__pycache__/`. **`.env` was committed previously, so any keys it contained must be rotated — they remain in git history until it is rewritten.**
- Permission modes (`security/permissions.py`): `plan` blocks tools requiring `write`/`execute`; `ask` auto-allows read-only tools and requires approval for the rest; `auto_safe` blocks `execute`; `auto_edit`/`yolo` allow everything. Every tool call passes through `check_permission()` in `Agent._execute_tool`. In `ask` mode the CLI prompts interactively (`y`/`a`/`N`, with a per-session always-allow list, cleared on `/mode` change); the API has no approval channel, so non-read tools are blocked there unless the session uses another mode. Treat `yolo` as fully unsandboxed.
- Before any tool with `write` permission and a `path` argument runs, `CheckpointManager` copies the file to `.claxcode/snapshots/<session>/<timestamp>/` for rollback.
- `run_shell`/`git_command` execute arbitrary shell commands; `admin_add_tool` writes new tool modules; skill `tools.py` files are `exec()`'d — all by design, all dangerous with untrusted input.
- Every tool call (allowed or blocked) is appended to `.claxcode/audit.jsonl` by `security/audit.py`.
- `.claxcode/` (DB + snapshots) is local runtime state — do not commit it either.

## Extending the Project

- **New tool**: create a module in `claxcode/tools/`, subclass `Tool`, apply `@tool`, implement `execute()`. Auto-discovered on next start.
- **New LLM provider**: subclass `LLMProvider` in `core/models.py` and either add a branch in `get_provider()` or call `register_custom_provider(name, cls)` at runtime.
- **New skill**: directory with `SKILL.md` (`# Name`, `## Description`, `## Instructions`, optional `## Commands`) plus optional `tools.py`. `SkillManager.load_defaults()` loads `claxcode/skills/` (builtin), then `~/.claxcode/skills/` and `~/.agent/skills/` (user), then `<project>/.claxcode/skills/`, `<project>/.agent/skills/` and `<project>/skills/` (project) — on a name conflict the later source wins. Content is injected into the system prompt; the CLI has `/skills create|reload`.
- **Hooks**: `hooks.json` in `~/.claxcode/` or `<project>/.claxcode/` defines `PreToolUse`/`PostToolUse` shell commands with a regex `match` on tool names. The command gets a JSON payload on stdin and `CLAXCODE_TOOL_NAME`/`CLAXCODE_TOOL_ARGS` env vars; a non-zero PreToolUse exit blocks the tool call. Wired in `Agent._execute_tool`.
- **Subagents**: subclass `Subagent` (`subagents/base.py`) with a restricted `allowed_tools` list; explore and planner are read-only, executor gets everything.

## Known Gaps / Honest State

- `extensions/mcp.py` and `plugins.py` are stubs.
- No CI configuration, no Dockerfile, no deployment tooling — the app is run locally.
- Context compression summarizes the oldest half of the history with the LLM when over threshold (drop-oldest remains as the hard fallback); the token estimate is still a rough `len(text)//3`.
- `CLAUDE.md` in the repo root is a mostly-empty template generated by the CLI's `/init` command; `README.md` is the authoritative human-facing doc.
- The `3.4.0` file in the repo root is a stray pip-install log, safe to ignore/delete.
