from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_membership
from app.database import get_db
from app.models.models import Assignment, OrganizationMembership, RequestStatus, ServiceRequest

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/dashboard")
async def get_dashboard(
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    org_id = membership.organization_id

    # Total and status counts
    status_counts_res = await db.execute(
        select(ServiceRequest.status, func.count(ServiceRequest.id))
        .where(ServiceRequest.org_id == org_id)
        .group_by(ServiceRequest.status)
    )
    status_counts = {str(k.value): v for k, v in status_counts_res.all()}

    # SLA breached count
    breached_count = await db.scalar(
        select(func.count(ServiceRequest.id)).where(
            ServiceRequest.org_id == org_id,
            ServiceRequest.sla_breached == True,
        )
    ) or 0

    # Total requests
    total_requests = sum(status_counts.values())

    return {
        "total_requests": total_requests,
        "status_breakdown": status_counts,
        "sla_breached_count": breached_count,
        "active_jobs": status_counts.get(RequestStatus.IN_PROGRESS.value, 0) + status_counts.get(RequestStatus.ASSIGNED.value, 0),
    }


@router.get("/utilization")
async def get_utilization(
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    # Aggregated minutes by technician
    query = (
        select(
            Assignment.technician_id,
            func.sum(Assignment.work_minutes).label("total_work_minutes"),
            func.sum(Assignment.travel_minutes).label("total_travel_minutes"),
            func.count(Assignment.id).label("total_assignments"),
        )
        .join(ServiceRequest, Assignment.service_request_id == ServiceRequest.id)
        .where(ServiceRequest.org_id == membership.organization_id)
        .group_by(Assignment.technician_id)
    )
    res = await db.execute(query)
    results = []
    for tech_id, work_min, trav_min, total_assign in res:
        results.append({
            "technician_id": str(tech_id),
            "total_work_minutes": work_min or 0,
            "total_travel_minutes": trav_min or 0,
            "total_assignments": total_assign or 0,
        })
    return results
