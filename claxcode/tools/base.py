"""Tool base class."""

from abc import ABC, abstractmethod
from typing import Any


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
