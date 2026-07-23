"""短期记忆管理器 - 会话级别存储."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from claxcode.memory.session_store import ShortTermMemoryORM, get_db_session


class ShortTermMemory:
    """管理会话短期记忆."""

    async def save(
        self,
        session_id: str,
        content: str,
        is_compressed: bool = False,
    ) -> str:
        """保存短期记忆.

        Args:
            session_id: 会话ID
            content: 记忆内容
            is_compressed: 是否已压缩

        Returns:
            记忆ID
        """
        memory_id = str(uuid4())
        async for db in get_db_session():
            db: AsyncSession
            memory = ShortTermMemoryORM(
                id=memory_id,
                session_id=session_id,
                content=content,
                is_compressed=is_compressed,
                created_at=datetime.now(UTC),
            )
            db.add(memory)
            await db.commit()
            return memory_id

    async def get_by_session(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """获取指定会话的短期记忆.

        Args:
            session_id: 会话ID
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        async for db in get_db_session():
            db: AsyncSession
            result = await db.execute(
                select(ShortTermMemoryORM)
                .where(ShortTermMemoryORM.session_id == session_id)
                .order_by(desc(ShortTermMemoryORM.created_at))
                .limit(limit)
            )
            memories = result.scalars().all()
            return [
                {
                    "id": m.id,
                    "content": m.content,
                    "is_compressed": m.is_compressed,
                    "created_at": m.created_at.isoformat(),
                }
                for m in memories
            ]

    async def clear_session(self, session_id: str) -> int:
        """清空指定会话的所有短期记忆.

        Args:
            session_id: 会话ID

        Returns:
            删除的记忆数量
        """
        async for db in get_db_session():
            db: AsyncSession
            result = await db.execute(
                delete(ShortTermMemoryORM).where(ShortTermMemoryORM.session_id == session_id)
            )
            await db.commit()
            return result.rowcount

    async def delete(self, memory_id: str) -> bool:
        """删除单条短期记忆.

        Args:
            memory_id: 记忆ID

        Returns:
            是否成功删除
        """
        async for db in get_db_session():
            db: AsyncSession
            result = await db.execute(
                select(ShortTermMemoryORM).where(ShortTermMemoryORM.id == memory_id)
            )
            memory = result.scalar_one_or_none()
            if memory:
                await db.delete(memory)
                await db.commit()
                return True
            return False

    async def get_content_for_compression(
        self,
        session_id: str,
        limit: int = 100,
    ) -> str:
        """获取用于压缩的记忆内容.

        Args:
            session_id: 会话ID
            limit: 获取数量限制

        Returns:
            合并后的记忆内容
        """
        memories = await self.get_by_session(session_id, limit=limit)
        if not memories:
            return ""

        # 按时间顺序排列（最早的在前）
        memories.reverse()

        contents = []
        for m in memories:
            if not m["is_compressed"]:
                contents.append(m["content"])

        return "\n\n".join(contents)


# 全局实例
short_term_memory = ShortTermMemory()
