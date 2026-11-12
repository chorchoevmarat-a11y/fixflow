import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_membership
from app.database import get_db
from app.models.models import OrganizationMembership, Property

router = APIRouter(prefix="/properties", tags=["properties"])


class PropertyCreate(BaseModel):
    name: str
    address: str
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str = "US"
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    access_notes: str | None = None


class PropertyUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    access_notes: str | None = None
    is_active: bool | None = None


@router.get("")
async def list_properties(
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    query = select(Property).where(
        Property.organization_id == membership.organization_id,
        Property.is_active == True,
    )
    if search:
        query = query.where(Property.name.ilike(f"%{search}%") | Property.address.ilike(f"%{search}%"))

    total_count = await db.scalar(
        select(func.count(Property.id)).where(
            Property.organization_id == membership.organization_id,
            Property.is_active == True,
        )
    ) or 0

    res = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    properties = res.scalars().all()

    return {
        "items": [
            {
                "id": str(p.id),
                "name": p.name,
                "address": p.address,
                "city": p.city,
                "state": p.state,
                "postal_code": p.postal_code,
                "country": p.country,
                "contact_name": p.contact_name,
                "contact_phone": p.contact_phone,
                "contact_email": p.contact_email,
                "access_notes": p.access_notes,
                "created_at": p.created_at.isoformat(),
            }
            for p in properties
        ],
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_count + page_size - 1) // page_size,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_property(
    payload: PropertyCreate,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    prop = Property(
        organization_id=membership.organization_id,
        name=payload.name,
        address=payload.address,
        city=payload.city,
        state=payload.state,
        postal_code=payload.postal_code,
        country=payload.country,
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        access_notes=payload.access_notes,
    )
    db.add(prop)
    await db.commit()
    await db.refresh(prop)
    return {"id": str(prop.id), "name": prop.name, "address": prop.address}


@router.get("/{property_id}")
async def get_property(
    property_id: uuid.UUID,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    prop = await db.get(Property, property_id)
    if not prop or prop.organization_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Property not found")
    return {
        "id": str(prop.id),
        "name": prop.name,
        "address": prop.address,
        "city": prop.city,
        "state": prop.state,
        "postal_code": prop.postal_code,
        "country": prop.country,
        "contact_name": prop.contact_name,
        "contact_phone": prop.contact_phone,
        "contact_email": prop.contact_email,
        "access_notes": prop.access_notes,
        "is_active": prop.is_active,
    }


@router.patch("/{property_id}")
async def update_property(
    property_id: uuid.UUID,
    payload: PropertyUpdate,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    prop = await db.get(Property, property_id)
    if not prop or prop.organization_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Property not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(prop, k, v)

    await db.commit()
    await db.refresh(prop)
    return {"id": str(prop.id), "name": prop.name}


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_property(
    property_id: uuid.UUID,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    prop = await db.get(Property, property_id)
    if not prop or prop.organization_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Property not found")
    prop.is_active = False
    await db.commit()
