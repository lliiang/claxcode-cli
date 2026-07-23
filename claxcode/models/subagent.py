"""Subagent models."""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SubagentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SubagentTask(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    agent_type: str = "explore"  # explore | planner | executor
    instruction: str
    status: SubagentStatus = SubagentStatus.PENDING
    result: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
