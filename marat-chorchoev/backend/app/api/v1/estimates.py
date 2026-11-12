import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_membership
from app.database import get_db
from app.models.models import Estimate, EstimateStatus, OrganizationMembership, RequestStatus, ServiceRequest

router = APIRouter(prefix="/estimates", tags=["estimates"])


class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: float


class EstimateCreate(BaseModel):
    service_request_id: uuid.UUID
    labor_cost: float = 0.0
    materials_cost: float = 0.0
    other_cost: float = 0.0
    tax_rate: float = 0.0
    line_items: list[LineItem] | None = None
    notes: str | None = None


class RejectPayload(BaseModel):
    reason: str


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_estimate(
    payload: EstimateCreate,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    sr = await db.get(ServiceRequest, payload.service_request_id)
    if not sr or sr.org_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Service request not found")

    subtotal = payload.labor_cost + payload.materials_cost + payload.other_cost
    total = subtotal * (1 + payload.tax_rate)

    estimate = Estimate(
        service_request_id=payload.service_request_id,
        created_by_id=membership.user_id,
        status=EstimateStatus.DRAFT,
        labor_cost=payload.labor_cost,
        materials_cost=payload.materials_cost,
        other_cost=payload.other_cost,
        tax_rate=payload.tax_rate,
        total_cost=total,
        notes=payload.notes,
        line_items=[item.model_dump() for item in payload.line_items] if payload.line_items else [],
    )
    db.add(estimate)
    await db.commit()
    await db.refresh(estimate)
    return {
        "id": str(estimate.id),
        "service_request_id": str(estimate.service_request_id),
        "total_cost": float(estimate.total_cost),
        "status": estimate.status.value,
    }


@router.post("/{estimate_id}/submit")
async def submit_estimate(
    estimate_id: uuid.UUID,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    estimate = await db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")

    sr = await db.get(ServiceRequest, estimate.service_request_id)
    if not sr or sr.org_id != membership.organization_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    estimate.status = EstimateStatus.SUBMITTED
    estimate.submitted_at = datetime.now(timezone.utc)
    sr.status = RequestStatus.PENDING_ESTIMATE

    await db.commit()
    await db.refresh(estimate)
    return {"id": str(estimate.id), "status": estimate.status.value}


@router.post("/{estimate_id}/approve")
async def approve_estimate(
    estimate_id: uuid.UUID,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    estimate = await db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")

    sr = await db.get(ServiceRequest, estimate.service_request_id)
    if not sr or sr.org_id != membership.organization_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    estimate.status = EstimateStatus.APPROVED
    estimate.reviewed_at = datetime.now(timezone.utc)
    estimate.reviewed_by_id = membership.user_id
    sr.status = RequestStatus.ESTIMATE_APPROVED

    await db.commit()
    await db.refresh(estimate)
    return {"id": str(estimate.id), "status": estimate.status.value}


@router.post("/{estimate_id}/reject")
async def reject_estimate(
    estimate_id: uuid.UUID,
    payload: RejectPayload,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    estimate = await db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")

    sr = await db.get(ServiceRequest, estimate.service_request_id)
    if not sr or sr.org_id != membership.organization_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    estimate.status = EstimateStatus.REJECTED
    estimate.reviewed_at = datetime.now(timezone.utc)
    estimate.reviewed_by_id = membership.user_id
    estimate.rejection_reason = payload.reason

    await db.commit()
    await db.refresh(estimate)
    return {"id": str(estimate.id), "status": estimate.status.value}
