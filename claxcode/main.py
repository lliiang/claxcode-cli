"""FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from claxcode.config import settings
from claxcode.memory.session_store import init_db
from claxcode.api import session, chat, tools, subagents


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    await init_db()
    yield
    # Shutdown


app = FastAPI(
    title=settings.app_name,
    description="Agentic coding assistant API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(session.router, prefix="/sessions", tags=["sessions"])
app.include_router(chat.router, prefix="/sessions", tags=["chat"])
app.include_router(tools.router, prefix="/tools", tags=["tools"])
app.include_router(subagents.router, prefix="/subagents", tags=["subagents"])


@app.get("/health", response_class=PlainTextResponse)
async def health():
    return "ok"


def run() -> None:
    """CLI entry point to start the server."""
    import uvicorn

    uvicorn.run(
        "claxcode.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    run()
