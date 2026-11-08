"""Tests for rolling project memory."""

from claxcode.memory import init_db, project_memory


async def test_update_summary_creates_project_without_init(tmp_path):
    await init_db()
    project = str(tmp_path / "new-project")
    assert await project_memory.update_summary(project, "当前采用滚动项目摘要") is True

    saved = await project_memory.get_project(project)
    assert saved is not None
    assert saved["context_summary"] == "当前采用滚动项目摘要"


async def test_init_project_records_description_and_time(tmp_path):
    await init_db()
    project = str(tmp_path / "described-project")
    await project_memory.init_project(project, {"name": "demo", "description": "项目说明"})

    saved = await project_memory.get_project(project)
    assert saved is not None
    assert saved["config"]["description"] == "项目说明"
    assert saved["config"]["initialized_at"].startswith(saved["initialized_at"])
    projects = await project_memory.list_all_projects()
    assert any(
        p["project_path"] == saved["project_path"] and p["description"] == "项目说明"
        for p in projects
    )
