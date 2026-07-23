"""Tests for file operation tools."""

import pytest

from claxcode.tools.file_operations import (
    CreateDirectory,
    EditFile,
    ReadFile,
    RenameFile,
    StrReplaceFile,
    ViewFile,
    WriteFile,
)


@pytest.mark.asyncio
async def test_read_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello", encoding="utf-8")
    tool = ReadFile()
    result = await tool.execute(path=str(f))
    assert result == "hello"


@pytest.mark.asyncio
async def test_write_file(tmp_path):
    f = tmp_path / "out.txt"
    tool = WriteFile()
    result = await tool.execute(path=str(f), content="world")
    assert "已写入" in result
    assert f.read_text(encoding="utf-8") == "world"


@pytest.mark.asyncio
async def test_str_replace_file(tmp_path):
    f = tmp_path / "replace.txt"
    f.write_text("foo bar baz", encoding="utf-8")
    tool = StrReplaceFile()
    result = await tool.execute(path=str(f), old="bar", new="qux")
    assert "替换" in result
    assert f.read_text(encoding="utf-8") == "foo qux baz"


@pytest.mark.asyncio
async def test_create_directory(tmp_path):
    d = tmp_path / "nested" / "dir"
    tool = CreateDirectory()
    await tool.execute(path=str(d))
    assert d.exists()


@pytest.mark.asyncio
async def test_rename_file(tmp_path):
    old = tmp_path / "a.txt"
    old.write_text("x")
    new = tmp_path / "b.txt"
    tool = RenameFile()
    await tool.execute(old_path=str(old), new_path=str(new))
    assert new.exists()
    assert not old.exists()


@pytest.mark.asyncio
async def test_view_file_basic(tmp_path):
    f = tmp_path / "view.txt"
    f.write_text("line1\nline2\nline3", encoding="utf-8")
    tool = ViewFile()
    result = await tool.execute(path=str(f))
    assert "1 | line1" in result
    assert "2 | line2" in result
    assert "3 | line3" in result


@pytest.mark.asyncio
async def test_view_file_range(tmp_path):
    f = tmp_path / "view.txt"
    f.write_text("a\nb\nc\nd\ne", encoding="utf-8")
    tool = ViewFile()
    result = await tool.execute(path=str(f), view_range=[2, 4])
    assert "2 | b" in result
    assert "3 | c" in result
    assert "4 | d" in result
    assert "1 | a" not in result
    assert "5 | e" not in result


@pytest.mark.asyncio
async def test_view_file_truncation(tmp_path):
    f = tmp_path / "view.txt"
    f.write_text("\n".join(f"line{i}" for i in range(1, 101)), encoding="utf-8")
    tool = ViewFile()
    result = await tool.execute(path=str(f), max_lines=10)
    assert "1 | line1" in result
    assert "10 | line10" in result
    assert "共 100 行" in result
    assert "11 | line11" not in result


@pytest.mark.asyncio
async def test_edit_file_single_block(tmp_path):
    f = tmp_path / "edit.txt"
    f.write_text("def foo():\n    pass\n", encoding="utf-8")
    tool = EditFile()
    result = await tool.execute(
        path=str(f),
        edits=[{"old_string": "    pass", "new_string": "    return 42"}],
    )
    assert "已编辑" in result
    assert f.read_text(encoding="utf-8") == "def foo():\n    return 42\n"


@pytest.mark.asyncio
async def test_edit_file_multiple_blocks(tmp_path):
    f = tmp_path / "edit.txt"
    f.write_text("a\nb\nc\n", encoding="utf-8")
    tool = EditFile()
    result = await tool.execute(
        path=str(f),
        edits=[
            {"old_string": "a", "new_string": "A"},
            {"old_string": "c", "new_string": "C"},
        ],
    )
    assert "已编辑" in result
    assert f.read_text(encoding="utf-8") == "A\nb\nC\n"


@pytest.mark.asyncio
async def test_edit_file_not_found(tmp_path):
    f = tmp_path / "edit.txt"
    f.write_text("hello world\n", encoding="utf-8")
    tool = EditFile()
    result = await tool.execute(
        path=str(f),
        edits=[{"old_string": "nonexistent", "new_string": "x"}],
    )
    assert "未找到" in result
    assert "hello world" in result


@pytest.mark.asyncio
async def test_edit_file_ambiguous(tmp_path):
    f = tmp_path / "edit.txt"
    f.write_text("a\na\na\n", encoding="utf-8")
    tool = EditFile()
    result = await tool.execute(
        path=str(f),
        edits=[{"old_string": "a", "new_string": "b"}],
    )
    assert "3 处" in result
    assert "1-1" in result
