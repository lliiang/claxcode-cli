"""Session API tests."""

import pytest


@pytest.mark.asyncio
async def test_create_and_get_session(client):
    resp = await client.post("/sessions", json={"name": "Test", "project_path": ".", "permission_mode": "ask"})
    assert resp.status_code == 200
    data = resp.json()
    session_id = data["id"]

    get_resp = await client.get(f"/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Test"


@pytest.mark.asyncio
async def test_list_sessions(client):
    resp = await client.get("/sessions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
