"""Tests for admin_add_tool."""

import pytest

from claxcode.tools.admin import AdminAddTool
from claxcode.tools.registry import registry


@pytest.mark.asyncio
async def test_admin_add_tool_success():
    tool = AdminAddTool()
    result = await tool.execute(
        name="greet",
        description="Say hello to someone.",
        code='''name = kwargs.get("name", "world")
return f"Hello, {name}!"
''',
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name to greet"}
            },
            "required": ["name"],
        },
    )
    assert "已成功注册" in result
    # Verify it was added to registry
    assert registry.get("greet") is not None
    # Execute the new tool
    greet_tool = registry.get("greet")
    assert greet_tool is not None
    output = await greet_tool.execute(name="Alice")
    assert output == "Hello, Alice!"


@pytest.mark.asyncio
async def test_admin_add_tool_duplicate():
    tool = AdminAddTool()
    # First registration
    await tool.execute(name="dup_test", description="x", code="return 'x'")
    # Second registration should fail
    result = await tool.execute(name="dup_test", description="x", code="return 'x'")
    assert "已存在" in result


@pytest.mark.asyncio
async def test_admin_add_tool_invalid_name():
    tool = AdminAddTool()
    result = await tool.execute(name="bad-name!", description="x", code="return 'x'")
    assert "字母数字" in result


@pytest.mark.asyncio
async def test_admin_add_tool_runtime_error():
    tool = AdminAddTool()
    result = await tool.execute(name="broken", description="x", code="return x  # undefined")
    assert "已成功注册" in result
    # The error only surfaces when the generated tool is actually called
    broken_tool = registry.get("broken")
    assert broken_tool is not None
    output = await broken_tool.execute()
    assert "出错" in output


@pytest.mark.asyncio
async def test_admin_tool_can_use_common_builtins():
    tool = AdminAddTool()
    result = await tool.execute(
        name="sort_words",
        description="Sort words.",
        code='''words = kwargs.get("words", [])
if not all(isinstance(w, str) for w in words):
    return "bad"
return ",".join(sorted(words))
''',
    )
    assert "已成功注册" in result
    sort_tool = registry.get("sort_words")
    assert sort_tool is not None
    output = await sort_tool.execute(words=["b", "a", "c"])
    assert output == "a,b,c"
