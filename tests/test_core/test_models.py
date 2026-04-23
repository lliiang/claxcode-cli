"""Tests for LLM provider abstraction and custom model support."""

import json

import pytest

from claxcode.core.models import (
    CustomHTTPProvider,
    DummyProvider,
    OllamaProvider,
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
