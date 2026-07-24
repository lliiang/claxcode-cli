"""Tests for vision (multimodal image) support."""

import base64
from pathlib import Path

from claxcode.config import settings
from claxcode.core.context import ContextManager
from claxcode.core.images import is_image_file, load_image_part, make_image_part
from claxcode.core.models import _to_anthropic_content, _to_ollama_message
from claxcode.tools.base import attach_image, drain_images

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNgYGBgAAAABQABXvMqOgAAAABJRU5ErkJggg=="
)


def test_is_image_file():
    assert is_image_file(Path("a.png"))
    assert is_image_file(Path("b.JPG"))
    assert not is_image_file(Path("c.py"))


def test_make_image_part():
    part = make_image_part(PNG_1PX, "image/png")
    assert part is not None
    assert part["type"] == "image_url"
    assert part["image_url"]["url"].startswith("data:image/png;base64,")


def test_make_image_part_respects_vision_flag(monkeypatch):
    monkeypatch.setattr(settings, "llm_vision", False)
    assert make_image_part(PNG_1PX) is None


def test_make_image_part_rejects_oversize(monkeypatch):
    monkeypatch.setattr("claxcode.core.images.MAX_IMAGE_BYTES", 10)
    assert make_image_part(PNG_1PX) is None


def test_load_image_part(tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(PNG_1PX)
    assert load_image_part(img) is not None
    assert load_image_part(tmp_path / "missing.png") is None


def test_context_add_user_content():
    ctx = ContextManager(system_prompt="sys")
    part = {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}}
    ctx.add_user_content("看这张图", [part])
    msg = ctx.messages[-1]
    assert msg["role"] == "user"
    assert msg["content"][0] == {"type": "text", "text": "看这张图"}
    assert msg["content"][1] == part


def test_attach_and_drain_images(monkeypatch):
    monkeypatch.setattr(settings, "llm_vision", True)
    attach_image(PNG_1PX)
    images = drain_images()
    assert len(images) == 1
    assert drain_images() == []  # 已清空


def test_to_anthropic_content():
    part = {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}
    result = _to_anthropic_content([{"type": "text", "text": "hi"}, part])
    assert result[0] == {"type": "text", "text": "hi"}
    assert result[1] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "QUJD"},
    }
    assert _to_anthropic_content("plain") == "plain"


def test_to_ollama_message():
    part = {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}
    out = _to_ollama_message({"role": "user", "content": [{"type": "text", "text": "hi"}, part]})
    assert out["content"] == "hi"
    assert out["images"] == ["QUJD"]
    plain = {"role": "user", "content": "text"}
    assert _to_ollama_message(plain) == plain
