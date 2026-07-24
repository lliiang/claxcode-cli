"""Integration tests for the persistent browser session (actor pattern).

Runs against real chromium when available; skips otherwise.
Uses only local data: URLs — no network access needed.
"""

import asyncio

import pytest

import claxcode.tools.browser as bmod
from claxcode.tools.browser import BrowserSession

pytestmark = pytest.mark.skipif(bmod.async_playwright is None, reason="playwright 未安装")

PAGE_A = "data:text/html,<title>PageA</title><input id='q'><button id='b'>go</button>"


@pytest.fixture
async def session():
    s = BrowserSession()
    try:
        await s.run_command("navigate", url=PAGE_A, headless=True)
    except Exception as exc:
        pytest.skip(f"chromium 不可用: {exc}")
    yield s
    await s.run_command("shutdown")


async def test_continuous_operations_same_page(session):
    """navigate -> type -> evaluate 共享同一页面状态。"""
    await session.run_command("type", selector="#q", text="连续操作")
    result = await session.run_command(
        "evaluate", script="document.querySelector('#q').value"
    )
    assert "连续操作" in result


async def test_commands_from_different_tasks_share_session(session):
    """另一个 asyncio task 发出的命令操作的是同一个页面（actor 跨 task 连续）。"""
    await session.run_command("type", selector="#q", text="跨任务")

    async def read_value():
        return await session.run_command(
            "evaluate", script="document.querySelector('#q').value"
        )

    result = await asyncio.create_task(read_value())
    assert "跨任务" in result


async def test_close_page_then_navigate_recreates(session):
    """关闭页面后会话仍可继续：自动重建页面。"""
    await session.run_command("close_page")
    result = await session.run_command("navigate", url=PAGE_A)
    assert "PageA" in result


async def test_shutdown_then_relaunch(session):
    """整体关闭后再次使用会自动重启浏览器。"""
    result = await session.run_command("shutdown")
    assert "已关闭" in result
    result = await session.run_command("list_pages")
    assert "未打开" in result or "没有打开" in result
    result = await session.run_command("navigate", url=PAGE_A)
    assert "PageA" in result


async def test_tool_wrapper_returns_error_string():
    """工具层把异常转换为错误字符串（不抛出）。"""
    tool = bmod.BrowserClick()
    session = BrowserSession()
    try:
        await session.run_command("navigate", url=PAGE_A, headless=True)
    except Exception as exc:
        pytest.skip(f"chromium 不可用: {exc}")
    bmod._session = session  # 替换模块级会话
    try:
        result = await tool.execute(selector="#nonexistent", timeout=300)
        assert result.startswith("❌")
    finally:
        await session.run_command("shutdown")


def test_session_headless_default_from_settings(monkeypatch):
    """BROWSER_HEADLESS 配置决定新会话的默认模式。"""
    monkeypatch.setattr(bmod.settings, "browser_headless", False)
    assert BrowserSession()._headless is False
    monkeypatch.setattr(bmod.settings, "browser_headless", True)
    assert BrowserSession()._headless is True


async def test_navigate_default_headless_reads_config(monkeypatch):
    """不传 headless 时透传 None（由会话按配置决定）。"""
    captured: dict = {}

    class FakeSession:
        async def run_command(self, action, **params):
            captured["action"] = action
            captured.update(params)
            return "ok"

    monkeypatch.setattr(bmod, "_session", FakeSession())
    result = await bmod.BrowserNavigate().execute(url="https://example.com")
    assert result == "ok"
    assert captured["headless"] is None


async def test_navigate_explicit_headless_passthrough(monkeypatch):
    """显式传 headless 时按原值透传。"""
    captured: dict = {}

    class FakeSession:
        async def run_command(self, action, **params):
            captured.update(params)
            return "ok"

    monkeypatch.setattr(bmod, "_session", FakeSession())
    await bmod.BrowserNavigate().execute(url="https://example.com", headless=False)
    assert captured["headless"] is False
