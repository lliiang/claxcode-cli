"""Tests for file operation tools."""

import pytest

from claxcode.tools.file_operations import ReadFile, WriteFile, StrReplaceFile, CreateDirectory, RenameFile


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
    assert "written" in result
    assert f.read_text(encoding="utf-8") == "world"


@pytest.mark.asyncio
async def test_str_replace_file(tmp_path):
    f = tmp_path / "replace.txt"
    f.write_text("foo bar baz", encoding="utf-8")
    tool = StrReplaceFile()
    result = await tool.execute(path=str(f), old="bar", new="qux")
    assert "Replaced" in result
    assert f.read_text(encoding="utf-8") == "foo qux baz"


@pytest.mark.asyncio
async def test_create_directory(tmp_path):
    d = tmp_path / "nested" / "dir"
    tool = CreateDirectory()
    result = await tool.execute(path=str(d))
    assert d.exists()


@pytest.mark.asyncio
async def test_rename_file(tmp_path):
    old = tmp_path / "a.txt"
    old.write_text("x")
    new = tmp_path / "b.txt"
    tool = RenameFile()
    result = await tool.execute(old_path=str(old), new_path=str(new))
    assert new.exists()
    assert not old.exists()
