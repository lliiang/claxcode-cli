"""LLM abstraction layer supporting multiple providers and custom models."""

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

import httpx

from claxcode.config import settings


class ToolCallChunk:
    def __init__(self):
        self.id: str = ""
        self.name: str = ""
        self.arguments: str = ""


class LLMProvider(ABC):
    """Abstract LLM provider."""

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str | dict[str, Any]]:
        """Yield text chunks or tool-call dicts."""
        ...


class DummyProvider(LLMProvider):
    """Fallback provider when no LLM package is installed or config is invalid."""

    def __init__(self, reason: str = ""):
        self.reason = reason

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str | dict[str, Any]]:
        if self.reason:
            yield f"[DummyProvider] {self.reason}"
        else:
            yield "[DummyProvider] No LLM configured. Please set LLM_PROVIDER and LLM_API_KEY."


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible API provider using httpx (no openai package required)."""

    def __init__(self):
        self.api_key = settings.llm_api_key or "sk-test"
        self.base_url = (settings.llm_base_url or "https://api.openai.com").rstrip("/")
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str | dict[str, Any]]:
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                current_tool: ToolCallChunk | None = None

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line == "[DONE]":
                        break
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content

                    # Tool calls
                    tcs = delta.get("tool_calls", [])
                    for tc in tcs:
                        if tc.get("id"):
                            if current_tool is None:
                                current_tool = ToolCallChunk()
                            current_tool.id = tc["id"]
                        func = tc.get("function", {})
                        if func.get("name"):
                            if current_tool is None:
                                current_tool = ToolCallChunk()
                            current_tool.name = func["name"]
                        if func.get("arguments"):
                            if current_tool is None:
                                current_tool = ToolCallChunk()
                            current_tool.arguments += func["arguments"]

                    finish_reason = data.get("choices", [{}])[0].get("finish_reason")
                    if finish_reason and current_tool and current_tool.name:
                        try:
                            args = json.loads(current_tool.arguments or "{}")
                        except json.JSONDecodeError:
                            # Some providers return malformed JSON; fall back to raw string
                            args = {"_raw": current_tool.arguments}
                        yield {
                            "type": "tool_call",
                            "id": current_tool.id,
                            "name": current_tool.name,
                            "arguments": args,
                        }
                        current_tool = None


class AnthropicProvider(LLMProvider):
    def __init__(self):
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise ImportError(
                "anthropic package is required for AnthropicProvider. Install with: pip install anthropic"
            ) from exc

        self.client = AsyncAnthropic(api_key=settings.llm_api_key or "sk-test")
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str | dict[str, Any]]:
        system = ""
        anthropic_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                anthropic_messages.append({"role": m["role"], "content": m["content"]})

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": True,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        async with self.client.messages.stream(**kwargs) as stream:
            current_tool: ToolCallChunk | None = None
            async for event in stream:
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "text") and event.delta.text:
                        yield event.delta.text
                    if hasattr(event.delta, "partial_json"):
                        if current_tool is None:
                            current_tool = ToolCallChunk()
                        current_tool.arguments += event.delta.partial_json
                elif event.type == "content_block_start":
                    if hasattr(event.content_block, "name"):
                        if current_tool is None:
                            current_tool = ToolCallChunk()
                        current_tool.name = event.content_block.name
                        current_tool.id = getattr(event.content_block, "id", "")
                elif event.type == "message_stop":
                    if current_tool and current_tool.name:
                        yield {
                            "type": "tool_call",
                            "id": current_tool.id,
                            "name": current_tool.name,
                            "arguments": json.loads(current_tool.arguments or "{}"),
                        }
                        current_tool = None


class GenericOpenAIProvider(OpenAIProvider):
    """For local models with OpenAI-compatible API (e.g., vLLM, LM Studio, DashScope)."""

    pass


class OllamaProvider(LLMProvider):
    """Native Ollama API provider."""

    def __init__(self):
        self.base_url = settings.llm_base_url or "http://localhost:11434"
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        self.options = self._parse_options()

    def _parse_options(self) -> dict[str, Any]:
        """Parse extra Ollama options from custom config."""
        opts: dict[str, Any] = {}
        try:
            custom = json.loads(settings.llm_custom_config or "{}")
            opts.update(custom.get("ollama_options", {}))
        except json.JSONDecodeError:
            pass
        return opts

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str | dict[str, Any]]:
        url = f"{self.base_url.rstrip('/')}/api/chat"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
                **self.options,
            },
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["function"]["name"],
                        "description": t["function"]["description"],
                        "parameters": t["function"]["parameters"],
                    },
                }
                for t in tools
            ]

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("done"):
                        break
                    msg = data.get("message", {})
                    content = msg.get("content", "")
                    if content:
                        yield content
                    tool_calls = msg.get("tool_calls", [])
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        yield {
                            "type": "tool_call",
                            "id": tc.get("id", ""),
                            "name": func.get("name", ""),
                            "arguments": func.get("arguments", {}),
                        }


class CustomHTTPProvider(LLMProvider):
    """Generic HTTP provider for custom LLM APIs.

    Uses llm_custom_config to define request/response format:
    {
        "request_template": {
            "url": "http://localhost:8000/v1/chat",
            "method": "POST",
            "headers": {"Authorization": "Bearer {api_key}"},
            "body": {
                "model": "{model}",
                "messages": "{messages}",
                "temperature": "{temperature}",
                "max_tokens": "{max_tokens}",
                "stream": true
            }
        },
        "response_parser": {
            "content_path": "choices.0.delta.content",
            "tool_calls_path": "choices.0.delta.tool_calls"
        }
    }
    """

    def __init__(self):
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        self.api_key = settings.llm_api_key
        self.custom_config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        try:
            return json.loads(settings.llm_custom_config or "{}")
        except json.JSONDecodeError:
            return {}

    def _render_template(self, template: Any, **values: Any) -> Any:
        if isinstance(template, str):
            result = template
            for key, val in values.items():
                result = result.replace(f"{{{key}}}", json.dumps(val) if isinstance(val, (list, dict)) else str(val))
            return result
        if isinstance(template, dict):
            return {k: self._render_template(v, **values) for k, v in template.items()}
        if isinstance(template, list):
            return [self._render_template(item, **values) for item in template]
        return template

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str | dict[str, Any]]:
        cfg = self.custom_config.get("request_template", {})
        url = cfg.get("url", "http://localhost:8000/v1/chat")
        method = cfg.get("method", "POST")
        headers = self._render_template(cfg.get("headers", {}), api_key=self.api_key)
        body = self._render_template(
            cfg.get("body", {}),
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            tools=tools or [],
        )

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(method, url, headers=headers, json=body) as response:
                response.raise_for_status()
                parser = self.custom_config.get("response_parser", {})
                content_path = parser.get("content_path", "choices.0.delta.content")

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line == "[DONE]":
                        break
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    content = self._get_path(data, content_path)
                    if content:
                        yield content

                    tool_path = parser.get("tool_calls_path")
                    if tool_path:
                        tcs = self._get_path(data, tool_path)
                        if tcs:
                            for tc in tcs:
                                yield {
                                    "type": "tool_call",
                                    "id": tc.get("id", ""),
                                    "name": tc.get("function", {}).get("name", ""),
                                    "arguments": tc.get("function", {}).get("arguments", {}),
                                }

    def _get_path(self, data: dict, path: str) -> Any:
        parts = path.split(".")
        current: Any = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                current = current[int(part)] if int(part) < len(current) else None
            else:
                return None
            if current is None:
                return None
        return current


_CUSTOM_PROVIDERS: dict[str, type[LLMProvider]] = {}


def register_custom_provider(name: str, provider_cls: type[LLMProvider]) -> None:
    """Register a custom LLM provider class at runtime.

    Example:
        from claxcode.core.models import register_custom_provider, LLMProvider

        class MyProvider(LLMProvider):
            async def stream_chat(self, messages, tools=None):
                yield "Hello from my model!"

        register_custom_provider("my_model", MyProvider)
    """
    _CUSTOM_PROVIDERS[name.lower()] = provider_cls


def get_provider() -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider in _CUSTOM_PROVIDERS:
        return _CUSTOM_PROVIDERS[provider]()
    if provider == "openai":
        return OpenAIProvider()
    if provider == "anthropic":
        try:
            return AnthropicProvider()
        except ImportError as exc:
            return DummyProvider(
                reason=f"Failed to load provider '{provider}'. {exc}. "
                "Install the required package or choose a different LLM_PROVIDER."
            )
    if provider == "generic_openai":
        return GenericOpenAIProvider()
    if provider == "ollama":
        return OllamaProvider()
    if provider == "custom_http":
        return CustomHTTPProvider()
    return DummyProvider(
        reason=f"Unknown provider '{provider}'. "
        "Supported: openai, anthropic, generic_openai, ollama, custom_http."
    )
