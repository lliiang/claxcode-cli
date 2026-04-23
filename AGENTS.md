# AGENTS.md — ClaxCode

## Project Overview

ClaxCode is an agentic coding assistant built with FastAPI. It follows an **Agentic Loop** architecture (Gather Context -> Think -> Act -> Verify) and supports subagents, an extensible tool system, and streaming chat via SSE.

## Technology Stack

- **Backend**: FastAPI + Uvicorn
- **LLM Layer**: Abstracted provider system (OpenAI, Anthropic, Generic OpenAI-compatible) with fallback DummyProvider
- **Database**: Async SQLite via SQLAlchemy + aiosqlite
- **Testing**: pytest + pytest-asyncio + httpx
- **Package Manager**: pip with `pyproject.toml`

## Directory Structure

```
claxcode/
├── api/           # FastAPI routers (session, chat, tools, subagents)
├── core/          # Agentic loop, LLM providers, context manager, checkpoints
├── tools/         # Tool registry and implementations (file ops, search, exec, web, code intel)
├── subagents/     # Explore, Planner, Executor subagents
├── memory/        # Session store, auto-memory, project context loading
├── extensions/    # Skills, MCP, Hooks, Plugins (stubs for future phases)
├── security/      # Permission modes and audit logging
├── models/        # Pydantic data models
├── config.py      # Pydantic Settings
└── main.py        # Application entry point
```

## Build and Run

```bash
# Create virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install core dependencies
pip install -e "."

# Run server
python -m claxcode.main
# or
claxcode
```

## Testing

```bash
pytest
```

## Configuration

Copy `.env.example` to `.env` and adjust values:

- `LLM_PROVIDER` — `openai`, `anthropic`, or `generic_openai`
- `LLM_API_KEY`
- `LLM_MODEL` (default: `gpt-4o`)
- `DATABASE_URL`
- `PERMISSION_MODE` — `ask`, `auto_edit`, `plan`, `auto_safe`

## Key Design Decisions

- **Streaming-first**: All chat responses are streamed via SSE.
- **Filesystem snapshots**: Checkpoints copy files before edits (works without git).
- **DummyProvider fallback**: App starts even without OpenAI/Anthropic packages installed.
- **Pydantic v2**: Used for settings, API models, and tool schemas.

## Notes for Future Agents

1. **Tool registration**: Import tool modules in `tools/__init__.py` to trigger `@tool` decorator registration.
2. **Adding a new tool**: Subclass `Tool` in the appropriate category module, apply `@tool`, and implement `execute()`.
3. **LLM provider**: To add a new provider, subclass `LLMProvider` in `core/models.py` and register it in `get_provider()`.
4. **Database migrations**: Currently uses `create_all` on startup. For production, consider Alembic.
