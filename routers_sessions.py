from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

import models
from database import get_async_db
from schemas import MessageOut, SessionCreate, SessionOut, SessionRename
from utils import get_user_identifier

router = APIRouter(prefix="/sessions", tags=["sessions"])


async def require_user_id(user_id=Depends(get_user_identifier)) -> int:
    # Multi-session history is only meaningful for a real account — a
    # guest identity has no account to own sessions with.
    if not isinstance(user_id, int):
        raise HTTPException(status_code=401, detail="Log in to use chat sessions.")
    return user_id


async def get_owned_session(db: AsyncSession, user_id: int, session_id: int) -> models.ChatSessions:
    session = (
        await db.execute(
            select(models.ChatSessions).where(
                models.ChatSessions.id == session_id,
                models.ChatSessions.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreate,
    user_id: int = Depends(require_user_id),
    db: AsyncSession = Depends(get_async_db),
):
    session = models.ChatSessions(user_id=user_id, title=payload.title or "New chat")
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    user_id: int = Depends(require_user_id),
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(models.ChatSessions)
        .where(models.ChatSessions.user_id == user_id)
        .order_by(models.ChatSessions.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def get_session_messages(
    session_id: int,
    user_id: int = Depends(require_user_id),
    db: AsyncSession = Depends(get_async_db),
):
    await get_owned_session(db, user_id, session_id)

    result = await db.execute(
        select(models.Prompts)
        .where(models.Prompts.session_id == session_id)
        .order_by(models.Prompts.created_at.asc())
    )
    messages = []
    for row in result.scalars().all():
        messages.append(MessageOut(role="user", content=row.userprompt))
        messages.append(MessageOut(role="assistant", content=row.response))
    return messages


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    user_id: int = Depends(require_user_id),
    db: AsyncSession = Depends(get_async_db),
):
    session = await get_owned_session(db, user_id, session_id)
    await db.execute(delete(models.Prompts).where(models.Prompts.session_id == session_id))
    await db.delete(session)
    await db.commit()


@router.patch("/{session_id}", response_model=SessionOut)
async def update_session_name(
    session_id: int,
    payload: SessionRename,
    user_id: int = Depends(require_user_id),
    db: AsyncSession = Depends(get_async_db),
):
    session = await get_owned_session(db, user_id, session_id)
    session.title = payload.new_session_name
    await db.commit()
    await db.refresh(session)
    return session
