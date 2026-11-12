import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_membership, require_roles
from app.database import get_db
from app.models.models import Holiday, MemberRole, Organization, OrganizationMembership, User
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrgUpdate(BaseModel):
    name: str | None = None
    timezone: str | None = None
    business_hours: dict | None = None
    sla_policy: dict | None = None


@router.get("/current")
async def get_current_org(
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    org = await db.get(Organization, membership.organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "timezone": org.timezone,
        "business_hours": org.business_hours,
        "sla_policy": org.sla_policy,
        "your_role": membership.role.value,
    }


@router.patch("/current")
async def update_current_org(
    payload: OrgUpdate,
    membership: Annotated[OrganizationMembership, Depends(require_roles(MemberRole.OWNER, MemberRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    org = await db.get(Organization, membership.organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if payload.name is not None:
        org.name = payload.name
    if payload.timezone is not None:
        org.timezone = payload.timezone
    if payload.business_hours is not None:
        org.business_hours = payload.business_hours
    if payload.sla_policy is not None:
        org.sla_policy = payload.sla_policy

    await db.commit()
    await db.refresh(org)
    return {
        "id": str(org.id),
        "name": org.name,
        "timezone": org.timezone,
        "business_hours": org.business_hours,
        "sla_policy": org.sla_policy,
    }


@router.get("/members")
async def list_members(
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
    role: MemberRole | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    query = (
        select(OrganizationMembership, User)
        .join(User, OrganizationMembership.user_id == User.id)
        .where(
            OrganizationMembership.organization_id == membership.organization_id,
            OrganizationMembership.is_active == True,
        )
    )
    if role:
        query = query.where(OrganizationMembership.role == role)

    total_count = await db.scalar(
        select(func.count(OrganizationMembership.id)).where(
            OrganizationMembership.organization_id == membership.organization_id,
            OrganizationMembership.is_active == True,
        )
    ) or 0

    results = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = []
    for mem, usr in results:
        items.append({
            "membership_id": str(mem.id),
            "user_id": str(usr.id),
            "email": usr.email,
            "full_name": usr.full_name,
            "role": mem.role.value,
            "hourly_rate": float(mem.hourly_rate) if mem.hourly_rate else None,
            "skills": mem.skills or [],
        })

    return {
        "items": items,
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_count + page_size - 1) // page_size,
    }


@router.get("/holidays")
async def list_holidays(
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    query = select(Holiday).where(Holiday.organization_id == membership.organization_id)
    res = await db.execute(query)
    holidays = res.scalars().all()
    return [
        {
            "id": str(h.id),
            "name": h.name,
            "date": h.date.isoformat(),
            "is_recurring": h.is_recurring,
        }
        for h in holidays
    ]
