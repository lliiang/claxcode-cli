"""Tests for web tools (HTTP mocked via pytest-httpx)."""

from claxcode.tools.web import FetchURL, WebSearch

DDG_HTML = """
<html><body>
<a rel="nofollow" class="result__a" href="https://example.com/1">First <b>Result</b></a>
<a rel="nofollow" class="result__a" href="https://example.com/2">Second Result</a>
</body></html>
"""


async def test_web_search_parses_results(httpx_mock):
    httpx_mock.add_response(text=DDG_HTML)
    tool = WebSearch()
    result = await tool.execute(query="test query")
    assert "First Result" in result
    assert "https://example.com/1" in result
    assert "Second Result" in result


async def test_web_search_sends_query_param(httpx_mock):
    httpx_mock.add_response(text="<html></html>")
    tool = WebSearch()
    await tool.execute(query="hello world")
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.params["q"] == "hello world"


async def test_web_search_http_error(httpx_mock):
    httpx_mock.add_response(status_code=403, text="forbidden")
    tool = WebSearch()
    result = await tool.execute(query="x")
    assert "错误" in result


async def test_fetch_url_content(httpx_mock):
    httpx_mock.add_response(url="https://example.com/page", text="page content")
    tool = FetchURL()
    result = await tool.execute(url="https://example.com/page")
    assert result == "page content"


async def test_fetch_url_truncates(httpx_mock):
    httpx_mock.add_response(url="https://example.com/big", text="x" * 200)
    tool = FetchURL()
    result = await tool.execute(url="https://example.com/big", max_length=100)
    assert "已截断" in result
    assert len(result) < 200
