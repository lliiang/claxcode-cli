"""项目记忆管理器 - 项目级别存储."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from claxcode.memory.session_store import ProjectMemoryORM, get_db_session


class ProjectMemory:
    """管理项目级别记忆."""

    async def init_project(
        self,
        project_path: str,
        config: dict[str, Any],
    ) -> str:
        """初始化项目记忆.

        Args:
            project_path: 项目路径
            config: 项目配置信息

        Returns:
            项目记忆ID
        """
        project_path = str(Path(project_path).resolve())
        config = dict(config)
        now = datetime.now(UTC)

        async for db in get_db_session():
            db: AsyncSession
            result = await db.execute(
                select(ProjectMemoryORM).where(ProjectMemoryORM.project_path == project_path)
            )
            existing = result.scalar_one_or_none()

            if existing:
                previous = json.loads(existing.config) if existing.config else {}
                initialized_at = (
                    previous.get("initialized_at") or existing.initialized_at.isoformat()
                )
                config.setdefault("initialized_at", initialized_at)
                existing.config = json.dumps(config, ensure_ascii=False)
                existing.updated_at = now
                await db.commit()
                return existing.id
            else:
                config.setdefault("initialized_at", now.isoformat())
                memory_id = str(uuid4())
                memory = ProjectMemoryORM(
                    id=memory_id,
                    project_path=project_path,
                    initialized_at=now,
                    config=json.dumps(config, ensure_ascii=False),
                    context_summary="",
                    updated_at=now,
                )
                db.add(memory)
                await db.commit()
                return memory_id

    async def get_project(self, project_path: str) -> dict[str, Any] | None:
        """获取项目记忆.

        Args:
            project_path: 项目路径

        Returns:
            项目记忆信息，不存在则返回 None
        """
        project_path = str(Path(project_path).resolve())

        async for db in get_db_session():
            db: AsyncSession
            result = await db.execute(
                select(ProjectMemoryORM).where(ProjectMemoryORM.project_path == project_path)
            )
            memory = result.scalar_one_or_none()

            if memory:
                return {
                    "id": memory.id,
                    "project_path": memory.project_path,
                    "initialized_at": memory.initialized_at.isoformat(),
                    "config": json.loads(memory.config) if memory.config else {},
                    "context_summary": memory.context_summary,
                    "updated_at": memory.updated_at.isoformat(),
                }
            return None

    async def update_summary(self, project_path: str, summary: str) -> bool:
        """更新项目上下文摘要.

        Args:
            project_path: 项目路径
            summary: 摘要内容

        Returns:
            是否成功更新
        """
        project_path = str(Path(project_path).resolve())

        async for db in get_db_session():
            db: AsyncSession
            result = await db.execute(
                select(ProjectMemoryORM).where(ProjectMemoryORM.project_path == project_path)
            )
            memory = result.scalar_one_or_none()

            now = datetime.now(UTC)
            if memory is None:
                memory = ProjectMemoryORM(
                    id=str(uuid4()),
                    project_path=project_path,
                    initialized_at=now,
                    config="",
                    context_summary=summary,
                    updated_at=now,
                )
                db.add(memory)
            else:
                memory.context_summary = summary
                memory.updated_at = now
            await db.commit()
            return True

    async def list_all_projects(self, limit: int = 100) -> list[dict[str, Any]]:
        """列出所有项目.

        Args:
            limit: 返回数量限制

        Returns:
            项目列表
        """
        async for db in get_db_session():
            db: AsyncSession
            result = await db.execute(
                select(ProjectMemoryORM)
                .order_by(ProjectMemoryORM.updated_at.desc())
                .limit(limit)
            )
            memories = result.scalars().all()
            return [
                {
                    "id": m.id,
                    "project_path": m.project_path,
                    "name": Path(m.project_path).name,
                    "description": (
                        json.loads(m.config).get("description", "") if m.config else ""
                    ),
                    "initialized_at": m.initialized_at.isoformat(),
                    "updated_at": m.updated_at.isoformat(),
                    "has_summary": bool(m.context_summary),
                }
                for m in memories
            ]

    def generate_context_md(self, config: dict[str, Any]) -> str:
        """生成 AGENT.md 文件内容.

        Args:
            config: 项目配置

        Returns:
            Markdown 格式的项目上下文
        """
        lines = [
            f"# {config.get('name', '未命名项目')}",
            "",
            "## 项目描述",
            config.get("description") or "暂无描述。",
        ]
        if config.get("initialized_at"):
            lines.extend(["", "## 初始化时间", config["initialized_at"]])
        return "\n".join(lines) + "\n"


# 全局实例
project_memory = ProjectMemory()
