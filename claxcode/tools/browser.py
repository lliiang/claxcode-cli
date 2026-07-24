"""Playwright browser automation tools with a persistent session.

Requires: pip install playwright && playwright install chromium

Architecture: all Playwright objects live in a single dedicated asyncio
task (actor pattern). Tool calls from any task — the CLI loop, API SSE
handlers, subagents — only post commands to a queue and await results.
Playwright's async objects are bound to the task that created them, so
this actor is what makes the browser session continuous across tool
calls, across request tasks, and across conversation turns.
"""

from __future__ import annotations

import asyncio
import base64
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal

from claxcode.config import settings
from claxcode.tools.base import Tool, attach_image
from claxcode.tools.registry import tool

# Lazy import — fail at runtime only if not installed
try:
    from playwright.async_api import Browser, BrowserContext, Page, async_playwright
except ImportError:
    async_playwright = None  # type: ignore[assignment]

WaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]


class BrowserSession:
    """A persistent browser session owned by a single actor task."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[
            tuple[str, dict[str, Any], asyncio.Future[Any]]
        ] = asyncio.Queue()
        self._task: asyncio.Task[Any] | None = None
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._headless = settings.browser_headless
        self._proxy: str | None = None

    async def run_command(self, action: str, **params: Any) -> str:
        """Post a command to the actor task and await its result."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._actor_loop())
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        await self._queue.put((action, params, future))
        result: str = await future
        return result

    # ── actor ────────────────────────────────────────────────────────

    async def _actor_loop(self) -> None:
        try:
            while True:
                action, params, future = await self._queue.get()
                if action == "shutdown":
                    await self._teardown()
                    if not future.done():
                        future.set_result("🛑 浏览器已关闭")
                    return
                try:
                    result = await self._dispatch(action, params)
                except Exception as exc:
                    if not future.done():
                        future.set_exception(exc)
                else:
                    if not future.done():
                        future.set_result(result)
        finally:
            with suppress(Exception):
                await self._teardown()

    async def _dispatch(self, action: str, params: dict[str, Any]) -> Any:
        handler = getattr(self, f"_do_{action}", None)
        if handler is None:
            raise ValueError(f"未知的浏览器操作: {action}")
        return await handler(**params)

    # ── lifecycle (actor task only) ──────────────────────────────────

    async def _ensure_browser(self, headless: bool | None = None, proxy: str | None = None) -> None:
        if headless is not None and self._browser is not None and headless != self._headless:
            await self._teardown()  # 切换有头/无头需要重启浏览器
        if headless is not None:
            self._headless = headless
        if proxy is not None:
            self._proxy = proxy
        if self._browser is not None and self._browser.is_connected():
            return
        if async_playwright is None:
            raise RuntimeError(
                "Playwright 未安装。请运行: pip install playwright && playwright install chromium"
            )
        self._playwright = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {"headless": self._headless}
        if self._proxy:
            launch_kwargs["proxy"] = {"server": self._proxy}
        try:
            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        except Exception as exc:
            if not self._headless or "Executable doesn't exist" not in str(exc):
                raise
            # headless shell 缺失时回退到完整版 chromium
            self._browser = await self._playwright.chromium.launch(
                channel="chromium", **launch_kwargs
            )
        self._context = None
        self._page = None

    async def _ensure_page(self) -> Page:
        await self._ensure_browser()
        if self._page is not None and not self._page.is_closed():
            return self._page
        if self._context is None:
            assert self._browser is not None
            self._context = await self._browser.new_context()
        for page in reversed(self._context.pages):
            if not page.is_closed():
                self._page = page
                return page
        self._page = await self._context.new_page()
        return self._page

    async def _teardown(self) -> None:
        with suppress(Exception):
            if self._context is not None:
                await self._context.close()
        with suppress(Exception):
            if self._browser is not None and self._browser.is_connected():
                await self._browser.close()
        with suppress(Exception):
            if self._playwright is not None:
                await self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    # ── commands (actor task only) ───────────────────────────────────

    async def _do_navigate(
        self, url: str, headless: bool | None = None, wait_until: WaitUntil = "load"
    ) -> str:
        await self._ensure_browser(headless=headless)
        page = await self._ensure_page()
        await page.goto(url, wait_until=wait_until)
        return f"✅ 已导航到 {url}\n   标题: {await page.title()}\n   URL: {page.url}"

    async def _do_click(self, selector: str, timeout: int = 5000) -> str:
        page = await self._ensure_page()
        await page.click(selector, timeout=timeout)
        return f"🖱️ 已点击元素 '{selector}'"

    async def _do_type(
        self, selector: str, text: str, delay: int = 0, clear_first: bool = True
    ) -> str:
        page = await self._ensure_page()
        if clear_first:
            await page.fill(selector, "")
        await page.type(selector, text, delay=delay)
        return f"⌨️ 已在 '{selector}' 中输入 '{text}'"

    async def _do_screenshot(
        self, path: str = "", full_page: bool = False, return_base64: bool = False
    ) -> str:
        page = await self._ensure_page()
        data = await page.screenshot(full_page=full_page, type="png")
        attach_image(data)  # 视觉模型可直接看到截图
        if return_base64:
            return f"📸 截图 (base64, {len(data)} 字节):\n{base64.b64encode(data).decode()}"
        if not path:
            path = f"screenshot_{int(time.time())}.png"
        Path(path).write_bytes(data)
        return f"📸 截图已保存: {path}"

    async def _do_get_content(self, selector: str = "", max_length: int = 5000) -> str:
        page = await self._ensure_page()
        if selector:
            el = await page.query_selector(selector)
            if el is None:
                return f"❌ 未找到元素 '{selector}'"
            text = await el.inner_text()
        else:
            import re

            text = re.sub(r"<[^>]+>", "", await page.content())
            text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_length:
            text = text[:max_length] + "\n... [已截断]"
        return text

    async def _do_evaluate(self, script: str) -> str:
        page = await self._ensure_page()
        result = await page.evaluate(script)
        return f"📜 JS 执行结果:\n{result}"

    async def _do_wait(self, timeout: int = 2000, selector: str = "") -> str:
        page = await self._ensure_page()
        if selector:
            await page.wait_for_selector(selector, timeout=timeout)
            return f"⏳ 元素 '{selector}' 已就绪"
        await page.wait_for_timeout(timeout)
        return f"⏳ 已等待 {timeout}毫秒"

    async def _do_list_pages(self) -> str:
        if self._browser is None or not self._browser.is_connected():
            return "ℹ️ 浏览器未打开"
        pages = []
        for ctx in self._browser.contexts:
            for pg in ctx.pages:
                pages.append(f"  • {pg.url}  (标题: {await pg.title()})")
        if not pages:
            return "ℹ️ 没有打开的页面"
        return "📑 打开的页面:\n" + "\n".join(pages)

    async def _do_close_page(self) -> str:
        if self._page is not None and not self._page.is_closed():
            await self._page.close()
        self._page = None
        return "📄 页面已关闭"


