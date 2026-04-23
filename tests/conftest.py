"""Pytest shared fixtures."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from claxcode.main import app
from claxcode.memory.session_store import init_db


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for FastAPI app testing."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
