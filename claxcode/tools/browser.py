"""Playwright browser automation tools.

Requires: pip install playwright && playwright install chromium
"""

from __future__ import annotations

import base64
from typing import Any

from claxcode.tools.base import Tool
from claxcode.tools.registry import tool

# Lazy import — fail at runtime only if not installed
try:
    from playwright.async_api import Browser, Page, async_playwright
except ImportError:
    async_playwright = None  # type: ignore[assignment]


# ── Shared browser instance (singleton per process) ──────────────────────

_browser: Browser | None = None


async def _get_browser(headless: bool = True, proxy: str | None = None) -> Browser:
    """Get or launch the shared Playwright browser instance."""
    global _browser
    if _browser is not None and _browser.is_connected():
        return _browser

    if async_playwright is None:
        raise RuntimeError(
            "Playwright 未安装。请运行: pip install playwright && playwright install chromium"
        )

    p = await async_playwright().start()
    launch_kwargs: dict[str, Any] = {"headless": headless}
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}
    _browser = await p.chromium.launch(**launch_kwargs)
    return _browser


# ── Helper: ensure page context ──────────────────────────────────────────

_page_context: dict[str, Any] = {}


async def _ensure_page(browser: Browser | None = None) -> Page:
    """Return an existing page or create a new one."""
    if browser is None:
        browser = await _get_browser()

    # 检查是否有已存在的页面且未关闭
    if "page" in _page_context:
        page = _page_context["page"]
        if page and not page.is_closed():
            return page

    # 获取浏览器上下文中的页面
    pages = browser.contexts[0].pages if browser.contexts else []
    if pages:
        # 使用最后一个活动的页面
        for p in reversed(pages):
            if not p.is_closed():
                _page_context["page"] = p
                return p

    # 创建新页面
    ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
    _page_context["page"] = await ctx.new_page()
    return _page_context["page"]


# ── Tools ────────────────────────────────────────────────────────────────


@tool
class BrowserNavigate(Tool):
    """导航到指定 URL。"""

    name = "browser_navigate"
    description = "在浏览器中打开 URL。"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to navigate to"},
            "headless": {"type": "boolean", "default": True, "description": "Run browser in headless mode"},
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
        self,
        url: str,
        headless: bool = True,
        wait_until: str = "load",
        **kwargs: Any,
    ) -> str:
        browser = await _get_browser(headless=headless)
        page = await _ensure_page(browser)
        try:
            await page.goto(url, wait_until=wait_until)
            return (
                f"✅ 已导航到 {url}\n"
                f"   标题: {await page.title()}\n"
                f"   URL: {page.url}"
            )
        except Exception as exc:
            return f"❌ 导航失败: {exc}"


@tool
class BrowserClick(Tool):
    """点击页面上的元素。"""

    name = "browser_click"
    description = "点击由 CSS 选择器标识的元素。"
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
        page = await _ensure_page()
        try:
            await page.click(selector, timeout=timeout)
            return f"🖱️ 已点击元素 '{selector}'"
        except Exception as exc:
            return f"❌ 点击失败: {exc}"


@tool
class BrowserType(Tool):
    """在输入框中输入文本。"""

    name = "browser_type"
    description = "在输入字段中输入文本。"
    input_schema = {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector of the input element"},
            "text": {"type": "string", "description": "Text to type"},
            "delay": {"type": "integer", "default": 0, "description": "Delay between keystrokes in ms"},
            "clear_first": {"type": "boolean", "default": True, "description": "Clear the field before typing"},
        },
        "required": ["selector", "text"],
    }
    category = "browser"
    required_permissions = ["web"]

    async def execute(
        self,
        selector: str,
        text: str,
        delay: int = 0,
        clear_first: bool = True,
        **kwargs: Any,
    ) -> str:
        page = await _ensure_page()
        try:
            if clear_first:
                await page.fill(selector, "")
            await page.type(selector, text, delay=delay)
            return f"⌨️ 已在 '{selector}' 中输入 '{text}'"
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
            "full_page": {"type": "boolean", "default": False, "description": "Capture full-page screenshot"},
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
        self,
        path: str = "",
        full_page: bool = False,
        return_base64: bool = False,
        **kwargs: Any,
    ) -> str:
        page = await _ensure_page()
        try:
            if return_base64:
                screenshot_bytes = await page.screenshot(full_page=full_page, type="png")
                b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                return f"📸 截图 (base64, {len(screenshot_bytes)} 字节):\n{b64}"
            if not path:
                path = f"screenshot_{int(__import__('time').time())}.png"
            await page.screenshot(path=path, full_page=full_page)
            return f"📸 截图已保存: {path}"
        except Exception as exc:
            return f"❌ 截图失败: {exc}"