# 进程级共享会话：所有浏览器工具共用，跨调用与跨对话保持连续
_session = BrowserSession()


# ── Tools（薄封装：投递命令到 actor，异常转为错误字符串） ────────────────


@tool
class BrowserNavigate(Tool):
    """导航到指定 URL。"""

    name = "browser_navigate"
    description = "在浏览器中打开 URL。浏览器会话跨多次调用保持，可连续操作同一页面。"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to navigate to"},
            "headless": {
                "type": "boolean",
                "description": "有头/无头；不传则读取 BROWSER_HEADLESS 配置（默认 true）",
            },
            "wait_until": {
                "type": "string",
                "default": "load",
                "enum": ["load", "domcontentloaded", "networkidle", "commit"],
                "description": "When to consider navigation succeeded",
            },
        },
        "required": ["url"],
    }
    category = "browser"
    required_permissions = ["web"]

    async def execute(
        self, url: str, headless: bool | None = None, wait_until: WaitUntil = "load", **kwargs: Any
    ) -> str:
        try:
            return await _session.run_command(
                "navigate", url=url, headless=headless, wait_until=wait_until
            )
        except Exception as exc:
            return f"❌ 导航失败: {exc}"


@tool
class BrowserClick(Tool):
    """点击页面上的元素。"""

    name = "browser_click"
    description = "点击由 CSS 选择器标识的元素（作用于当前页面）。"
    input_schema = {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector of the element to click"},
            "timeout": {"type": "integer", "default": 5000, "description": "Wait timeout in ms"},
        },
        "required": ["selector"],
    }
    category = "browser"
    required_permissions = ["web"]

    async def execute(self, selector: str, timeout: int = 5000, **kwargs: Any) -> str:
        try:
            return await _session.run_command("click", selector=selector, timeout=timeout)
        except Exception as exc:
            return f"❌ 点击失败: {exc}"


@tool
class BrowserType(Tool):
    """在输入框中输入文本。"""

    name = "browser_type"
    description = "在输入字段中输入文本（作用于当前页面）。"
    input_schema = {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector of the input element"},
            "text": {"type": "string", "description": "Text to type"},
            "delay": {"type": "integer", "default": 0, "description": "Keystroke delay in ms"},
            "clear_first": {"type": "boolean", "default": True, "description": "Clear first"},
        },
        "required": ["selector", "text"],
    }
    category = "browser"
    required_permissions = ["web"]

    async def execute(
        self, selector: str, text: str, delay: int = 0, clear_first: bool = True, **kwargs: Any
    ) -> str:
        try:
            return await _session.run_command(
                "type", selector=selector, text=text, delay=delay, clear_first=clear_first
            )
        except Exception as exc:
            return f"❌ 输入失败: {exc}"


