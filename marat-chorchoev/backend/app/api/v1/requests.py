import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_membership
from app.database import get_db
from app.models.models import (
    AuditAction,
    AuditEvent,
    OrganizationMembership,
    RequestPriority,
    RequestStatus,
    ServiceCategory,
    ServiceRequest,
)

router = APIRouter(prefix="/requests", tags=["requests"])


class RequestCreate(BaseModel):
    title: str
    description: str | None = None
    property_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    priority: RequestPriority = RequestPriority.MEDIUM
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    tags: list[str] | None = None


class RequestUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: RequestPriority | None = None
    property_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    tags: list[str] | None = None


class StatusTransition(BaseModel):
    status: RequestStatus
    notes: str | None = None


VALID_TRANSITIONS = {
    RequestStatus.DRAFT: [RequestStatus.SUBMITTED, RequestStatus.CANCELLED],
    RequestStatus.SUBMITTED: [RequestStatus.TRIAGED, RequestStatus.ASSIGNED, RequestStatus.CANCELLED],
    RequestStatus.TRIAGED: [RequestStatus.ASSIGNED, RequestStatus.PENDING_ESTIMATE, RequestStatus.CANCELLED],
    RequestStatus.ASSIGNED: [RequestStatus.IN_PROGRESS, RequestStatus.CANCELLED],
    RequestStatus.IN_PROGRESS: [
        RequestStatus.ON_HOLD,
        RequestStatus.PENDING_PARTS,
        RequestStatus.PENDING_ESTIMATE,
        RequestStatus.COMPLETED,
        RequestStatus.CANCELLED,
    ],
    RequestStatus.ON_HOLD: [RequestStatus.IN_PROGRESS, RequestStatus.CANCELLED],
    RequestStatus.PENDING_PARTS: [RequestStatus.IN_PROGRESS, RequestStatus.CANCELLED],
    RequestStatus.PENDING_ESTIMATE: [RequestStatus.ESTIMATE_APPROVED, RequestStatus.CANCELLED],
    RequestStatus.ESTIMATE_APPROVED: [RequestStatus.IN_PROGRESS, RequestStatus.ASSIGNED, RequestStatus.CANCELLED],
    RequestStatus.COMPLETED: [RequestStatus.CLOSED],
    RequestStatus.CANCELLED: [],
    RequestStatus.CLOSED: [],
}


