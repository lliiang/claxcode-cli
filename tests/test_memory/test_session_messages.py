"""Tests for session message persistence."""

from uuid import uuid4

from claxcode.memory import init_db
from claxcode.memory.session_store import get_session_messages, save_session_messages


async def test_save_and_load_roundtrip():
    await init_db()
    sid = uuid4()
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么可以帮你？"},
    ]
    await save_session_messages(sid, messages)
    assert await get_session_messages(sid) == messages


async def test_load_missing_returns_empty():
    await init_db()
    assert await get_session_messages(uuid4()) == []


async def test_overwrite_existing():
    await init_db()
    sid = uuid4()
    await save_session_messages(sid, [{"role": "user", "content": "first"}])
    await save_session_messages(sid, [{"role": "user", "content": "second"}])
    assert await get_session_messages(sid) == [{"role": "user", "content": "second"}]
