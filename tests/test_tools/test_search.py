"""Tests for search tools."""

import pytest

from claxcode.tools.search import GlobSearch, GrepSearch, ExploreCodebase


@pytest.mark.asyncio
async def test_glob_search(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.txt").write_text("x")
    tool = GlobSearch()
    result = await tool.execute(pattern="*.py", directory=str(tmp_path))
    assert "a.py" in result
    assert "b.txt" not in result


@pytest.mark.asyncio
async def test_grep_search(tmp_path):
    (tmp_path / "a.py").write_text("hello world")
    tool = GrepSearch()
    result = await tool.execute(pattern="hello", directory=str(tmp_path))
    assert "a.py" in result


@pytest.mark.asyncio
async def test_explore_codebase(tmp_path):
    (tmp_path / "file.txt").write_text("x")
    tool = ExploreCodebase()
    result = await tool.execute(directory=str(tmp_path), depth=1)
    assert "file.txt" in result
