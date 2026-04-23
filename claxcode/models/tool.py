"""Tool-related models."""

from typing import Any
from pydantic import BaseModel


class ToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    category: str
    required_permissions: list[str]


class ToolInvokeRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


class ToolInvokeResponse(BaseModel):
    name: str
    output: str
    error: bool = False
