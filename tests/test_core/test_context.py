"""Tests for ContextManager compression primitives."""

from claxcode.core.context import ContextManager


def test_pop_oldest_keeps_system_and_returns_removed():
    ctx = ContextManager(system_prompt="sys")
    for i in range(6):
        ctx.add_message("user", f"msg {i}")

    removed = ctx.pop_oldest(2)

    assert [m["content"] for m in removed] == ["msg 0", "msg 1"]
    assert ctx.messages[0]["role"] == "system"
    assert ctx.messages[1]["content"] == "msg 2"


def test_pop_oldest_drops_orphan_tool_results():
    ctx = ContextManager(system_prompt="sys")
    ctx.add_message("user", "q")
    ctx.messages.append({"role": "tool", "tool_call_id": "x", "content": "out"})

    removed = ctx.pop_oldest(1)

    assert len(removed) == 2
    assert all(m.get("role") != "tool" for m in ctx.messages[1:])


def test_insert_summary_goes_after_system_prompt():
    ctx = ContextManager(system_prompt="sys")
    ctx.add_message("user", "hello")

    ctx.insert_summary("summary")

    assert ctx.messages[1] == {"role": "system", "content": "summary"}


def test_hard_compress_drops_orphan_tool_results():
    ctx = ContextManager(system_prompt="sys")
    ctx.messages.append({"role": "tool", "tool_call_id": "x", "content": "out"})
    ctx.add_message("user", "hello")

    ctx._maybe_compress()

    assert ctx.messages[1]["role"] == "user"


def test_restore_appends_and_drops_orphan_tool_results():
    ctx = ContextManager(system_prompt="sys")
    ctx.restore([
        {"role": "tool", "tool_call_id": "x", "content": "out"},
        {"role": "user", "content": "hello"},
    ])

    assert ctx.messages[0]["role"] == "system"
    assert ctx.messages[1] == {"role": "user", "content": "hello"}


def test_restore_empty_is_noop():
    ctx = ContextManager(system_prompt="sys")
    ctx.restore([])
    assert len(ctx.messages) == 1


def test_restore_drops_orphan_assistant_tool_calls():
    ctx = ContextManager(system_prompt="sys")
    ctx.restore([
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "x"}}],
        },
    ])

    assert len(ctx.messages) == 2
    assert ctx.messages[1] == {"role": "user", "content": "hi"}


def test_restore_keeps_valid_tool_call_pairs():
    ctx = ContextManager(system_prompt="sys")
    ctx.restore([
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "x"}}],
        },
        {"role": "tool", "tool_call_id": "tc1", "content": "out"},
    ])

    assert len(ctx.messages) == 4
    assert ctx.messages[2]["role"] == "assistant"
    assert ctx.messages[3] == {"role": "tool", "tool_call_id": "tc1", "content": "out"}
