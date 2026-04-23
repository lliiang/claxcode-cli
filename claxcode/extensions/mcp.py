"""MCP (Model Context Protocol) connector (stub for Phase 5)."""

from typing import Any


class MCPClient:
    """Client for connecting to MCP servers."""

    def __init__(self, server_url: str):
        self.server_url = server_url

    async def list_tools(self) -> list[dict[str, Any]]:
        return []
