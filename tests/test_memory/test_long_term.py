"""Tests for long-term memory CRUD (regression: /memory list)."""

from uuid import uuid4

from claxcode.memory import init_db, long_term_memory


async def test_save_list_search_delete_roundtrip():
    await init_db()
    sid = str(uuid4())

    memory_id = await long_term_memory.save(
        session_id=sid,
        compressed_content="讨论了权限系统重构方案",
        keywords=["权限", "重构"],
        project_path="/tmp/proj",
    )
    assert memory_id

    all_memories = await long_term_memory.list_all(limit=10)
    assert any(m["compressed_content"] == "讨论了权限系统重构方案" for m in all_memories)

    found = await long_term_memory.search(keywords=["权限"], project_path="/tmp/proj")
    assert any(m["id"] == memory_id for m in found)

    assert await long_term_memory.delete(memory_id) is True
    assert await long_term_memory.delete(memory_id) is False


async def test_search_filters_by_project():
    await init_db()
    await long_term_memory.save(
        session_id=str(uuid4()),
        compressed_content="项目A的记忆",
        keywords=[],
        project_path="/tmp/projA",
    )
    found = await long_term_memory.search(project_path="/tmp/projA")
    assert all(m["project_path"] == "/tmp/projA" for m in found)
