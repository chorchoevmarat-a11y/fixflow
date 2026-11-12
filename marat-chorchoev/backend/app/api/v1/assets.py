import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_membership
from app.database import get_db
from app.models.models import Asset, AssetHistory, AssetStatus, OrganizationMembership

router = APIRouter(prefix="/assets", tags=["assets"])


class AssetCreate(BaseModel):
    property_id: uuid.UUID
    name: str
    asset_tag: str | None = None
    make: str | None = None
    model: str | None = None
    serial_number: str | None = None
    year: int | None = None
    location_description: str | None = None


class AssetUpdate(BaseModel):
    name: str | None = None
    asset_tag: str | None = None
    make: str | None = None
    model: str | None = None
    serial_number: str | None = None
    year: int | None = None
    status: AssetStatus | None = None
    location_description: str | None = None


@router.get("")
async def list_assets(
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
    property_id: uuid.UUID | None = None,
    status: AssetStatus | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    query = select(Asset).where(Asset.organization_id == membership.organization_id)
    if property_id:
        query = query.where(Asset.property_id == property_id)
    if status:
        query = query.where(Asset.status == status)
    if search:
        query = query.where(Asset.name.ilike(f"%{search}%") | Asset.asset_tag.ilike(f"%{search}%"))

    total_count = await db.scalar(
        select(func.count(Asset.id)).where(Asset.organization_id == membership.organization_id)
    ) or 0

    res = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    assets = res.scalars().all()

    return {
        "items": [
            {
                "id": str(a.id),
                "property_id": str(a.property_id),
                "name": a.name,
                "asset_tag": a.asset_tag,
                "make": a.make,
                "model": a.model,
                "serial_number": a.serial_number,
                "year": a.year,
                "status": a.status.value,
                "location_description": a.location_description,
                "created_at": a.created_at.isoformat(),
            }
            for a in assets
        ],
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_count + page_size - 1) // page_size,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_asset(
    payload: AssetCreate,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    asset = Asset(
        organization_id=membership.organization_id,
        property_id=payload.property_id,
        name=payload.name,
        asset_tag=payload.asset_tag,
        make=payload.make,
        model=payload.model,
        serial_number=payload.serial_number,
        year=payload.year,
        location_description=payload.location_description,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return {"id": str(asset.id), "name": asset.name, "asset_tag": asset.asset_tag}


@router.get("/{asset_id}")
async def get_asset(
    asset_id: uuid.UUID,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    asset = await db.get(Asset, asset_id)
    if not asset or asset.organization_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {
        "id": str(asset.id),
        "property_id": str(asset.property_id),
        "name": asset.name,
        "asset_tag": asset.asset_tag,
        "make": asset.make,
        "model": asset.model,
        "serial_number": asset.serial_number,
        "year": asset.year,
        "status": asset.status.value,
        "location_description": asset.location_description,
    }


@router.patch("/{asset_id}")
async def update_asset(
    asset_id: uuid.UUID,
    payload: AssetUpdate,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    asset = await db.get(Asset, asset_id)
    if not asset or asset.organization_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Asset not found")

    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        old_val = getattr(asset, k)
        if old_val != v:
            history = AssetHistory(
                asset_id=asset.id,
                changed_by_id=membership.user_id,
                field_name=k,
                old_value=str(old_val),
                new_value=str(v),
            )
            db.add(history)
            setattr(asset, k, v)

    await db.commit()
    await db.refresh(asset)
    return {"id": str(asset.id), "name": asset.name, "status": asset.status.value}


@router.get("/{asset_id}/history")
async def get_asset_history(
    asset_id: uuid.UUID,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    asset = await db.get(Asset, asset_id)
    if not asset or asset.organization_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Asset not found")

    res = await db.execute(select(AssetHistory).where(AssetHistory.asset_id == asset_id).order_by(AssetHistory.changed_at.desc()))
    records = res.scalars().all()
    return [
        {
            "id": str(r.id),
            "field_name": r.field_name,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "changed_at": r.changed_at.isoformat(),
        }
        for r in records
    ]
