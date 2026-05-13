"""SQLite persistence for sessions using SQLAlchemy async."""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from claxcode.config import settings


class Base(DeclarativeBase):
    pass


class SessionORM(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="新会话")
    project_path: Mapped[str] = mapped_column(String(512), default=".")
    permission_mode: Mapped[str] = mapped_column(String(32), default="ask")
    messages: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SubagentTaskORM(Base):
    __tablename__ = "subagent_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), default="")
    agent_type: Mapped[str] = mapped_column(String(32), default="explore")
    instruction: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    result: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LongTermMemoryORM(Base):
    """长期记忆表 - 全局记忆存储"""
    __tablename__ = "long_term_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    keywords: Mapped[str] = mapped_column(Text, default="")  # JSON 格式存储关键词列表
    compressed_content: Mapped[str] = mapped_column(Text, default="")  # 压缩后的核心内容
    project_path: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class ShortTermMemoryORM(Base):
    """短期记忆表 - 会话级别存储"""
    __tablename__ = "short_term_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    is_compressed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class ProjectMemoryORM(Base):
    """项目记忆表 - 项目级别存储"""
    __tablename__ = "project_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_path: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    initialized_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    config: Mapped[str] = mapped_column(Text, default="")  # JSON 格式存储项目配置
    context_summary: Mapped[str] = mapped_column(Text, default="")  # 项目上下文摘要
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


_engine = None
_session_maker = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url, echo=settings.debug)
    return _engine


def _get_session_maker():
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_maker


async def init_db():
    """Initialize database tables."""
    # Ensure parent directory exists for SQLite file
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db_session():
    """Yield an async DB session."""
    async with _get_session_maker()() as session:
        yield session
