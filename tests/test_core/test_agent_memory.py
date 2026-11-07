"""Tests for per-turn, scoped memory injection."""

from uuid import uuid4

from claxcode.core.agent import Agent


async def test_memories_refresh_without_duplication(tmp_path, monkeypatch):
    searches = []

    async def fake_get_project(project_path):
        return {"context_summary": "项目当前采用分层记忆"}

    async def fake_search(**kwargs):
        searches.append(kwargs)
        query = " ".join(kwargs.get("keywords") or [])
        content = "权限记忆" if "权限" in query else "浏览器记忆"
        return [{
            "compressed_content": content,
            "project_path": "" if "全局" in query else str(tmp_path),
        }]

    monkeypatch.setattr("claxcode.memory.project_memory.get_project", fake_get_project)
    monkeypatch.setattr("claxcode.memory.long_term_memory.search", fake_search)
    agent = Agent(session_id=uuid4(), project_path=str(tmp_path))

    await agent._load_memories("检查权限设计")
    assert agent.context.system_prompt.count("项目当前采用分层记忆") == 1
    assert "权限记忆" in agent.context.system_prompt

    await agent._load_memories("检查全局浏览器记忆")
    assert agent.context.system_prompt.count("项目当前采用分层记忆") == 1
    assert "权限记忆" not in agent.context.system_prompt
    assert "[全局] 浏览器记忆" in agent.context.system_prompt
    assert searches[0]["keywords"] == ["检查权限设计"]
    assert searches[0]["include_global"] is True


async def test_new_auto_memory_applies_to_current_agent(tmp_path, monkeypatch):
    from claxcode.memory.auto_memory import AutoMemory

    async def fake_get_project(project_path):
        return None

    async def fake_search(**kwargs):
        return []

    mem = AutoMemory(store_path=tmp_path / "auto.json")
    monkeypatch.setattr("claxcode.core.agent.auto_memory", mem)
    monkeypatch.setattr("claxcode.memory.project_memory.get_project", fake_get_project)
    monkeypatch.setattr("claxcode.memory.long_term_memory.search", fake_search)
    agent = Agent(session_id=uuid4(), project_path=str(tmp_path))

    await agent._load_memories("你好")
    assert "简洁回答" not in agent.context.system_prompt
    mem.remember("回答风格", "简洁回答")
    await agent._load_memories("继续")
    assert agent.context.system_prompt.count("简洁回答") == 1

    async def fail_get_project(project_path):
        raise OSError("database unavailable")

    monkeypatch.setattr("claxcode.memory.project_memory.get_project", fail_get_project)
    await agent._load_memories("数据库异常")
    assert agent.context.system_prompt.count("简洁回答") == 1
