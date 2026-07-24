"""Web tools."""

import re
from typing import Any

import httpx

from claxcode.tools.base import Tool
from claxcode.tools.registry import tool

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ClaxCode/0.1"


@tool
class FetchURL(Tool):
    name = "fetch_url"
    description = "获取 URL 的文本内容。"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_length": {"type": "integer", "default": 10000},
        },
        "required": ["url"],
    }
    category = "web"
    required_permissions = ["web"]

    async def execute(self, url: str, max_length: int = 10000, **kwargs: Any) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=30, headers={"User-Agent": USER_AGENT}
            ) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                text = resp.text
                if len(text) > max_length:
                    text = text[:max_length] + "\n... [已截断]"
                return text
        except httpx.HTTPStatusError as exc:
            return f"HTTP 错误 {exc.response.status_code}: {url}"
        except Exception as exc:
            return f"获取 {url} 时出错: {exc}"


@tool
class WebSearch(Tool):
    name = "web_search"
    description = "使用 DuckDuckGo 搜索网页（HTML 抓取）。"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }
    category = "web"
    required_permissions = ["web"]

    async def execute(self, query: str, max_results: int = 5, **kwargs: Any) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=30, headers={"User-Agent": USER_AGENT}
            ) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/", params={"q": query}
                )
                resp.raise_for_status()
                results = []
                for href, title in re.findall(
                    r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>',
                    resp.text,
                ):
                    title = re.sub(r"<.*?>", "", title)
                    results.append(f"{title}\n{href}")
                    if len(results) >= max_results:
                        break
                if not results:
                    return "未找到搜索结果。"
                return "\n\n".join(results)
        except Exception as exc:
            return f"搜索错误: {exc}"
