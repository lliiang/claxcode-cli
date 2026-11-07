"""Tests for scoped long-term memory CRUD and relevance search."""

from pathlib import Path
from uuid import uuid4

import pytest

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
    project_path = str(Path("/tmp/projA").resolve())
    memory_id = await long_term_memory.save(
        session_id=str(uuid4()),
        compressed_content="项目A的记忆",
        keywords=[],
        project_path="/tmp/projA",
    )
    found = await long_term_memory.search(project_path="/tmp/projA")
    assert any(m["id"] == memory_id for m in found)
    assert all(m["project_path"] == project_path for m in found)


async def test_chinese_relevance_and_scopes(tmp_path):
    await init_db()
    project = str(tmp_path / "project")
    other = str(tmp_path / "other")
    memory_ids = []
    try:
        memory_ids.append(await long_term_memory.save(
            session_id=str(uuid4()),
            compressed_content="权限系统采用分层审批，写操作需要确认",
            keywords=["权限", "安全"],
            project_path=project,
        ))
        memory_ids.append(await long_term_memory.save(
            session_id=str(uuid4()),
            compressed_content="浏览器会话会自动保存截图",
            keywords=["浏览器"],
            project_path=project,
        ))
        memory_ids.append(await long_term_memory.save(
            session_id=str(uuid4()),
            compressed_content="其他项目的权限设计",
            keywords=["权限"],
            project_path=other,
        ))
        global_id = await long_term_memory.save(
            session_id=str(uuid4()),
            compressed_content="用户全局偏好：回答始终使用中文",
            keywords=["中文", "偏好"],
        )
        memory_ids.append(global_id)

        found = await long_term_memory.search(
            keywords=["请继续检查权限系统"],
            project_path=project,
            include_global=True,
        )
        assert found[0]["compressed_content"].startswith("权限系统")
        assert all(m["project_path"] != str(Path(other).resolve()) for m in found)

        global_found = await long_term_memory.search(
            keywords=["中文回答"], project_path=project, include_global=True
        )
        assert any(m["id"] == global_id for m in global_found)

        project_only = await long_term_memory.list_all(
            project_path=project, include_global=False
        )
        assert project_only
        assert all(m["project_path"] == str(Path(project).resolve()) for m in project_only)
    finally:
        for memory_id in memory_ids:
            await long_term_memory.delete(memory_id)


async def test_empty_memory_is_rejected():
    await init_db()
    with pytest.raises(ValueError, match="不能为空"):
        await long_term_memory.save(str(uuid4()), "  ", [])
