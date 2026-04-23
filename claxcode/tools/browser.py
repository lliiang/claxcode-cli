"""Playwright browser automation tools.

Requires: pip install playwright && playwright install chromium
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from claxcode.tools.base import Tool
from claxcode.tools.registry import tool

# Lazy import — fail at runtime only if not installed
try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
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
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
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
    global _page_context
    if browser is None:
        browser = await _get_browser()
    pages = browser.contexts[0].pages if browser.contexts else []
    if pages:
        _page_context["page"] = pages[-1]
    if "page" not in _page_context or not _page_context["page"].is_closed():
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        _page_context["page"] = await ctx.new_page()
    return _page_context["page"]


# ── Tools ────────────────────────────────────────────────────────────────


@tool
class BrowserNavigate(Tool):
    """Navigate to a URL."""

    name = "browser_navigate"
    description = "Open a URL in the browser."
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
                f"✅ Navigated to {url}\n"
                f"   Title: {await page.title()}\n"
                f"   URL: {page.url}"
            )
        except Exception as exc:
            return f"❌ Navigation failed: {exc}"


@tool
class BrowserClick(Tool):
    """Click an element on the page."""

    name = "browser_click"
    description = "Click an element identified by a CSS selector."
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
            return f"🖱️ Clicked element '{selector}'"
        except Exception as exc:
            return f"❌ Click failed: {exc}"


@tool
class BrowserType(Tool):
    """Type text into an input field."""

    name = "browser_type"
    description = "Type text into an input field."
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
            return f"⌨️ Typed '{text}' into '{selector}'"
        except Exception as exc:
            return f"❌ Type failed: {exc}"


@tool
class BrowserScreenshot(Tool):
    """Take a screenshot of the current page."""

    name = "browser_screenshot"
    description = "Take a screenshot and save it to a file, or return base64 data."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to save the screenshot (e.g. screenshot.png)", "default": ""},
            "full_page": {"type": "boolean", "default": False, "description": "Capture full-page screenshot"},
            "return_base64": {"type": "boolean", "default": False, "description": "Return base64-encoded PNG data instead of saving"},
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
                return f"📸 Screenshot (base64, {len(screenshot_bytes)} bytes):\n{b64}"
            if not path:
                path = f"screenshot_{int(__import__('time').time())}.png"
            await page.screenshot(path=path, full_page=full_page)
            return f"📸 Screenshot saved: {path}"
        except Exception as exc:
            return f"❌ Screenshot failed: {exc}"


@tool
class BrowserGetContent(Tool):
    """Get text content of the page or a specific element."""

    name = "browser_get_content"
    description = "Get visible text content of the page or a CSS-selected element."
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
                    return f"❌ Element '{selector}' not found"
                text = await el.inner_text()
            else:
                text = await page.content()
                # Strip HTML tags for readability
                import re

                text = re.sub(r"<[^>]+>", "", text)
                text = re.sub(r"\s+", " ", text).strip()
            if len(text) > max_length:
                text = text[:max_length] + "\n... [truncated]"
            return text
        except Exception as exc:
            return f"❌ Failed to get content: {exc}"


@tool
class BrowserEvaluate(Tool):
    """Execute JavaScript in the browser page."""

    name = "browser_evaluate"
    description = "Run JavaScript code in the browser page and return the result."
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
            return f"📜 JS result:\n{result}"
        except Exception as exc:
            return f"❌ JS evaluation failed: {exc}"


@tool
class BrowserWait(Tool):
    """Wait for a condition on the page."""

    name = "browser_wait"
    description = "Wait for a time period, a selector to appear, or the page to load."
    input_schema = {
        "type": "object",
        "properties": {
            "timeout": {"type": "integer", "default": 2000, "description": "Time to wait in ms (used when no selector given)"},
        },
        "required": [],
    }
    category = "browser"
    required_permissions = ["web"]

    async def execute(self, timeout: int = 2000, **kwargs: Any) -> str:
        page = await _ensure_page()
        try:
            await page.wait_for_timeout(timeout)
            return f"⏳ Waited {timeout}ms"
        except Exception as exc:
            return f"❌ Wait failed: {exc}"


@tool
class BrowserClose(Tool):
    """Close the current page or the entire browser."""

    name = "browser_close"
    description = "Close the current page ('page') or the entire browser ('all')."
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
        global _browser, _page_context
        try:
            if target == "all":
                if _browser:
                    await _browser.close()
                    _browser = None
                _page_context.pop("page", None)
                return "🛑 Browser closed"
            # Close current page
            page = _page_context.pop("page", None)
            if page and not page.is_closed():
                await page.close()
            return "📄 Page closed"
        except Exception as exc:
            return f"❌ Close failed: {exc}"


@tool
class BrowserListPages(Tool):
    """List all open pages/tabs."""

    name = "browser_list_pages"
    description = "List all open pages/tabs in the browser."
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    category = "browser"
    required_permissions = ["web"]

    async def execute(self, **kwargs: Any) -> str:
        global _browser
        if _browser is None or not _browser.is_connected():
            return "ℹ️ No browser is open"
        pages = []
        for ctx in _browser.contexts:
            for pg in ctx.pages:
                pages.append(f"  • {pg.url}  (title: {await pg.title()})")
        if not pages:
            return "ℹ️ No open pages"
        return "📑 Open pages:\n" + "\n".join(pages)