@tool
class BrowserGetContent(Tool):
    """获取页面或特定元素的文本内容。"""

    name = "browser_get_content"
    description = "获取页面或 CSS 选择元素的可见文本内容。"
    input_schema = {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector (empty = entire page body text)",
                "default": "",
            },
            "max_length": {"type": "integer", "default": 5000, "description": "Max characters to return"},
        },
        "required": [],
    }
    category = "browser"
    required_permissions = ["web"]

    async def execute(self, selector: str = "", max_length: int = 5000, **kwargs: Any) -> str:
        page = await _ensure_page()
        try:
            if selector:
                el = await page.query_selector(selector)
                if el is None:
                    return f"❌ 未找到元素 '{selector}'"
                text = await el.inner_text()
            else:
                text = await page.content()
                # Strip HTML tags for readability
                import re

                text = re.sub(r"<[^>]+>", "", text)
                text = re.sub(r"\s+", " ", text).strip()
            if len(text) > max_length:
                text = text[:max_length] + "\n... [已截断]"
            return text
        except Exception as exc:
            return f"❌ 获取内容失败: {exc}"


@tool
class BrowserEvaluate(Tool):
    """在浏览器页面中执行 JavaScript。"""

    name = "browser_evaluate"
    description = "在浏览器页面中运行 JavaScript 代码并返回结果。"
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
        page = await _ensure_page()
        try:
            result = await page.evaluate(script)
            return f"📜 JS 执行结果:\n{result}"
        except Exception as exc:
            return f"❌ JS 执行失败: {exc}"


@tool
class BrowserWait(Tool):
    """等待页面上的某个条件。"""

    name = "browser_wait"
    description = "等待一段时间、等待选择器出现或等待页面加载。"
    input_schema = {
        "type": "object",
        "properties": {
            "timeout": {
                    "type": "integer",
                    "default": 2000,
                    "description": "Time to wait in ms (used when no selector given)",
                },
        },
        "required": [],
    }
    category = "browser"
    required_permissions = ["web"]

    async def execute(self, timeout: int = 2000, **kwargs: Any) -> str:
        page = await _ensure_page()
        try:
            await page.wait_for_timeout(timeout)
            return f"⏳ 已等待 {timeout}毫秒"
        except Exception as exc:
            return f"❌ 等待失败: {exc}"


@tool
class BrowserClose(Tool):
    """关闭当前页面或整个浏览器。"""

    name = "browser_close"
    description = "关闭当前页面 ('page') 或整个浏览器 ('all')。"
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
        global _browser
        try:
            if target == "all":
                if _browser:
                    await _browser.close()
                    _browser = None
                _page_context.pop("page", None)
                return "🛑 浏览器已关闭"
            # Close current page
            page = _page_context.pop("page", None)
            if page and not page.is_closed():
                await page.close()
            return "📄 页面已关闭"
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
        if _browser is None or not _browser.is_connected():
            return "ℹ️ 浏览器未打开"
        pages = []
        for ctx in _browser.contexts:
            for pg in ctx.pages:
                pages.append(f"  • {pg.url}  (标题: {await pg.title()})")
        if not pages:
            return "ℹ️ 没有打开的页面"
        return "📑 打开的页面:\n" + "\n".join(pages)
