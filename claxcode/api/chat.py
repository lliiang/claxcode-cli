"""Chat and streaming API."""

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from claxcode.core.agent import Agent
from claxcode.memory.session_store import get_db_session, SessionORM
from claxcode.models.session import ChatRequest

router = APIRouter()


@router.post("/{session_id}/chat")
async def chat(
    session_id: UUID,
    request: ChatRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Stream chat events via SSE."""
    result = await db.execute(select(SessionORM).where(SessionORM.id == str(session_id)))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    agent = Agent(
        session_id=session_id,
        project_path=row.project_path,
        permission_mode=row.permission_mode,
    )

    async def event_stream():
        async for event in agent.run(request.message):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )
