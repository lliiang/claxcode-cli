"""Tests for tools API."""

import pytest


@pytest.mark.asyncio
async def test_list_tools(client):
    resp = await client.get("/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    names = {t["name"] for t in data}
    assert "read_file" in names
    assert "write_file" in names


@pytest.mark.asyncio
async def test_invoke_read_file(client, tmp_path):
    f = tmp_path / "api_test.txt"
    f.write_text("api content", encoding="utf-8")
    resp = await client.post(
        "/tools/invoke",
        json={"name": "read_file", "arguments": {"path": str(f)}},
    )
    assert resp.status_code == 200
    assert resp.json()["output"] == "api content"
