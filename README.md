# ClaxCode

An agentic coding assistant powered by FastAPI.

## Architecture

- **Agentic Loop**: Gather Context -> Think -> Act -> Verify
- **Tools**: File operations, Search, Execution, Web, Code Intelligence
- **Subagents**: Explore, Planner, Executor with isolated contexts
- **Skills**: Reusable capability packages (inspired by Claude Code)
- **Extensions**: MCP, Hooks, Plugins

## Quick Start

### Interactive CLI (Recommended)

```bash
# Install
pip install -e "."

# Start interactive terminal session
claxcode-cli

# With options
claxcode-cli --project ./my-project --mode auto_edit
```

### API Server

```bash
# Start FastAPI server
claxcode
# or
python -m claxcode.main
```

## Supported LLM Providers

| Provider | `LLM_PROVIDER` value | Notes |
|---|---|---|
| OpenAI | `openai` | GPT-4, GPT-4o, etc. |
| Anthropic | `anthropic` | Claude 3/3.5 |
| Generic OpenAI-compatible | `generic_openai` | vLLM, LM Studio, DashScope, etc. |
| Ollama (native) | `ollama` | Local models via Ollama API |
| Custom HTTP | `custom_http` | Any API via configurable request/response templates |
| Custom (code) | any name | Register your own `LLMProvider` subclass |

## Configuration

Copy `.env.example` to `.env` and adjust:

```env
LLM_PROVIDER=generic_openai
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
LLM_MODEL=kimi-k2.5
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=4096
PERMISSION_MODE=ask
```

### Permission Modes

| Mode | Description |
|---|---|
| `ask` | Ask for approval on every edit/execution |
| `auto_edit` | Auto-accept file edits, ask for shell/exec |
| `plan` | Read-only, no mutations |
| `auto_safe` | Auto-accept edits and safe commands, ask for destructive ops |
| **yolo** | **Auto-accept everything — full autopilot** |

```bash
# YOLO mode: fully automated, no confirmations
claxcode-cli --mode yolo
```

### Using Ollama

```env
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434
LLM_MODEL=llama3.1
LLM_CUSTOM_CONFIG={"ollama_options": {"num_ctx": 8192}}
```

### Using Generic OpenAI-compatible APIs

```env
LLM_PROVIDER=generic_openai
LLM_BASE_URL=http://localhost:8000/v1
LLM_API_KEY=sk-optional
LLM_MODEL=your-model-name
```

### Using Custom HTTP API

For APIs that don't match OpenAI format, use `custom_http` with `LLM_CUSTOM_CONFIG`:

```env
LLM_PROVIDER=custom_http
LLM_CUSTOM_CONFIG={
  "request_template": {
    "url": "http://localhost:8000/chat",
    "method": "POST",
    "headers": {"Authorization": "Bearer {api_key}"},
    "body": {
      "model": "{model}",
      "messages": "{messages}",
      "temperature": "{temperature}",
      "stream": true
    }
  },
  "response_parser": {
    "content_path": "choices.0.delta.content"
  }
}
```

Template variables: `{api_key}`, `{model}`, `{messages}`, `{temperature}`, `{max_tokens}`, `{tools}`.

### Registering a Custom Provider in Code

```python
from claxcode.core.models import register_custom_provider, LLMProvider
from collections.abc import AsyncIterator
from typing import Any

class MyProvider(LLMProvider):
    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str | dict[str, Any]]:
        # Your implementation here
        yield "Hello from my model!"

register_custom_provider("my_model", MyProvider)
```

Then set `LLM_PROVIDER=my_model`.

## Skills

Skills are reusable capability packages inspired by Claude Code. Each skill is a directory containing a `SKILL.md` file that describes conventions, instructions, and commands. Skill content is automatically injected into the agent's system prompt.

### Skill Directory Layout

```
skills/
  python-refactor/
    SKILL.md
  docker-best-practices/
    SKILL.md
```

### SKILL.md Format

```markdown
# Skill Name

## Description
Brief explanation of what this skill does.

## Instructions
Detailed instructions for the agent on how to use this skill.
Can include examples, conventions, file patterns, etc.

## Commands (optional)
- `cmd_name`: Description of what this command does
```

### Skill Discovery

Skills are loaded from two locations:

1. **Global skills**: `~/.claxcode/skills/`
2. **Project skills**: `./.claxcode/skills/` or `./skills/`

An example skill is included at `skills/python-refactor/`.

## CLI Commands

When running `claxcode-cli`:

| Command | Description |
|---|---|
| `/help` | Show available commands |
| `/tools` | List available tools |
| `/mode <mode>` | Set permission mode (ask/auto_edit//plan/auto_safe/yolo) |
| `/skills` | List loaded skills |
| `/config` | Show current LLM configuration |
| `/clear` | Clear conversation context |
| `/project` | Show project context (CLAUDE.md) |
| `/exit`, `/quit` | Exit ClaxCode |

## API

- `POST /sessions` — Create a session
- `GET /sessions` — List sessions
- `POST /sessions/{id}/chat` — Chat with SSE streaming
- `GET /tools` — List available tools
- `POST /tools/invoke` — Invoke a tool directly
- `POST /subagents` — Spawn a subagent

## Testing

```bash
pytest
```
