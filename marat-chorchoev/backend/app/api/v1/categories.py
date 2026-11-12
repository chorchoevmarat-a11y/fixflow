import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_membership
from app.database import get_db
from app.models.models import OrganizationMembership, ServiceCategory

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryCreate(BaseModel):
    name: str
    description: str | None = None
    color: str | None = None
    icon: str | None = None
    sla_hours: float | None = None
    parent_id: uuid.UUID | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None
    sla_hours: float | None = None
    is_active: bool | None = None


@router.get("")
async def list_categories(
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    res = await db.execute(
        select(ServiceCategory).where(
            ServiceCategory.organization_id == membership.organization_id,
            ServiceCategory.is_active == True,
        )
    )
    categories = res.scalars().all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "description": c.description,
            "color": c.color,
            "icon": c.icon,
            "sla_hours": c.sla_hours,
            "parent_id": str(c.parent_id) if c.parent_id else None,
        }
        for c in categories
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    cat = ServiceCategory(
        organization_id=membership.organization_id,
        name=payload.name,
        description=payload.description,
        color=payload.color,
        icon=payload.icon,
        sla_hours=payload.sla_hours,
        parent_id=payload.parent_id,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return {"id": str(cat.id), "name": cat.name, "sla_hours": cat.sla_hours}
