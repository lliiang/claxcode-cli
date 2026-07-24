"""Tool base class."""

from abc import ABC, abstractmethod
from typing import Any

from claxcode.core.images import make_image_part


class Tool(ABC):
    """Base class for all ClaxCode tools."""

    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = {}
    category: str = "general"
    required_permissions: list[str] = []

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return a string result."""
        ...


# Tools may attach images for the model to see (e.g. browser screenshots).
# The agent loop drains this collector after each tool call and injects
# the images into the conversation as content parts.
_pending_images: list[dict[str, Any]] = []


def attach_image(data: bytes, media_type: str = "image/png") -> None:
    """Attach an image to the current tool call's result for the model to see."""
    part = make_image_part(data, media_type)
    if part is not None:
        _pending_images.append(part)


def drain_images() -> list[dict[str, Any]]:
    """Take all pending images (called by the agent loop after each tool call)."""
    images = list(_pending_images)
    _pending_images.clear()
    return images
