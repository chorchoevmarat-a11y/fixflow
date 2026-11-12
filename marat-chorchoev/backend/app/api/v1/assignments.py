import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_membership
from app.database import get_db
from app.models.models import (
    Assignment,
    AssignmentStatus,
    MemberRole,
    OrganizationMembership,
    RequestStatus,
    ServiceRequest,
    User,
)

router = APIRouter(prefix="/assignments", tags=["assignments"])


class AssignRequest(BaseModel):
    service_request_id: uuid.UUID
    technician_id: uuid.UUID  # OrganizationMembership id
    start_at: datetime | None = None
    end_at: datetime | None = None
    notes: str | None = None


class AssignmentStatusUpdate(BaseModel):
    status: AssignmentStatus
    travel_minutes: int | None = None
    work_minutes: int | None = None
    notes: str | None = None


@router.get("/candidates")
async def list_candidates(
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category_id: uuid.UUID | None = None,
) -> list[dict]:
    query = (
        select(OrganizationMembership, User)
        .join(User, OrganizationMembership.user_id == User.id)
        .where(
            OrganizationMembership.organization_id == membership.organization_id,
            OrganizationMembership.is_active == True,
            OrganizationMembership.role == MemberRole.TECHNICIAN,
        )
    )
    res = await db.execute(query)
    candidates = []
    for mem, usr in res:
        candidates.append({
            "id": str(mem.id),
            "user_id": str(usr.id),
            "name": usr.full_name,
            "skills": mem.skills or [],
            "hourly_rate": float(mem.hourly_rate) if mem.hourly_rate else None,
        })
    return candidates


@router.post("", status_code=status.HTTP_201_CREATED)
async def assign_technician(
    payload: AssignRequest,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    sr = await db.get(ServiceRequest, payload.service_request_id)
    if not sr or sr.org_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Service request not found")

    tech = await db.get(OrganizationMembership, payload.technician_id)
    if not tech or tech.organization_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Technician not found in this organization")

    # Check for schedule conflicts if times are provided
    if payload.start_at and payload.end_at:
        conflict_query = select(Assignment).where(
            Assignment.technician_id == payload.technician_id,
            Assignment.status.in_([AssignmentStatus.PENDING, AssignmentStatus.ACCEPTED, AssignmentStatus.EN_ROUTE, AssignmentStatus.ON_SITE]),
            Assignment.start_at < payload.end_at,
            Assignment.end_at > payload.start_at,
        )
        conflicts = (await db.execute(conflict_query)).scalars().all()
        if conflicts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Technician has a scheduling conflict during this time slot",
            )

    assignment = Assignment(
        service_request_id=payload.service_request_id,
        technician_id=payload.technician_id,
        assigned_by_id=membership.user_id,
        status=AssignmentStatus.PENDING,
        start_at=payload.start_at,
        end_at=payload.end_at,
        notes=payload.notes,
    )
    db.add(assignment)

    if sr.status in [RequestStatus.SUBMITTED, RequestStatus.TRIAGED]:
        sr.status = RequestStatus.ASSIGNED

    await db.commit()
    await db.refresh(assignment)
    return {
        "id": str(assignment.id),
        "service_request_id": str(assignment.service_request_id),
        "technician_id": str(assignment.technician_id),
        "status": assignment.status.value,
    }


@router.post("/{assignment_id}/status")
async def update_assignment_status(
    assignment_id: uuid.UUID,
    payload: AssignmentStatusUpdate,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    sr = await db.get(ServiceRequest, assignment.service_request_id)
    if not sr or sr.org_id != membership.organization_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    assignment.status = payload.status
    now = datetime.now(timezone.utc)

    if payload.status == AssignmentStatus.ACCEPTED:
        assignment.accepted_at = now
    elif payload.status == AssignmentStatus.DECLINED:
        assignment.declined_at = now
    elif payload.status == AssignmentStatus.EN_ROUTE:
        assignment.en_route_at = now
    elif payload.status == AssignmentStatus.ON_SITE:
        assignment.on_site_at = now
        if sr.status == RequestStatus.ASSIGNED:
            sr.status = RequestStatus.IN_PROGRESS
            if not sr.actual_start:
                sr.actual_start = now
    elif payload.status == AssignmentStatus.COMPLETED:
        assignment.completed_at = now

    if payload.travel_minutes is not None:
        assignment.travel_minutes = payload.travel_minutes
    if payload.work_minutes is not None:
        assignment.work_minutes = payload.work_minutes
    if payload.notes:
        assignment.notes = payload.notes

    await db.commit()
    await db.refresh(assignment)
    return {"id": str(assignment.id), "status": assignment.status.value}


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_technician(
    assignment_id: uuid.UUID,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    sr = await db.get(ServiceRequest, assignment.service_request_id)
    if not sr or sr.org_id != membership.organization_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    assignment.status = AssignmentStatus.CANCELLED
    await db.commit()
