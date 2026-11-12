import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_membership
from app.database import get_db
from app.models.models import AuditEvent, OrganizationMembership

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def list_audit_events(
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service_request_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list[dict]:
    query = select(AuditEvent).where(AuditEvent.org_id == membership.organization_id)
    if service_request_id:
        query = query.where(AuditEvent.service_request_id == service_request_id)

    query = query.order_by(AuditEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    res = await db.execute(query)
    events = res.scalars().all()

    return [
        {
            "id": str(e.id),
            "action": e.action.value,
            "entity_type": e.entity_type,
            "entity_id": str(e.entity_id) if e.entity_id else None,
            "actor_id": str(e.actor_id) if e.actor_id else None,
            "service_request_id": str(e.service_request_id) if e.service_request_id else None,
            "old_value": e.old_value,
            "new_value": e.new_value,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]
