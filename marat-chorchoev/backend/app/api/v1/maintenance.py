import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_membership
from app.database import get_db
from app.models.models import (
    MaintenancePlan,
    MaintenancePlanOccurrence,
    OrganizationMembership,
    RecurrenceRule,
    RequestPriority,
    RequestStatus,
    ServiceRequest,
)

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


class MaintenancePlanCreate(BaseModel):
    name: str
    description: str | None = None
    asset_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    recurrence: RecurrenceRule
    advance_days: int = 7
    priority: RequestPriority = RequestPriority.MEDIUM
    estimated_duration_minutes: int | None = 60
    start_date: datetime | None = None


@router.get("/plans")
async def list_plans(
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    query = select(MaintenancePlan).where(
        MaintenancePlan.organization_id == membership.organization_id,
        MaintenancePlan.is_active == True,
    )
    res = await db.execute(query)
    plans = res.scalars().all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "recurrence": p.recurrence.value,
            "next_occurrence": p.next_occurrence.isoformat() if p.next_occurrence else None,
            "asset_id": str(p.asset_id) if p.asset_id else None,
            "is_active": p.is_active,
        }
        for p in plans
    ]


@router.post("/plans", status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: MaintenancePlanCreate,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    next_occ = payload.start_date or datetime.now(timezone.utc)
    plan = MaintenancePlan(
        organization_id=membership.organization_id,
        name=payload.name,
        description=payload.description,
        asset_id=payload.asset_id,
        property_id=payload.property_id,
        category_id=payload.category_id,
        recurrence=payload.recurrence,
        next_occurrence=next_occ,
        advance_days=payload.advance_days,
        priority=payload.priority,
        estimated_duration_minutes=payload.estimated_duration_minutes,
        start_date=payload.start_date,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return {"id": str(plan.id), "name": plan.name, "next_occurrence": plan.next_occurrence.isoformat()}


@router.post("/plans/{plan_id}/generate")
async def trigger_generation(
    plan_id: uuid.UUID,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    plan = await db.get(MaintenancePlan, plan_id)
    if not plan or plan.organization_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Maintenance plan not found")

    occ_date = plan.next_occurrence or datetime.now(timezone.utc)

    # Check composite unique (plan_id, occurrence_date)
    existing = await db.execute(
        select(MaintenancePlanOccurrence).where(
            MaintenancePlanOccurrence.plan_id == plan.id,
            MaintenancePlanOccurrence.occurrence_date == occ_date,
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "already_generated", "occurrence_date": occ_date.isoformat()}

    # Create service request
    req_number = f"PM-{datetime.now(timezone.utc).year}-{uuid.uuid4().hex[:6].upper()}"
    sr = ServiceRequest(
        org_id=plan.organization_id,
        property_id=plan.property_id,
        asset_id=plan.asset_id,
        category_id=plan.category_id,
        request_number=req_number,
        title=f"PM: {plan.name}",
        description=plan.description,
        priority=plan.priority,
        status=RequestStatus.SUBMITTED,
        source="pm",
        scheduled_start=occ_date,
    )
    db.add(sr)
    await db.flush()

    occ = MaintenancePlanOccurrence(
        plan_id=plan.id,
        service_request_id=sr.id,
        occurrence_date=occ_date,
    )
    db.add(occ)

    # Calculate next occurrence
    rec_days = {
        RecurrenceRule.DAILY: 1,
        RecurrenceRule.WEEKLY: 7,
        RecurrenceRule.BIWEEKLY: 14,
        RecurrenceRule.MONTHLY: 30,
        RecurrenceRule.QUARTERLY: 90,
        RecurrenceRule.SEMI_ANNUAL: 180,
        RecurrenceRule.ANNUAL: 365,
    }
    days = rec_days.get(plan.recurrence, 30)
    plan.last_generated_at = datetime.now(timezone.utc)
    plan.next_occurrence = occ_date + timedelta(days=days)

    await db.commit()
    return {
        "status": "generated",
        "service_request_id": str(sr.id),
        "request_number": sr.request_number,
        "next_occurrence": plan.next_occurrence.isoformat(),
    }
