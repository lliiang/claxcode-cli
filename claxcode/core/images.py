"""Image attachment helpers for multimodal (vision) conversations.

Canonical internal format is the OpenAI content part:
    {"type": "image_url", "image_url": {"url": "data:<media>;base64,<data>"}}
Providers convert it to their native format (Anthropic image source,
Ollama images field); OpenAI-compatible APIs pass it through as-is.
"""

import base64
from pathlib import Path

from claxcode.config import settings

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 单张图片上限 5MB


def is_image_file(path: Path) -> bool:
    """Whether the path looks like a supported image file."""
    return path.suffix.lower() in IMAGE_EXTENSIONS


def make_image_part(data: bytes, media_type: str = "image/png") -> dict | None:
    """Build an image_url content part from raw bytes (None when vision is off/oversized)."""
    if not settings.llm_vision or not data or len(data) > MAX_IMAGE_BYTES:
        return None
    b64 = base64.b64encode(data).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}}


def load_image_part(path: Path) -> dict | None:
    """Read an image file into an image_url content part."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return make_image_part(data, MEDIA_TYPES.get(path.suffix.lower(), "image/png"))
