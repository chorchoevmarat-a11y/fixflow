import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_membership
from app.database import get_db
from app.models.models import NoteVisibility, OrganizationMembership, ServiceRequest, WorkNote

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteCreate(BaseModel):
    service_request_id: uuid.UUID
    content: str
    visibility: NoteVisibility = NoteVisibility.INTERNAL
    client_command_id: str | None = None  # Idempotency key


@router.get("")
async def list_notes(
    service_request_id: uuid.UUID,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    sr = await db.get(ServiceRequest, service_request_id)
    if not sr or sr.org_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Service request not found")

    query = select(WorkNote).where(WorkNote.service_request_id == service_request_id).order_by(WorkNote.created_at.asc())
    res = await db.execute(query)
    notes = res.scalars().all()

    return [
        {
            "id": str(n.id),
            "service_request_id": str(n.service_request_id),
            "author_id": str(n.author_id) if n.author_id else None,
            "content": n.content,
            "visibility": n.visibility.value,
            "is_system": n.is_system,
            "created_at": n.created_at.isoformat(),
        }
        for n in notes
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreate,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    if payload.client_command_id:
        existing = await db.execute(select(WorkNote).where(WorkNote.client_command_id == payload.client_command_id))
        found = existing.scalar_one_or_none()
        if found:
            return {
                "id": str(found.id),
                "content": found.content,
                "status": "already_processed",
            }

    sr = await db.get(ServiceRequest, payload.service_request_id)
    if not sr or sr.org_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Service request not found")

    note = WorkNote(
        service_request_id=payload.service_request_id,
        author_id=membership.user_id,
        content=payload.content,
        visibility=payload.visibility,
        client_command_id=payload.client_command_id,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return {
        "id": str(note.id),
        "content": note.content,
        "created_at": note.created_at.isoformat(),
    }
