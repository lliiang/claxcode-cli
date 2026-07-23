"""Tests for the durable auto-memory store."""

from claxcode.memory.auto_memory import AutoMemory


def test_remember_and_recall(tmp_path):
    mem = AutoMemory(store_path=tmp_path / "auto.json")
    assert mem.remember("回复语言", "中文") == "已记住: 回复语言"
    assert mem.recall("回复语言") == "中文"


def test_persistence_across_instances(tmp_path):
    path = tmp_path / "auto.json"
    AutoMemory(store_path=path).remember("k", "v")
    assert AutoMemory(store_path=path).recall("k") == "v"


def test_forget(tmp_path):
    mem = AutoMemory(store_path=tmp_path / "auto.json")
    mem.remember("k", "v")
    assert mem.forget("k") is True
    assert mem.recall("k") is None
    assert mem.forget("k") is False


def test_limit_still_allows_updates(tmp_path):
    mem = AutoMemory(store_path=tmp_path / "auto.json", limit=2)
    mem.remember("a", "1")
    mem.remember("b", "2")
    assert "已满" in mem.remember("c", "3")
    assert mem.remember("a", "9") == "已记住: a"
    assert mem.recall("a") == "9"


def test_corrupt_file_tolerated(tmp_path):
    path = tmp_path / "auto.json"
    path.write_text("not json", encoding="utf-8")
    assert AutoMemory(store_path=path).items() == {}


def test_prompt_fragment(tmp_path):
    mem = AutoMemory(store_path=tmp_path / "auto.json")
    assert mem.to_prompt_fragment() == ""
    mem.remember("风格", "简洁")
    assert "风格: 简洁" in mem.to_prompt_fragment()
