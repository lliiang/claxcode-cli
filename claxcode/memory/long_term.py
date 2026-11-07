"""Searchable long-term memories with project and global scopes."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, or_, select

from claxcode.memory.session_store import LongTermMemoryORM, get_db_session

_STOP_TERMS = {
    "我们", "你们", "他们", "这个", "那个", "可以", "怎么", "什么", "一下",
    "帮我", "谢谢", "现在", "还是", "就是", "因为", "所以", "如果", "已经", "继续",
}


def _normalize_project_path(project_path: str) -> str:
    return str(Path(project_path).resolve()) if project_path else ""


def _search_terms(keywords: list[str] | None) -> list[str]:
    """Build searchable words and Chinese bigrams without external tokenizers."""
    if not keywords:
        return []
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", " ".join(keywords).lower()):
        if re.fullmatch(r"[a-z0-9_]+", token):
            if len(token) >= 2:
                terms.add(token)
            continue
        if len(token) <= 6 and token not in _STOP_TERMS:
            terms.add(token)
        terms.update(
            token[i:i + 2]
            for i in range(len(token) - 1)
            if token[i:i + 2] not in _STOP_TERMS
        )
    return sorted(terms, key=lambda term: (-len(term), term))[:60]


def _relevance(memory: LongTermMemoryORM, terms: list[str]) -> int:
    text = f"{memory.keywords}\n{memory.compressed_content}".lower()
    return sum(len(term) if len(term) > 2 else 1 for term in terms if term in text)


def _to_dict(memory: LongTermMemoryORM, truncate: bool = False) -> dict[str, Any]:
    content = memory.compressed_content
    if truncate and len(content) > 200:
        content = content[:200] + "..."
    return {
        "id": memory.id,
        "session_id": memory.session_id,
        "timestamp": memory.timestamp.isoformat(),
        "keywords": json.loads(memory.keywords) if memory.keywords else [],
        "compressed_content": content,
        "project_path": memory.project_path,
    }


class LongTermMemory:
    """Manage searchable project memories and cross-project global memories."""

    async def save(
        self,
        session_id: str,
        compressed_content: str,
        keywords: list[str],
        project_path: str = "",
    ) -> str:
        """Save a memory; an empty project_path means global scope."""
        content = compressed_content.strip()
        if not content:
            raise ValueError("记忆内容不能为空")
        memory_id = str(uuid4())
        normalized_keywords = list(dict.fromkeys(k.strip() for k in keywords if k.strip()))
        async for db in get_db_session():
            memory = LongTermMemoryORM(
                id=memory_id,
                session_id=session_id,
                timestamp=datetime.now(UTC),
                keywords=json.dumps(normalized_keywords, ensure_ascii=False),
                compressed_content=content,
                project_path=_normalize_project_path(project_path),
            )
            db.add(memory)
            await db.commit()
            return memory_id
        return memory_id

    async def search(
        self,
        keywords: list[str] | None = None,
        project_path: str | None = None,
        limit: int = 10,
        include_global: bool = False,
    ) -> list[dict[str, Any]]:
        """Search by relevance within a project, optionally including global memories."""
        terms = _search_terms(keywords)
        normalized_path = _normalize_project_path(project_path or "")
        async for db in get_db_session():
            query = select(LongTermMemoryORM).order_by(desc(LongTermMemoryORM.timestamp))
            if normalized_path:
                if include_global:
                    query = query.where(
                        or_(
                            LongTermMemoryORM.project_path == normalized_path,
                            LongTermMemoryORM.project_path == "",
                        )
                    )
                else:
                    query = query.where(LongTermMemoryORM.project_path == normalized_path)

            result = await db.execute(query.limit(200 if terms else limit))
            memories = list(result.scalars().all())
            if terms:
                memories = [m for m in memories if _relevance(m, terms) > 0]
                memories.sort(key=lambda m: _relevance(m, terms), reverse=True)
            return [_to_dict(m) for m in memories[:limit]]
        return []

    async def list_all(
        self,
        limit: int = 50,
        project_path: str | None = None,
        include_global: bool = False,
    ) -> list[dict[str, Any]]:
        """List recent memories, optionally restricted to project and global scopes."""
        normalized_path = _normalize_project_path(project_path or "")
        async for db in get_db_session():
            query = select(LongTermMemoryORM).order_by(desc(LongTermMemoryORM.timestamp))
            if normalized_path:
                if include_global:
                    query = query.where(
                        or_(
                            LongTermMemoryORM.project_path == normalized_path,
                            LongTermMemoryORM.project_path == "",
                        )
                    )
                else:
                    query = query.where(LongTermMemoryORM.project_path == normalized_path)
            result = await db.execute(query.limit(limit))
            return [_to_dict(m, truncate=True) for m in result.scalars().all()]
        return []

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        async for db in get_db_session():
            result = await db.execute(
                select(LongTermMemoryORM).where(LongTermMemoryORM.id == memory_id)
            )
            memory = result.scalar_one_or_none()
            if memory:
                await db.delete(memory)
                await db.commit()
                return True
            return False
        return False

    async def export_to_file(self, filepath: str, project_path: str | None = None) -> int:
        """Export memories to JSON."""
        memories = await self.search(project_path=project_path, limit=1000)
        export_data = {
            "export_time": datetime.now(UTC).isoformat(),
            "memories": memories,
        }
        Path(filepath).write_text(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return len(memories)

    async def import_from_file(self, filepath: str) -> int:
        """Import memories from JSON without reusing their original IDs."""
        data = json.loads(Path(filepath).read_text(encoding="utf-8"))
        memories = data.get("memories", [])
        count = 0
        async for db in get_db_session():
            for item in memories:
                memory = LongTermMemoryORM(
                    id=str(uuid4()),
                    session_id=item.get("session_id", ""),
                    timestamp=datetime.fromisoformat(item["timestamp"]),
                    keywords=json.dumps(item.get("keywords", []), ensure_ascii=False),
                    compressed_content=item.get("compressed_content", ""),
                    project_path=_normalize_project_path(item.get("project_path", "")),
                )
                db.add(memory)
                count += 1
            await db.commit()
        return count


long_term_memory = LongTermMemory()
