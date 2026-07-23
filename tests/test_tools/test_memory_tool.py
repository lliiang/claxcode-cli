"""Tests for the remember_fact tool."""

from claxcode.memory.auto_memory import AutoMemory
from claxcode.tools.memory_tool import RememberFactTool


async def test_remember_fact_records(tmp_path, monkeypatch):
    mem = AutoMemory(store_path=tmp_path / "auto.json")
    monkeypatch.setattr("claxcode.tools.memory_tool.auto_memory", mem)

    tool = RememberFactTool()
    result = await tool.execute(key="回复语言", value="中文")

    assert "已记住" in result
    assert mem.recall("回复语言") == "中文"
