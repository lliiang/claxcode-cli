"""Tests for rolling project memory."""

from claxcode.memory import init_db, project_memory


async def test_update_summary_creates_project_without_init(tmp_path):
    await init_db()
    project = str(tmp_path / "new-project")
    assert await project_memory.update_summary(project, "当前采用滚动项目摘要") is True

    saved = await project_memory.get_project(project)
    assert saved is not None
    assert saved["context_summary"] == "当前采用滚动项目摘要"
