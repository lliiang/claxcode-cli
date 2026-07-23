"""Session management API."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from claxcode.memory.session_store import SessionORM, get_db_session
from claxcode.models.session import Session, SessionCreate

router = APIRouter()


def _orm_to_model(orm: SessionORM) -> Session:
    return Session(
        id=UUID(orm.id),
        name=orm.name,
        project_path=orm.project_path,
        permission_mode=orm.permission_mode,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


@router.post("", response_model=Session)
async def create_session(
    data: SessionCreate,
    db: AsyncSession = Depends(get_db_session),
):
    session_orm = SessionORM(
        id=str(uuid4()),
        name=data.name,
        project_path=data.project_path,
        permission_mode=data.permission_mode,
    )
    db.add(session_orm)
    await db.commit()
    await db.refresh(session_orm)
    return _orm_to_model(session_orm)


@router.get("", response_model=list[Session])
async def list_sessions(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(SessionORM).order_by(SessionORM.created_at.desc()))
    return [_orm_to_model(row) for row in result.scalars().all()]


@router.get("/{session_id}", response_model=Session)
async def get_session(session_id: UUID, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(SessionORM).where(SessionORM.id == str(session_id)))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return _orm_to_model(row)


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: UUID, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(SessionORM).where(SessionORM.id == str(session_id)))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    await db.delete(row)
    await db.commit()
    return None