@tool
class BrowserScreenshot(Tool):
    """截取当前页面的屏幕截图。"""

    name = "browser_screenshot"
    description = "截取屏幕截图并保存到文件，或返回 base64 数据。"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to save the screenshot (e.g. screenshot.png)",
                "default": "",
            },
            "full_page": {"type": "boolean", "default": False, "description": "Full-page capture"},
            "return_base64": {
                "type": "boolean",
                "default": False,
                "description": "Return base64-encoded PNG data instead of saving",
            },
        },
        "required": [],
    }
    category = "browser"
    required_permissions = ["web", "write"]

    async def execute(
        self, path: str = "", full_page: bool = False, return_base64: bool = False, **kwargs: Any
    ) -> str:
        try:
            return await _session.run_command(
                "screenshot", path=path, full_page=full_page, return_base64=return_base64
            )
        except Exception as exc:
            return f"❌ 截图失败: {exc}"


@tool
class BrowserGetContent(Tool):
    """获取页面或特定元素的文本内容。"""

    name = "browser_get_content"
    description = "获取页面或 CSS 选择元素的可见文本内容（作用于当前页面）。"
    input_schema = {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector (empty = entire page body text)",
                "default": "",
            },
            "max_length": {"type": "integer", "default": 5000, "description": "Max chars"},
        },
        "required": [],
    }
    category = "browser"
    required_permissions = ["web"]

    async def execute(self, selector: str = "", max_length: int = 5000, **kwargs: Any) -> str:
        try:
            return await _session.run_command(
                "get_content", selector=selector, max_length=max_length
            )
        except Exception as exc:
            return f"❌ 获取内容失败: {exc}"


@tool
class BrowserEvaluate(Tool):
    """在浏览器页面中执行 JavaScript。"""

    name = "browser_evaluate"
    description = "在浏览器当前页面中运行 JavaScript 代码并返回结果。"
    input_schema = {
        "type": "object",
        "properties": {
            "script": {"type": "string", "description": "JavaScript code to execute"},
        },
        "required": ["script"],
    }
    category = "browser"
    required_permissions = ["web"]

    async def execute(self, script: str, **kwargs: Any) -> str:
        try:
            return await _session.run_command("evaluate", script=script)
        except Exception as exc:
            return f"❌ JS 执行失败: {exc}"


@tool
class BrowserWait(Tool):
    """等待页面上的某个条件。"""

    name = "browser_wait"
    description = "等待一段时间，或等待某个 CSS 选择器出现在当前页面上。"
    input_schema = {
        "type": "object",
        "properties": {
            "timeout": {
                "type": "integer",
                "default": 2000,
                "description": "Timeout in ms",
            },
            "selector": {
                "type": "string",
                "default": "",
                "description": "CSS selector to wait for (empty = just sleep)",
            },
        },
        "required": [],
    }
    category = "browser"
    required_permissions = ["web"]

    async def execute(self, timeout: int = 2000, selector: str = "", **kwargs: Any) -> str:
        try:
            return await _session.run_command("wait", timeout=timeout, selector=selector)
        except Exception as exc:
            return f"❌ 等待失败: {exc}"


@tool
class BrowserClose(Tool):
    """关闭当前页面或整个浏览器。"""

    name = "browser_close"
    description = "关闭当前页面 ('page') 或整个浏览器会话 ('all')。"
    input_schema = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "enum": ["page", "all"],
                "default": "page",
                "description": "'page' = close current tab, 'all' = close the whole browser",
            },
        },
        "required": [],
    }
    category = "browser"
    required_permissions = ["web"]

    async def execute(self, target: str = "page", **kwargs: Any) -> str:
        try:
            if target == "all":
                return await _session.run_command("shutdown")
            return await _session.run_command("close_page")
        except Exception as exc:
            return f"❌ 关闭失败: {exc}"


@tool
class BrowserListPages(Tool):
    """列出所有打开的页面/标签。"""

    name = "browser_list_pages"
    description = "列出浏览器中所有打开的页面/标签。"
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    category = "browser"
    required_permissions = ["web"]

    async def execute(self, **kwargs: Any) -> str:
        try:
            return await _session.run_command("list_pages")
        except Exception as exc:
            return f"❌ 获取页面列表失败: {exc}"