@router.get("")
async def list_requests(
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: RequestStatus | None = None,
    priority: RequestPriority | None = None,
    property_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    search: str | None = None,
    sla_breached: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    query = select(ServiceRequest).where(ServiceRequest.org_id == membership.organization_id)
    if status:
        query = query.where(ServiceRequest.status == status)
    if priority:
        query = query.where(ServiceRequest.priority == priority)
    if property_id:
        query = query.where(ServiceRequest.property_id == property_id)
    if asset_id:
        query = query.where(ServiceRequest.asset_id == asset_id)
    if sla_breached is not None:
        query = query.where(ServiceRequest.sla_breached == sla_breached)
    if search:
        query = query.where(
            ServiceRequest.title.ilike(f"%{search}%") | ServiceRequest.request_number.ilike(f"%{search}%")
        )

    count_q = select(func.count(ServiceRequest.id)).where(ServiceRequest.org_id == membership.organization_id)
    if status:
        count_q = count_q.where(ServiceRequest.status == status)
    if priority:
        count_q = count_q.where(ServiceRequest.priority == priority)
    if property_id:
        count_q = count_q.where(ServiceRequest.property_id == property_id)
    if asset_id:
        count_q = count_q.where(ServiceRequest.asset_id == asset_id)
    if sla_breached is not None:
        count_q = count_q.where(ServiceRequest.sla_breached == sla_breached)

    total_count = await db.scalar(count_q) or 0
    query = query.order_by(ServiceRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

    res = await db.execute(query)
    requests = res.scalars().all()

    return {
        "items": [
            {
                "id": str(r.id),
                "request_number": r.request_number,
                "title": r.title,
                "status": r.status.value,
                "priority": r.priority.value,
                "property_id": str(r.property_id) if r.property_id else None,
                "asset_id": str(r.asset_id) if r.asset_id else None,
                "category_id": str(r.category_id) if r.category_id else None,
                "sla_due_at": r.sla_due_at.isoformat() if r.sla_due_at else None,
                "sla_breached": r.sla_breached,
                "scheduled_start": r.scheduled_start.isoformat() if r.scheduled_start else None,
                "scheduled_end": r.scheduled_end.isoformat() if r.scheduled_end else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in requests
        ],
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_count + page_size - 1) // page_size,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_request(
    payload: RequestCreate,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    # Generate sequential request_number
    count = await db.scalar(select(func.count(ServiceRequest.id)).where(ServiceRequest.org_id == membership.organization_id)) or 0
    req_number = f"REQ-{datetime.now(timezone.utc).year}-{count + 1:04d}"

    # Calculate SLA due date if category has sla_hours
    sla_due_at = None
    if payload.category_id:
        cat = await db.get(ServiceCategory, payload.category_id)
        if cat and cat.sla_hours:
            sla_due_at = datetime.now(timezone.utc) + timedelta(hours=cat.sla_hours)
    if not sla_due_at:
        # Default fallback SLA by priority
        hours_map = {
            RequestPriority.EMERGENCY: 4,
            RequestPriority.URGENT: 8,
            RequestPriority.HIGH: 24,
            RequestPriority.MEDIUM: 48,
            RequestPriority.LOW: 120,
        }
        sla_due_at = datetime.now(timezone.utc) + timedelta(hours=hours_map.get(payload.priority, 48))

    sr = ServiceRequest(
        org_id=membership.organization_id,
        requester_id=membership.user_id,
        property_id=payload.property_id,
        asset_id=payload.asset_id,
        category_id=payload.category_id,
        request_number=req_number,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        status=RequestStatus.SUBMITTED,
        sla_due_at=sla_due_at,
        scheduled_start=payload.scheduled_start,
        scheduled_end=payload.scheduled_end,
        tags=payload.tags,
    )
    db.add(sr)
    await db.flush()

    audit = AuditEvent(
        org_id=membership.organization_id,
        actor_id=membership.user_id,
        service_request_id=sr.id,
        action=AuditAction.CREATE,
        entity_type="service_request",
        entity_id=sr.id,
        new_value={"title": sr.title, "status": sr.status.value},
    )
    db.add(audit)

    await db.commit()
    await db.refresh(sr)
    return {
        "id": str(sr.id),
        "request_number": sr.request_number,
        "title": sr.title,
        "status": sr.status.value,
        "priority": sr.priority.value,
        "sla_due_at": sr.sla_due_at.isoformat() if sr.sla_due_at else None,
    }


@router.get("/{request_id}")
async def get_request(
    request_id: uuid.UUID,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    sr = await db.get(ServiceRequest, request_id)
    if not sr or sr.org_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Service request not found")

    return {
        "id": str(sr.id),
        "request_number": sr.request_number,
        "title": sr.title,
        "description": sr.description,
        "status": sr.status.value,
        "priority": sr.priority.value,
        "property_id": str(sr.property_id) if sr.property_id else None,
        "asset_id": str(sr.asset_id) if sr.asset_id else None,
        "category_id": str(sr.category_id) if sr.category_id else None,
        "requester_id": str(sr.requester_id) if sr.requester_id else None,
        "sla_due_at": sr.sla_due_at.isoformat() if sr.sla_due_at else None,
        "sla_breached": sr.sla_breached,
        "scheduled_start": sr.scheduled_start.isoformat() if sr.scheduled_start else None,
        "scheduled_end": sr.scheduled_end.isoformat() if sr.scheduled_end else None,
        "actual_start": sr.actual_start.isoformat() if sr.actual_start else None,
        "actual_end": sr.actual_end.isoformat() if sr.actual_end else None,
        "completed_at": sr.completed_at.isoformat() if sr.completed_at else None,
        "resolution_notes": sr.resolution_notes,
        "created_at": sr.created_at.isoformat(),
        "updated_at": sr.updated_at.isoformat(),
    }


@router.patch("/{request_id}")
async def update_request(
    request_id: uuid.UUID,
    payload: RequestUpdate,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    sr = await db.get(ServiceRequest, request_id)
    if not sr or sr.org_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Service request not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sr, k, v)

    await db.commit()
    await db.refresh(sr)
    return {"id": str(sr.id), "request_number": sr.request_number, "title": sr.title}


@router.post("/{request_id}/status")
async def transition_status(
    request_id: uuid.UUID,
    payload: StatusTransition,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    sr = await db.get(ServiceRequest, request_id)
    if not sr or sr.org_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Service request not found")

    current_status = sr.status
    target_status = payload.status

    allowed = VALID_TRANSITIONS.get(current_status, [])
    if target_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from {current_status.value} to {target_status.value}. Allowed: {[s.value for s in allowed]}",
        )

    now = datetime.now(timezone.utc)
    sr.status = target_status

    if target_status == RequestStatus.IN_PROGRESS and not sr.actual_start:
        sr.actual_start = now
    elif target_status == RequestStatus.COMPLETED:
        sr.actual_end = now
        sr.completed_at = now
        if payload.notes:
            sr.resolution_notes = payload.notes
    elif target_status == RequestStatus.CANCELLED:
        sr.cancelled_at = now
    elif target_status == RequestStatus.CLOSED:
        sr.closed_at = now

    audit = AuditEvent(
        org_id=membership.organization_id,
        actor_id=membership.user_id,
        service_request_id=sr.id,
        action=AuditAction.STATUS_CHANGE,
        entity_type="service_request",
        entity_id=sr.id,
        old_value={"status": current_status.value},
        new_value={"status": target_status.value, "notes": payload.notes},
    )
    db.add(audit)

    await db.commit()
    await db.refresh(sr)
    return {"id": str(sr.id), "status": sr.status.value, "updated_at": sr.updated_at.isoformat()}
