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
        # 确保路径标准化
        project_path = str(Path(project_path).resolve())

        async for db in get_db_session():
            db: AsyncSession
            # 检查是否已存在
            result = await db.execute(
                select(ProjectMemoryORM).where(ProjectMemoryORM.project_path == project_path)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # 更新现有配置
                existing.config = json.dumps(config, ensure_ascii=False)
                existing.updated_at = datetime.now(UTC)
                await db.commit()
                return existing.id
            else:
                # 创建新的项目记忆
                memory_id = str(uuid4())
                memory = ProjectMemoryORM(
                    id=memory_id,
                    project_path=project_path,
                    initialized_at=datetime.now(UTC),
                    config=json.dumps(config, ensure_ascii=False),
                    context_summary="",
                    updated_at=datetime.now(UTC),
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

            if memory:
                memory.context_summary = summary
                memory.updated_at = datetime.now(UTC)
                await db.commit()
                return True
            return False

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
                    "initialized_at": m.initialized_at.isoformat(),
                    "updated_at": m.updated_at.isoformat(),
                    "has_summary": bool(m.context_summary),
                }
                for m in memories
            ]

    def generate_context_md(self, config: dict[str, Any]) -> str:
        """生成 CLAUDE.md 文件内容.

        Args:
            config: 项目配置

        Returns:
            Markdown 格式的项目上下文
        """
        lines = [
            f"# {config.get('name', '未命名项目')}",
            "",
            "## 项目描述",
            config.get('description', ''),
            "",
            "## 技术栈",
            config.get('tech_stack', ''),
            "",
            "## 常用命令",
            "",
            "### 构建",
            f"```bash\n{config.get('build_command', '')}\n```",
            "",
            "### 测试",
            f"```bash\n{config.get('test_command', '')}\n```",
            "",
            "## 代码风格",
            config.get('code_style', ''),
            "",
            "## 其他说明",
            config.get('notes', ''),
        ]
        return "\n".join(lines)


# 全局实例
project_memory = ProjectMemory()
