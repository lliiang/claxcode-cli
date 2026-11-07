"""Tests for LLM provider abstraction and custom model support."""

import json

import pytest

from claxcode.core.models import (
    PROVIDER_BASE_URLS,
    CustomHTTPProvider,
    DummyProvider,
    OllamaProvider,
    OpenAIProvider,
    _chat_completions_url,
    get_provider,
    register_custom_provider,
)


@pytest.mark.asyncio
async def test_dummy_provider():
    provider = DummyProvider()
    chunks = [c async for c in provider.stream_chat([{"role": "user", "content": "hi"}])]
    assert len(chunks) == 1
    assert "DummyProvider" in chunks[0]


@pytest.mark.asyncio
async def test_custom_provider_registration(monkeypatch):
    """Users can register their own provider at runtime."""

    class MyCustomProvider(DummyProvider):
        async def stream_chat(self, messages, tools=None):
            yield "CustomHello"

    register_custom_provider("my_custom", MyCustomProvider)
    monkeypatch.setattr("claxcode.core.models.settings.llm_provider", "my_custom")

    provider = get_provider()
    chunks = [c async for c in provider.stream_chat([])]
    assert chunks == ["CustomHello"]


def test_ollama_provider_parse_options(monkeypatch):
    monkeypatch.setattr(
        "claxcode.core.models.settings.llm_custom_config",
        json.dumps({"ollama_options": {"num_ctx": 8192, "seed": 42}}),
    )
    provider = OllamaProvider()
    assert provider.options == {"num_ctx": 8192, "seed": 42}


def test_custom_http_provider_load_config(monkeypatch):
    cfg = {
        "request_template": {
            "url": "http://localhost:8000/chat",
            "method": "POST",
            "headers": {"Authorization": "Bearer {api_key}"},
            "body": {"model": "{model}", "messages": "{messages}"},
        },
        "response_parser": {"content_path": "choices.0.delta.content"},
    }
    monkeypatch.setattr(
        "claxcode.core.models.settings.llm_custom_config", json.dumps(cfg)
    )
    provider = CustomHTTPProvider()
    assert provider.custom_config["request_template"]["url"] == "http://localhost:8000/chat"


def test_custom_http_provider_render_template():
    provider = CustomHTTPProvider()
    rendered = provider._render_template(
        {"model": "{model}", "temp": "{temperature}", "msgs": "{messages}"},
        model="test-model",
        temperature=0.5,
        messages=[{"role": "user"}],
    )
    assert rendered["model"] == "test-model"
    assert rendered["temp"] == "0.5"
    assert rendered["msgs"] == '[{"role": "user"}]'


def test_custom_http_provider_get_path():
    provider = CustomHTTPProvider()
    data = {"choices": [{"delta": {"content": "hello"}}]}
    assert provider._get_path(data, "choices.0.delta.content") == "hello"
    assert provider._get_path(data, "choices.1.delta.content") is None
    assert provider._get_path(data, "nonexistent.path") is None


async def test_openai_stream_preserves_reasoning_and_separates_tools(
    monkeypatch, httpx_mock
):
    monkeypatch.setattr("claxcode.core.models.settings.llm_base_url", "https://llm.test")
    monkeypatch.setattr("claxcode.core.models.settings.llm_api_key", "dummy")
    events = [
        {"choices": [{"delta": {"reasoning_content": "需要检查服务器"}}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0,
            "id": "call-1",
            "function": {"name": "run_shell", "arguments": '{"command":'},
        }]}}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "function": {"arguments": '"pwd"}'}
        }]}}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 1,
            "id": "call-2",
            "function": {"name": "run_shell", "arguments": '{"command":"uptime"}'},
        }]}}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    content = "\n".join(f"data: {json.dumps(event)}" for event in events) + "\ndata: [DONE]\n"
    httpx_mock.add_response(
        method="POST", url="https://llm.test/v1/chat/completions", content=content.encode()
    )

    chunks = [chunk async for chunk in OpenAIProvider().stream_chat([], tools=[])]
    tool_calls = [
        chunk
        for chunk in chunks
        if isinstance(chunk, dict) and chunk["type"] == "tool_call"
    ]
    assert chunks[0] == {"type": "reasoning_delta", "content": "需要检查服务器"}
    assert [call["arguments"] for call in tool_calls] == [
        {"command": "pwd"}, {"command": "uptime"}
    ]


def test_domestic_provider_presets(monkeypatch):
    monkeypatch.setattr("claxcode.core.models.settings.llm_base_url", "")
    for name, base_url in PROVIDER_BASE_URLS.items():
        monkeypatch.setattr("claxcode.core.models.settings.llm_provider", name)
        provider = get_provider()
        assert provider.base_url == base_url
        assert _chat_completions_url(provider.base_url).endswith("/chat/completions")
    assert _chat_completions_url(PROVIDER_BASE_URLS["zhipu"]).endswith("/v4/chat/completions")
    assert _chat_completions_url(PROVIDER_BASE_URLS["volcengine"]).endswith(
        "/api/v3/chat/completions"
    )
