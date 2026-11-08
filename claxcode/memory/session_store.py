"""SQLite persistence for sessions using SQLAlchemy async."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from claxcode.config import settings
from claxcode.models.subagent import SubagentStatus, SubagentTask


class Base(DeclarativeBase):
    pass


class SessionORM(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="新会话")
    project_path: Mapped[str] = mapped_column(String(512), default=".")
    permission_mode: Mapped[str] = mapped_column(String(32), default="ask")
    messages: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class SubagentTaskORM(Base):
    __tablename__ = "subagent_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), default="")
    agent_type: Mapped[str] = mapped_column(String(32), default="explore")
    instruction: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    result: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LongTermMemoryORM(Base):
    """长期记忆表 - 全局记忆存储"""
    __tablename__ = "long_term_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    keywords: Mapped[str] = mapped_column(Text, default="")  # JSON 格式存储关键词列表
    compressed_content: Mapped[str] = mapped_column(Text, default="")  # 压缩后的核心内容
    project_path: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class ProjectMemoryORM(Base):
    """项目记忆表 - 项目级别存储"""
    __tablename__ = "project_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_path: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    initialized_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    config: Mapped[str] = mapped_column(Text, default="")  # JSON 格式存储项目配置
    context_summary: Mapped[str] = mapped_column(Text, default="")  # 项目上下文摘要
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


_engine = None
_session_maker = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url, echo=settings.debug)
    return _engine


def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_maker


async def init_db() -> None:
    """Initialize database tables."""
    # Ensure parent directory exists for SQLite file
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.replace("sqlite+aiosqlite:///", "").replace(
            "sqlite:///", ""
        )
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield an async DB session."""
    async with _get_session_maker()() as session:
        yield session


def _orm_to_subagent_task(row: SubagentTaskORM) -> SubagentTask:
    return SubagentTask(
        id=UUID(row.id),
        session_id=UUID(row.session_id),
        agent_type=row.agent_type,
        instruction=row.instruction,
        status=SubagentStatus(row.status),
        result=row.result,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


async def create_subagent_task(task: SubagentTask) -> None:
    """Persist a new subagent task."""
    async with _get_session_maker()() as db:
        db.add(
            SubagentTaskORM(
                id=str(task.id),
                session_id=str(task.session_id),
                agent_type=task.agent_type,
                instruction=task.instruction,
                status=task.status.value,
                result=task.result,
                created_at=task.created_at,
                completed_at=task.completed_at,
            )
        )
        await db.commit()


async def get_subagent_task(task_id: UUID) -> SubagentTask | None:
    """Load a subagent task by id, or None if it does not exist."""
    async with _get_session_maker()() as db:
        result = await db.execute(
            select(SubagentTaskORM).where(SubagentTaskORM.id == str(task_id))
        )
        row = result.scalar_one_or_none()
        return _orm_to_subagent_task(row) if row is not None else None


async def list_subagent_tasks(session_id: UUID, limit: int = 20) -> list[SubagentTask]:
    """List recent subagent tasks belonging to a session."""
    async with _get_session_maker()() as db:
        result = await db.execute(
            select(SubagentTaskORM)
            .where(SubagentTaskORM.session_id == str(session_id))
            .order_by(SubagentTaskORM.created_at.desc())
            .limit(limit)
        )
        return [_orm_to_subagent_task(row) for row in result.scalars().all()]


async def finish_subagent_task(task_id: UUID, status: SubagentStatus, result_text: str) -> None:
    """Mark a subagent task as completed/failed and store its result."""
    async with _get_session_maker()() as db:
        result = await db.execute(
            select(SubagentTaskORM).where(SubagentTaskORM.id == str(task_id))
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.status = status.value
        row.result = result_text
        row.completed_at = datetime.now(UTC)
        await db.commit()


async def save_session_messages(session_id: UUID, messages: list[dict[str, Any]]) -> None:
    """Persist conversation messages (excluding the system prompt) for a session.

    Creates the session row when it does not exist yet (e.g. CLI sessions).
    """
    async with _get_session_maker()() as db:
        result = await db.execute(select(SessionORM).where(SessionORM.id == str(session_id)))
        row = result.scalar_one_or_none()
        if row is None:
            row = SessionORM(id=str(session_id))
            db.add(row)
        row.messages = json.dumps(messages, ensure_ascii=False)
        await db.commit()


async def get_session_messages(session_id: UUID) -> list[dict[str, Any]]:
    """Load previously persisted conversation messages for a session."""
    async with _get_session_maker()() as db:
        result = await db.execute(
            select(SessionORM.messages).where(SessionORM.id == str(session_id))
        )
        raw = result.scalar_one_or_none()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []
