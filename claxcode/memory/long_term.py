"""长期记忆管理器 - 全局记忆存储."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from claxcode.memory.session_store import LongTermMemoryORM, get_db_session


class LongTermMemory:
    """管理全局长期记忆."""

    async def save(
        self,
        session_id: str,
        compressed_content: str,
        keywords: list[str],
        project_path: str = "",
    ) -> str:
        """保存长期记忆.

        Args:
            session_id: 会话ID
            compressed_content: 压缩后的核心内容
            keywords: 关键词列表
            project_path: 关联的项目路径

        Returns:
            记忆ID
        """
        memory_id = str(uuid4())
        async for db in get_db_session():
            db: AsyncSession
            memory = LongTermMemoryORM(
                id=memory_id,
                session_id=session_id,
                timestamp=datetime.now(UTC),
                keywords=json.dumps(keywords, ensure_ascii=False),
                compressed_content=compressed_content,
                project_path=project_path,
            )
            db.add(memory)
            await db.commit()
            return memory_id

    async def search(
        self,
        keywords: list[str] | None = None,
        project_path: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """搜索长期记忆.

        Args:
            keywords: 关键词列表
            project_path: 项目路径过滤
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        async for db in get_db_session():
            db: AsyncSession
            query = select(LongTermMemoryORM).order_by(desc(LongTermMemoryORM.timestamp))

            if project_path:
                query = query.where(LongTermMemoryORM.project_path == project_path)

            if keywords:
                conditions = []
                for kw in keywords:
                    conditions.append(LongTermMemoryORM.compressed_content.contains(kw))
                    conditions.append(LongTermMemoryORM.keywords.contains(kw))
                if conditions:
                    query = query.where(or_(*conditions))

            result = await db.execute(query.limit(limit))
            memories = result.scalars().all()

            return [
                {
                    "id": m.id,
                    "timestamp": m.timestamp.isoformat(),
                    "keywords": json.loads(m.keywords) if m.keywords else [],
                    "compressed_content": m.compressed_content,
                    "project_path": m.project_path,
                }
                for m in memories
            ]

    async def list_all(self, limit: int = 50) -> list[dict[str, Any]]:
        """列出所有长期记忆.

        Args:
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        async for db in get_db_session():
            db: AsyncSession
            result = await db.execute(
                select(LongTermMemoryORM).order_by(desc(LongTermMemoryORM.timestamp)).limit(limit)
            )
            memories = result.scalars().all()
            return [
                {
                    "id": m.id,
                    "timestamp": m.timestamp.isoformat(),
                    "keywords": json.loads(m.keywords) if m.keywords else [],
                    "compressed_content": m.compressed_content[:200] + "..." if len(m.compressed_content) > 200 else m.compressed_content,
                    "project_path": m.project_path,
                }
                for m in memories
            ]

    async def delete(self, memory_id: str) -> bool:
        """删除长期记忆.

        Args:
            memory_id: 记忆ID

        Returns:
            是否成功删除
        """
        async for db in get_db_session():
            db: AsyncSession
            result = await db.execute(select(LongTermMemoryORM).where(LongTermMemoryORM.id == memory_id))
            memory = result.scalar_one_or_none()
            if memory:
                await db.delete(memory)
                await db.commit()
                return True
            return False

    async def export_to_file(self, filepath: str, project_path: str | None = None) -> int:
        """导出记忆到文件.

        Args:
            filepath: 导出文件路径
            project_path: 可选的项目路径过滤

        Returns:
            导出的记忆数量
        """
        from pathlib import Path

        memories = await self.search(project_path=project_path, limit=1000)
        export_data = {
            "export_time": datetime.now(UTC).isoformat(),
            "memories": memories,
        }

        Path(filepath).write_text(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return len(memories)

    async def import_from_file(self, filepath: str) -> int:
        """从文件导入记忆.

        Args:
            filepath: 导入文件路径

        Returns:
            导入的记忆数量
        """
        from pathlib import Path

        data = json.loads(Path(filepath).read_text(encoding="utf-8"))
        memories = data.get("memories", [])

        count = 0
        async for db in get_db_session():
            db: AsyncSession
            for m in memories:
                memory = LongTermMemoryORM(
                    id=str(uuid4()),
                    session_id=m.get("session_id", ""),
                    timestamp=datetime.fromisoformat(m["timestamp"]),
                    keywords=json.dumps(m.get("keywords", []), ensure_ascii=False),
                    compressed_content=m.get("compressed_content", ""),
                    project_path=m.get("project_path", ""),
                )
                db.add(memory)
                count += 1
            await db.commit()

        return count


# 全局实例
long_term_memory = LongTermMemory()
