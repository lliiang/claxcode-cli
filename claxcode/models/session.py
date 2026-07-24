"""Session and chat request models."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Session(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = "New Session"
    project_path: str = "."
    permission_mode: str = "ask"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SessionCreate(BaseModel):
    name: str = "New Session"
    project_path: str = "."
    permission_mode: str = "ask"


class ChatRequest(BaseModel):
    message: str
